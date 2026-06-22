"""Licenses router — /api/v1/licenses — complete REST."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.core.database import get_db
from src.server.core.security import get_current_user, require_admin
from src.server.models.license import License
from src.server.models.user import User
from src.server.services.schemas import LicenseCreate, LicenseOut, LicenseRevoke

router = APIRouter()


# ── Admin endpoints ───────────────────────────────────────────────────────────


@router.post(
    "/",
    response_model=LicenseOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
    summary="Create a new license key",
)
async def create_license(body: LicenseCreate, db: AsyncSession = Depends(get_db)):
    lic = License(
        owner=body.owner,
        machines_limit=body.machines_limit,
        expires_at=body.expires_at,
    )
    db.add(lic)
    await db.flush()
    return lic


@router.get(
    "/",
    response_model=list[LicenseOut],
    dependencies=[Depends(require_admin)],
    summary="List all licenses",
)
async def list_licenses(
    status_filter: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(License)
    if status_filter:
        q = q.where(License.status == status_filter)
    result = await db.execute(q.order_by(License.created_at.desc()))
    return result.scalars().all()


@router.get(
    "/{license_id}",
    response_model=LicenseOut,
    dependencies=[Depends(require_admin)],
    summary="Get a license by ID",
)
async def get_license(license_id: int, db: AsyncSession = Depends(get_db)):
    lic = await db.get(License, license_id)
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    return lic


@router.patch(
    "/{license_id}",
    response_model=LicenseOut,
    dependencies=[Depends(require_admin)],
    summary="Update license owner or machine limit",
)
async def update_license(
    license_id: int,
    body: LicenseCreate,
    db: AsyncSession = Depends(get_db),
):
    lic = await db.get(License, license_id)
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    if body.owner is not None:
        lic.owner = body.owner
    if body.machines_limit is not None:
        lic.machines_limit = body.machines_limit
    if body.expires_at is not None:
        lic.expires_at = body.expires_at
    return lic


@router.post(
    "/revoke",
    dependencies=[Depends(require_admin)],
    summary="Revoke a license (disables login for associated users)",
)
async def revoke_license(body: LicenseRevoke, db: AsyncSession = Depends(get_db)):
    lic = await db.get(License, body.license_id)
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    if lic.status == "revoked":
        raise HTTPException(status_code=409, detail="License already revoked")
    lic.status = "revoked"
    return {"detail": f"License {lic.key} revoked", "key": lic.key}


@router.post(
    "/{license_id}/restore",
    response_model=LicenseOut,
    dependencies=[Depends(require_admin)],
    summary="Restore a revoked license",
)
async def restore_license(license_id: int, db: AsyncSession = Depends(get_db)):
    lic = await db.get(License, license_id)
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    lic.status = "active"
    return lic


@router.delete(
    "/{license_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
    summary="Permanently delete a license (unlinks associated users)",
)
async def delete_license(license_id: int, db: AsyncSession = Depends(get_db)):
    lic = await db.get(License, license_id)
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    await db.delete(lic)


# ── Authenticated user endpoints ──────────────────────────────────────────────


@router.get(
    "/check/{key}",
    response_model=LicenseOut,
    summary="Check validity of a license key (authenticated)",
)
async def check_license(
    key: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(License).where(License.key == key))
    lic = result.scalar_one_or_none()
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    if lic.expires_at and lic.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="License expired")
    return lic


@router.get(
    "/my",
    response_model=LicenseOut,
    summary="Get the current user's license details",
)
async def my_license(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.license_id:
        raise HTTPException(status_code=404, detail="No license attached to account")
    lic = await db.get(License, user.license_id)
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    return lic
