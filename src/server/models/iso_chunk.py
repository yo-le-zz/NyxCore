"""ISOChunkUpload ORM model — tracks resumable multipart uploads."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.server.core.database import Base


class ISOChunkUpload(Base):
    __tablename__ = "iso_chunk_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Unique session ID returned to client to resume uploads
    upload_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    total_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    received_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # pending | uploading | assembling | complete | failed
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    # SHA-256 of the complete assembled file (set by client, verified after assembly)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    user: Mapped["User"] = relationship("User")  # noqa: F821
