"""Health & info router — /api/v1/health"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.core.config import settings
from src.server.core.database import get_db

router = APIRouter()
_started_at = datetime.now(UTC)


@router.get("/health", summary="Server health check")
async def health(db: AsyncSession = Depends(get_db)):
    # Quick DB ping
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    usage = shutil.disk_usage(str(settings.iso_path))
    disk_pct = round((usage.used / usage.total) * 100, 1)
    uptime_s = int((datetime.now(UTC) - _started_at).total_seconds())

    return {
        "status": "ok" if db_ok else "degraded",
        "version": settings.VERSION,
        "app": settings.APP_NAME,
        "db": "ok" if db_ok else "error",
        "db_backend": settings.DB_BACKEND,
        "disk_used_pct": disk_pct,
        "disk_alert": disk_pct >= settings.DISK_ALERT_THRESHOLD_PCT,
        "uptime_seconds": uptime_s,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/info", summary="Server info (public)")
async def info():
    return {
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "db_backend": settings.DB_BACKEND,
    }
