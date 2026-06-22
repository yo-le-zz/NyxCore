"""
Admin router — /admin (web panel) + /admin/api (REST)
"""

from __future__ import annotations

import pathlib
import secrets
import shutil
from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.core.config import settings
from src.server.core.database import get_db
from src.server.core.security import require_admin
from src.server.models.license import License
from src.server.models.machine import Machine
from src.server.models.upload import Upload
from src.server.models.user import User
from src.server.services.schemas import AdminStats

_TMPL_DIR = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TMPL_DIR))

_sessions: dict[str, float] = {}
_SESSION_TTL = 3600

router = APIRouter()


def _new_session() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = datetime.now(UTC).timestamp() + _SESSION_TTL
    return token


def _valid_session(token: str | None) -> bool:
    if not token or token not in _sessions:
        return False
    if datetime.now(UTC).timestamp() > _sessions[token]:
        del _sessions[token]
        return False
    return True


def _require_session(admin_session: str | None = Cookie(default=None)):
    if not _valid_session(admin_session):
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    return admin_session


async def _get_stats(db: AsyncSession) -> dict:
    users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    lics = (await db.execute(select(func.count()).select_from(License))).scalar_one()
    active_l = (
        await db.execute(
            select(func.count()).select_from(License).where(License.status == "active")
        )
    ).scalar_one()
    machines = (await db.execute(select(func.count()).select_from(Machine))).scalar_one()
    banned = (
        await db.execute(
            select(func.count()).select_from(Machine).where(Machine.is_banned.is_(True))
        )
    ).scalar_one()
    uploads = (await db.execute(select(func.count()).select_from(Upload))).scalar_one()
    usage = shutil.disk_usage(str(settings.iso_path))
    used_pct = round((usage.used / usage.total) * 100, 1)
    return {
        "total_users": users,
        "total_licenses": lics,
        "active_licenses": active_l,
        "total_machines": machines,
        "banned_machines": banned,
        "total_uploads": uploads,
        "disk_used_gb": round(usage.used / 1e9, 2),
        "disk_total_gb": round(usage.total / 1e9, 2),
        "disk_used_pct": used_pct,
        "disk_alert": used_pct >= settings.DISK_ALERT_THRESHOLD_PCT,
    }


# ── Web panel ──────────────────────────────────────────────────────────────────


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "admin/login.html", {"error": ""})


@router.post("/login", include_in_schema=False)
async def login_submit(request: Request, password: str = Form(...)):
    if not secrets.compare_digest(password, settings.MASTER_PASSWORD):
        return templates.TemplateResponse(
            request, "admin/login.html", {"error": "Invalid password"}, status_code=401
        )
    token = _new_session()
    resp = RedirectResponse(url="/admin/", status_code=303)
    resp.set_cookie(
        "admin_session",
        token,
        httponly=True,
        samesite="strict",
        max_age=_SESSION_TTL,
        secure=not settings.DEBUG,
    )
    return resp


@router.get("/logout", include_in_schema=False)
async def logout(admin_session: str | None = Cookie(default=None)):
    if admin_session and admin_session in _sessions:
        del _sessions[admin_session]
    resp = RedirectResponse(url="/admin/login", status_code=303)
    resp.delete_cookie("admin_session")
    return resp


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(
    request: Request, session=Depends(_require_session), db: AsyncSession = Depends(get_db)
):
    stats = await _get_stats(db)
    recent = (
        (await db.execute(select(Upload).order_by(Upload.timestamp.desc()).limit(10)))
        .scalars()
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "stats": stats,
            "recent_uploads": recent,
        },
    )


@router.get("/users", response_class=HTMLResponse, include_in_schema=False)
async def users_page(
    request: Request, session=Depends(_require_session), db: AsyncSession = Depends(get_db)
):
    users = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    lics = {l.id: l for l in (await db.execute(select(License))).scalars().all()}
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "users": users,
            "licenses": lics,
        },
    )


@router.get("/licenses", response_class=HTMLResponse, include_in_schema=False)
async def licenses_page(
    request: Request, session=Depends(_require_session), db: AsyncSession = Depends(get_db)
):
    lics = (await db.execute(select(License).order_by(License.created_at.desc()))).scalars().all()
    return templates.TemplateResponse(request, "admin/licenses.html", {"licenses": lics})


@router.get("/machines", response_class=HTMLResponse, include_in_schema=False)
async def machines_page(
    request: Request, session=Depends(_require_session), db: AsyncSession = Depends(get_db)
):
    machines = (
        (await db.execute(select(Machine).order_by(Machine.last_seen.desc()))).scalars().all()
    )
    users = {u.id: u for u in (await db.execute(select(User))).scalars().all()}
    return templates.TemplateResponse(
        request,
        "admin/machines.html",
        {
            "machines": machines,
            "users": users,
        },
    )


