"""Initial schema — all tables.

Revision ID: 0001
Revises: 
Create Date: 2025-06-01 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "licenses",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(64), unique=True, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("owner", sa.String(64), nullable=True),
        sa.Column("machines_limit", sa.Integer, nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_licenses_key", "licenses", ["key"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("license_id", sa.Integer, sa.ForeignKey("licenses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "machines",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hardware_id", sa.String(128), nullable=False),
        sa.Column("hostname", sa.String(128), nullable=True),
        sa.Column("os_info", sa.String(256), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("is_banned", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("ban_reason", sa.String(256), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_machines_user_id", "machines", ["user_id"])
    op.create_index("ix_machines_hardware_id", "machines", ["hardware_id"])

    op.create_table(
        "uploads",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_name", sa.String(256), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_uploads_user_id", "uploads", ["user_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("jti", sa.String(64), unique=True, nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("parent_jti", sa.String(64), nullable=True),
        sa.Column("issued_ip", sa.String(45), nullable=True),
    )
    op.create_index("ix_refresh_tokens_jti", "refresh_tokens", ["jti"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    op.create_table(
        "iso_chunk_uploads",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("upload_id", sa.String(64), unique=True, nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(256), nullable=False),
        sa.Column("total_size", sa.BigInteger, nullable=False),
        sa.Column("total_chunks", sa.Integer, nullable=False),
        sa.Column("received_chunks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_iso_chunk_uploads_upload_id", "iso_chunk_uploads", ["upload_id"])
    op.create_index("ix_iso_chunk_uploads_user_id", "iso_chunk_uploads", ["user_id"])


def downgrade() -> None:
    op.drop_table("iso_chunk_uploads")
    op.drop_table("refresh_tokens")
    op.drop_table("uploads")
    op.drop_table("machines")
    op.drop_table("users")
    op.drop_table("licenses")
