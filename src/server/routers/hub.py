"""
Public Hub router — /hub/

Read-only website for people who do NOT have the NyxCore client installed:
  - GET  /hub/             → list/search/sort ISOs, download links
  - GET  /hub/stats        → public usage stats
  - GET  /hub/download/{filename} → direct HTTP download (NO upload, NO auth)

Strictly read-only: this module exposes no write/delete/upload routes. Visit
and download counters are the only writes, and they happen server-side only
(never client-controlled beyond "a request happened").
"""

from __future__ import annotations

import hashlib
import pathlib
from datetime import UTC, datetime

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.core.database import get_db
from src.server.models.hub import HubDownload, HubVisit
from src.server.models.upload import Upload
from src.server.models.user import User
from src.server.services import iso_storage
from src.server.services.schemas import HubStatsOut

_TMPL_DIR = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TMPL_DIR))

router = APIRouter()


def _client_ip(request: Request) -> str:
    # Respect a reverse proxy header if present, otherwise fall back to the
    # direct connection IP. Hashed before storage — we never need the raw IP.
    forwarded = request.headers.get("x-forwarded-for")
    return (forwarded.split(",")[0].strip() if forwarded else request.client.host) or "unknown"


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()


async def _record_visit(request: Request, db: AsyncSession) -> None:
    """One row per unique (ip, day) — refreshing the page repeatedly doesn't inflate stats."""
    ip_hash = _hash_ip(_client_ip(request))
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    existing = await db.execute(
        select(HubVisit).where(HubVisit.ip_hash == ip_hash, HubVisit.day == day)
    )
    if existing.scalar_one_or_none() is None:
        db.add(HubVisit(ip_hash=ip_hash, day=day))
        await db.flush()


async def _owner_map(db: AsyncSession) -> dict[str, str]:
    result = await db.execute(
        select(Upload.file_name, User.username)
        .join(User, User.id == Upload.user_id)
        .where(Upload.action == "upload")
        .order_by(Upload.timestamp.desc())
    )
    owners: dict[str, str] = {}
    for file_name, username in result.all():
        owners.setdefault(file_name, username)
    return owners


async def _download_counts(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(
        select(HubDownload.file_name, func.count()).group_by(HubDownload.file_name)
    )
    return {name: count for name, count in result.all()}


# ── Public homepage ────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def hub_home(
    request: Request,
    q: str = "",
    sort: str = "date",
    db: AsyncSession = Depends(get_db),
):
    await _record_visit(request, db)

    raw = iso_storage.list_complete()
    owners = await _owner_map(db)
    download_counts = await _download_counts(db)

    isos = []
    for f in raw:
        isos.append(
            {
                "file_name": f["file_name"],
                "file_size": f["file_size"],
                "uploaded_at": datetime.fromtimestamp(f["mtime"], tz=UTC),
                "uploader": owners.get(f["file_name"], "unknown"),
                "download_count": download_counts.get(f["file_name"], 0),
            }
        )

    if q:
        q_lower = q.lower()
        isos = [i for i in isos if q_lower in i["file_name"].lower()]

    sort_key = {
        "name": lambda i: i["file_name"].lower(),
        "size": lambda i: i["file_size"],
        "popularity": lambda i: i["download_count"],
        "date": lambda i: i["uploaded_at"],
    }.get(sort, lambda i: i["uploaded_at"])
    isos.sort(key=sort_key, reverse=(sort != "name"))

    return templates.TemplateResponse(
        request,
        "hub/index.html",
        {"isos": isos, "query": q, "sort": sort},
    )


# ── Public stats page ──────────────────────────────────────────────────────────


@router.get("/stats", response_class=HTMLResponse, include_in_schema=False)
async def hub_stats_page(request: Request, db: AsyncSession = Depends(get_db)):
    stats = await _compute_public_stats(db)
    return templates.TemplateResponse(request, "hub/stats.html", {"stats": stats})


@router.get("/api/stats", response_model=HubStatsOut, include_in_schema=False)
async def hub_stats_api(db: AsyncSession = Depends(get_db)):
    s = await _compute_public_stats(db)
    return HubStatsOut(**s)


async def _compute_public_stats(db: AsyncSession) -> dict:
    import shutil

    from src.server.core.config import settings

    total_visits = (await db.execute(select(func.count()).select_from(HubVisit))).scalar_one()
    total_hub_downloads = (
        await db.execute(select(func.count()).select_from(HubDownload))
    ).scalar_one()
    total_isos = len(iso_storage.list_complete())
    usage = shutil.disk_usage(str(settings.iso_path))

    return {
        "total_visits": total_visits,
        "total_hub_downloads": total_hub_downloads,
        "total_isos": total_isos,
        "total_disk_used_gb": round(usage.used / 1e9, 2),
        "total_disk_available_gb": round(usage.free / 1e9, 2),
    }


# ── Public download (no auth, no upload route exists in this router) ──────────


@router.get("/download/{filename}", include_in_schema=False)
async def hub_download(filename: str, request: Request, db: AsyncSession = Depends(get_db)):
    import re

    if not re.match(r"^[a-zA-Z0-9_\-\.]{1,200}$", filename) or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    path = iso_storage.complete_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="ISO not found")

    db.add(HubDownload(file_name=filename, ip_hash=_hash_ip(_client_ip(request))))
    await db.flush()

    file_size = path.stat().st_size

    async def _gen():
        async with aiofiles.open(path, "rb") as f:
            while chunk := await f.read(1024 * 1024):
                yield chunk

    headers = {
        "Content-Length": str(file_size),
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    return StreamingResponse(
        _gen(), status_code=200, headers=headers, media_type="application/octet-stream"
    )