@router.get("/isos", response_class=HTMLResponse, include_in_schema=False)
async def isos_page(request: Request, session=Depends(_require_session)):
    from src.server.services import iso_storage

    raw = iso_storage.list_complete()
    files = [
        {
            "file_name": f["file_name"],
            "file_size": f["file_size"],
            "uploaded_at": datetime.fromtimestamp(f["mtime"], tz=UTC).strftime("%Y-%m-%d %H:%M"),
        }
        for f in raw
    ]
    return templates.TemplateResponse(request, "admin/isos.html", {"files": files})


# ── Form actions ───────────────────────────────────────────────────────────────


@router.post("/users/{user_id}/toggle", include_in_schema=False)
async def toggle_user(
    user_id: int, session=Depends(_require_session), db: AsyncSession = Depends(get_db)
):
    user = await db.get(User, user_id)
    if user:
        user.is_active = not user.is_active
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/machines/{machine_id}/ban", include_in_schema=False)
async def ban_machine_web(
    machine_id: int,
    reason: str = Form(default="Banned by admin"),
    session=Depends(_require_session),
    db: AsyncSession = Depends(get_db),
):
    machine = await db.get(Machine, machine_id)
    if machine:
        machine.is_banned = True
        machine.ban_reason = reason
    return RedirectResponse(url="/admin/machines", status_code=303)


@router.post("/machines/{machine_id}/unban", include_in_schema=False)
async def unban_machine_web(
    machine_id: int, session=Depends(_require_session), db: AsyncSession = Depends(get_db)
):
    machine = await db.get(Machine, machine_id)
    if machine:
        machine.is_banned = False
        machine.ban_reason = None
    return RedirectResponse(url="/admin/machines", status_code=303)


@router.post("/licenses/create", include_in_schema=False)
async def create_license_web(
    owner: str = Form(default=""),
    machines_limit: int = Form(default=3),
    session=Depends(_require_session),
    db: AsyncSession = Depends(get_db),
):
    lic = License(owner=owner or None, machines_limit=machines_limit)
    db.add(lic)
    return RedirectResponse(url="/admin/licenses", status_code=303)


@router.post("/licenses/{license_id}/revoke", include_in_schema=False)
async def revoke_license_web(
    license_id: int, session=Depends(_require_session), db: AsyncSession = Depends(get_db)
):
    lic = await db.get(License, license_id)
    if lic:
        lic.status = "revoked"
    return RedirectResponse(url="/admin/licenses", status_code=303)


# ── REST (Bearer) ──────────────────────────────────────────────────────────────


@router.get("/api/stats", response_model=AdminStats, dependencies=[Depends(require_admin)])
async def api_stats(db: AsyncSession = Depends(get_db)):
    s = await _get_stats(db)
    return AdminStats(
        total_users=s["total_users"],
        total_licenses=s["total_licenses"],
        total_machines=s["total_machines"],
        total_uploads=s["total_uploads"],
        disk_used_gb=s["disk_used_gb"],
        disk_total_gb=s["disk_total_gb"],
        disk_used_pct=s["disk_used_pct"],
        alert=s["disk_alert"],
    )


@router.get("/api/users", dependencies=[Depends(require_admin)])
async def api_users(db: AsyncSession = Depends(get_db)):
    users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "is_active": u.is_active,
            "license_id": u.license_id,
            "created_at": u.created_at.isoformat(),
            "last_login": u.last_login.isoformat() if u.last_login else None,
        }
        for u in users
    ]


@router.post("/api/users/{user_id}/toggle", dependencies=[Depends(require_admin)])
async def api_toggle_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    return {"id": user.id, "is_active": user.is_active}


@router.get("/api/machines", dependencies=[Depends(require_admin)])
async def api_machines(db: AsyncSession = Depends(get_db)):
    machines = (
        (await db.execute(select(Machine).order_by(Machine.last_seen.desc()))).scalars().all()
    )
    return [
        {
            "id": m.id,
            "user_id": m.user_id,
            "hardware_id": m.hardware_id,
            "hostname": m.hostname,
            "ip": m.ip,
            "os_info": m.os_info,
            "is_banned": m.is_banned,
            "ban_reason": m.ban_reason,
            "last_seen": m.last_seen.isoformat(),
        }
        for m in machines
    ]


@router.get("/api/uploads", dependencies=[Depends(require_admin)])
async def api_uploads(db: AsyncSession = Depends(get_db)):
    uploads = (
        (await db.execute(select(Upload).order_by(Upload.timestamp.desc()).limit(500)))
        .scalars()
        .all()
    )
    return [
        {
            "id": u.id,
            "user_id": u.user_id,
            "file_name": u.file_name,
            "file_size": u.file_size,
            "action": u.action,
            "timestamp": u.timestamp.isoformat(),
        }
        for u in uploads
    ]
