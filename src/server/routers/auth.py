"""Auth router — /api/v1/auth."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.core.config import settings
from src.server.core.database import get_db
from src.server.core.security import (
    consume_refresh_token,
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    revoke_all_user_tokens,
    verify_password,
)
from src.server.models.license import License
from src.server.models.user import User
from src.server.services.schemas_auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    lic_result = await db.execute(select(License).where(License.key == body.license_key))
    lic = lic_result.scalar_one_or_none()
    if lic is None:
        raise HTTPException(status_code=400, detail="License key not found")
    if lic.status != "active":
        raise HTTPException(status_code=400, detail=f"License is {lic.status}")
    if lic.expires_at and lic.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="License has expired")

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        license_id=lic.id,
    )
    db.add(user)
    await db.flush()
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    # Constant-time: always check password even if user not found (prevent user enumeration)
    dummy_hash = "0" * 64 + "$" + "0" * 128
    stored = user.password_hash if user else dummy_hash
    valid = verify_password(body.password, stored)

    if not valid or user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    if user.license_id:
        lic_result = await db.execute(select(License).where(License.id == user.license_id))
        lic = lic_result.scalar_one_or_none()
        if lic and lic.status != "active":
            raise HTTPException(status_code=403, detail="Your license has been revoked")

    user.last_login = datetime.now(UTC)

    access = create_access_token(str(user.id))
    refresh = await create_refresh_token(user.id, db, request)

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(body: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Token rotation with reuse detection.
    Old refresh token is consumed (one-time use). New pair is issued.
    If the old token was already revoked → all sessions are nuked.
    """
    user_id, parent_jti = await consume_refresh_token(body.refresh_token, db, request)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    access = create_access_token(str(user_id))
    refresh = await create_refresh_token(user_id, db, request, parent_jti=parent_jti)

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all refresh tokens for the current user (full logout)."""
    await revoke_all_user_tokens(user.id, db)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
