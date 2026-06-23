"""HubVisit ORM model — public /hub/ analytics (visits + public downloads)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.server.core.database import Base


class HubVisit(Base):
    """
    One row per unique (ip, day) visit to the public hub homepage.
    Counting unique IP/day pairs avoids inflating the visit counter on
    every page refresh while still being simple (no session/cookie needed).
    """

    __tablename__ = "hub_visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # "YYYY-MM-DD"
    visited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class HubDownload(Base):
    """One row per completed download served through the public /hub/ site."""

    __tablename__ = "hub_downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
