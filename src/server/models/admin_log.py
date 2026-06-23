"""AdminActionLog ORM model — audit trail for every admin action."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.server.core.database import Base


class AdminActionLog(Base):
    __tablename__ = "admin_action_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # e.g. "delete_iso", "ban_user", "unban_user", "report_accept", "report_ignore",
    #      "report_ban_reporter", "cancel_upload"
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(256), nullable=False)  # filename / user id / etc.
    detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


async def log_admin_action(db, action: str, target: str, detail: str | None = None) -> None:
    """Convenience helper used across admin routes."""
    db.add(AdminActionLog(action=action, target=target, detail=detail))
    await db.flush()
