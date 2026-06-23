"""User ORM model."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.server.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    license_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("licenses.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── User-level ban (distinct from per-machine ban) ─────────────────────────
    # A banned user cannot log in (software) nor authenticate with the public hub.
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ban_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Cached counters (kept in sync at upload-complete / download time) ──────
    # Kept separate so the admin panel can show "files uploaded" vs "files
    # downloaded" instead of a single merged "transfers" number.
    total_uploads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_downloads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_upload_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_download_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    license: Mapped[License | None] = relationship("License", back_populates="users")  # noqa: F821
    machines: Mapped[list[Machine]] = relationship(
        "Machine", back_populates="user", cascade="all, delete-orphan"
    )  # noqa: F821
    uploads: Mapped[list[Upload]] = relationship(
        "Upload", back_populates="user", cascade="all, delete-orphan"
    )  # noqa: F821
