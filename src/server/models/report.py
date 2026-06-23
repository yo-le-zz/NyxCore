"""Report ORM model — user-submitted ISO reports, reviewed from the admin panel."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.server.core.database import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The ISO being reported, identified by filename (ISOs live on the filesystem,
    # not in a dedicated table — same approach as the rest of the codebase).
    file_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)

    reporter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # pending | accepted | ignored
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Free-text note left by the admin when resolving (optional)
    resolution_note: Mapped[str | None] = mapped_column(String(256), nullable=True)

    reporter: Mapped[User] = relationship("User")  # noqa: F821
