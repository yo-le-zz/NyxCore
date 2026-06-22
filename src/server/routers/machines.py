"""Machines router — /api/v1/machines — complete REST."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.core.database import get_db
from src.server.core.security import get_current_user, require_admin
from src.server.models.license import License
from src.server.models.machine import Machine
from src.server.models.user import User
from src.server.services.schemas import MachineBan, MachineOut, MachineRegister

router = APIRouter()


# ── User endpoints ────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=MachineOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register or heartbeat a machine (idempotent by hardware_id)",
)
async def register_machine(
    body: MachineRegister,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client_ip = request.client.host if request.client else None

    # Check existing registration first
    existing = await db.execute(
        select(Machine).where(
            Machine.user_id == user.id,
            Machine.hardware_id == body.hardware_id,
        )
    )
    machine = existing.scalar_one_or_none()

    if machine:
        if machine.is_banned:
            raise HTTPException(status_code=403, detail=f"Machine banned: {machine.ban_reason}")
        # Heartbeat — update last_seen
        machine.last_seen = datetime.now(UTC)
        machine.ip = client_ip
        if body.os_info:
            machine.os_info = body.os_info
        if body.hostname:
            machine.hostname = body.hostname
        await db.flush()
        return machine

    # New machine — check license limit
    if user.license_id:
        lic = await db.get(License, user.license_id)
        if lic:
            count = (await db.execute(
                select(func.count()).select_from(Machine)
                .where(Machine.user_id == user.id, Machine.is_banned.is_(False))
            )).scalar_one()
            if count >= lic.machines_limit:
                raise HTTPException(
                    status_code=403,
                    detail=f"Machine limit reached ({lic.machines_limit}/{lic.machines_limit})",
                )

    machine = Machine(
        user_id=user.id,
        hardware_id=body.hardware_id,
        hostname=body.hostname,
        os_info=body.os_info,
        ip=client_ip,
    )
    db.add(machine)
    await db.flush()
    return machine


@router.get(
    "/",
    response_model=list[MachineOut],
    summary="List current user's machines",
)
async def list_my_machines(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Machine).where(Machine.user_id == user.id).order_by(Machine.last_seen.desc())
    )
    return result.scalars().all()


@router.get(
    "/{machine_id}",
    response_model=MachineOut,
    summary="Get details of one of your machines",
)
async def get_my_machine(
    machine_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    machine = await db.get(Machine, machine_id)
    if not machine or machine.user_id != user.id:
        raise HTTPException(status_code=404, detail="Machine not found")
    return machine


@router.delete(
    "/{machine_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unregister one of your own machines",
)
async def delete_my_machine(
    machine_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    machine = await db.get(Machine, machine_id)
    if not machine or machine.user_id != user.id:
        raise HTTPException(status_code=404, detail="Machine not found")
    await db.delete(machine)


# ── Admin endpoints ───────────────────────────────────────────────────────────

@router.get(
    "/admin/all",
    response_model=list[MachineOut],
    dependencies=[Depends(require_admin)],
    summary="[Admin] List all machines across all users",
)
async def list_all_machines(
    banned_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    q = select(Machine)
    if banned_only:
        q = q.where(Machine.is_banned.is_(True))
    result = await db.execute(q.order_by(Machine.last_seen.desc()))
    return result.scalars().all()


@router.post(
    "/admin/ban",
    summary="[Admin] Ban a machine",
    dependencies=[Depends(require_admin)],
)
async def ban_machine(body: MachineBan, db: AsyncSession = Depends(get_db)):
    machine = await db.get(Machine, body.machine_id)
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    if machine.is_banned:
        raise HTTPException(status_code=409, detail="Machine already banned")
    machine.is_banned = True
    machine.ban_reason = body.reason
    return {"detail": f"Machine {machine.id} banned", "machine_id": machine.id}


@router.post(
    "/admin/unban/{machine_id}",
    response_model=MachineOut,
    dependencies=[Depends(require_admin)],
    summary="[Admin] Unban a machine",
)
async def unban_machine(machine_id: int, db: AsyncSession = Depends(get_db)):
    machine = await db.get(Machine, machine_id)
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    machine.is_banned = False
    machine.ban_reason = None
    return machine


@router.delete(
    "/admin/{machine_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
    summary="[Admin] Force-delete any machine",
)
async def admin_delete_machine(machine_id: int, db: AsyncSession = Depends(get_db)):
    machine = await db.get(Machine, machine_id)
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    await db.delete(machine)
