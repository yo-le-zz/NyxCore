"""
NyxCore — security layer.

Threat model addressed:
  1. Replay attacks       → JTI (JWT ID) stored in DB; each token single-use for refresh
  2. Refresh token theft  → token stored as SHA-256 hash in DB; raw value only in transit
  3. Token rotation       → every /refresh issues a NEW jti, revokes the old one;
                            if an already-revoked JTI is presented → full session wipe
                            (detect token theft via "refresh token reuse detection")
  4. Access token scope   → 15 min TTL (short window if stolen)
  5. Timing attacks       → secrets.compare_digest everywhere
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.core.config import settings
from src.server.core.database import get_db

_bearer = HTTPBearer(auto_error=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# ── Password (SHA-512 + random salt) ─────────────────────────────────────────

def hash_password(plain: str) -> str:
    salt = secrets.token_hex(32)
    digest = hashlib.sha512(f"{salt}{plain}".encode()).hexdigest()
    return f"{salt}${digest}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(
        hashlib.sha512(f"{salt}{plain}".encode()).hexdigest(),
        digest,
    )


# ── JWT (access token — short-lived, stateless) ───────────────────────────────

def create_access_token(subject: str) -> str:
    """
    Access token: HS256, 15-minute TTL, no DB entry needed.
    Kept short so that even if intercepted the window is small.
    """
    jti = secrets.token_urlsafe(32)
    payload = {
        "sub": subject,
        "jti": jti,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── Refresh token (stateful — stored as hash in DB) ───────────────────────────

async def create_refresh_token(
    user_id: int,
    db: AsyncSession,
    request: Request | None = None,
    parent_jti: str | None = None,
) -> str:
    """
    Issue a new refresh token:
    - Raw token = cryptographically random opaque string (urlsafe, 48 bytes)
    - Stored as SHA-256(raw) in DB
    - JTI = separate random ID embedded in the JWT so we can look it up

    Returns the raw token (send to client once, never stored raw).
    """
    from src.server.models.token import RefreshToken

    raw = secrets.token_urlsafe(48)
    jti = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    client_ip = request.client.host if (request and request.client) else None

    record = RefreshToken(
        jti=jti,
        user_id=user_id,
        token_hash=_sha256(raw),
        expires_at=expires_at,
        parent_jti=parent_jti,
        issued_ip=client_ip,
    )
    db.add(record)
    await db.flush()

    # Embed jti inside a signed JWT so the client sends ONE value and we verify both
    # signature (HMAC) and DB lookup (revocation / reuse detection).
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "iat": datetime.now(UTC),
        "exp": expires_at,
        "type": "refresh",
    }
    signed = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    # Combine signed JWT + raw secret: "signed.raw" — client stores and sends as-is
    return f"{signed}.{raw}"


async def consume_refresh_token(
    token: str,
    db: AsyncSession,
    request: Request | None = None,
) -> tuple[int, str]:
    """
    Validate, consume, and return (user_id, parent_jti) for the incoming refresh token.

    Reuse detection: if the JTI is already revoked → someone is replaying a stolen token.
    We immediately revoke ALL tokens for that user (force re-login everywhere).

    Returns (user_id, jti) so the caller can issue a new token with parent_jti set.

    Raises HTTPException on any error.
    """
    from src.server.models.token import RefreshToken

    try:
        signed_part, raw_part = token.rsplit(".", 1)
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed refresh token")

    # 1. Verify JWT signature + expiry
    payload = decode_token(signed_part)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Wrong token type")

    jti: str = payload.get("jti", "")
    user_id: int = int(payload["sub"])

    # 2. Look up DB record by JTI
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.jti == jti)
    )
    record = result.scalar_one_or_none()

    if record is None:
        raise HTTPException(status_code=401, detail="Refresh token not found")

    # 3. Reuse detection — JTI already revoked → token theft suspected
    if record.revoked:
        # Revoke ALL refresh tokens for this user (nuclear option)
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
            .values(revoked=True)
        )
        await db.commit()   # must commit immediately — nuclear revoke must be visible to next request
        raise HTTPException(
            status_code=401,
            detail="Refresh token reuse detected — all sessions invalidated",
        )

    # 4. Expiry check (belt + suspenders — JWT exp already checked above)
    _exp = record.expires_at
    if _exp.tzinfo is None:
        _exp = _exp.replace(tzinfo=UTC)
    if _exp < datetime.now(UTC):
        record.revoked = True
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # 5. Hash comparison — timing-safe
    expected_hash = _sha256(raw_part)
    if not secrets.compare_digest(record.token_hash, expected_hash):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # 6. Revoke this token (one-time use)
    record.revoked = True
    await db.flush()

    return user_id, jti


async def revoke_all_user_tokens(user_id: int, db: AsyncSession) -> None:
    """Logout — invalidate every active refresh token for the user."""
    from src.server.models.token import RefreshToken

    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )
    await db.flush()


# ── FastAPI dependencies ──────────────────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Security(_bearer)],
    db: AsyncSession = Depends(get_db),
):
    from src.server.models.user import User

    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Wrong token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")
    return user


async def require_admin(
    credentials: Annotated[HTTPAuthorizationCredentials, Security(_bearer)],
):
    if not secrets.compare_digest(credentials.credentials, settings.MASTER_PASSWORD):
        raise HTTPException(status_code=403, detail="Admin access denied")
