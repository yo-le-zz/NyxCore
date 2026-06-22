"""Pydantic schemas — licenses, machines, isos, admin, chunks."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Licenses ──────────────────────────────────────────────────────────────────

class LicenseCreate(BaseModel):
    owner: str | None = Field(None, max_length=64)
    machines_limit: int = Field(3, ge=1, le=100)
    expires_at: datetime | None = None


class LicenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    key: str
    status: str
    owner: str | None
    machines_limit: int
    created_at: datetime
    expires_at: datetime | None


class LicenseRevoke(BaseModel):
    license_id: int


# ── Machines ──────────────────────────────────────────────────────────────────

class MachineRegister(BaseModel):
    hardware_id: str = Field(..., min_length=4, max_length=128)
    hostname: str | None = Field(None, max_length=128)
    os_info: str | None = Field(None, max_length=256)


class MachineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    hardware_id: str
    hostname: str | None
    os_info: str | None
    ip: str | None
    is_banned: bool
    ban_reason: str | None
    registered_at: datetime
    last_seen: datetime


class MachineBan(BaseModel):
    machine_id: int
    reason: str = Field(..., min_length=1, max_length=256)


# ── ISOs ──────────────────────────────────────────────────────────────────────

class ISOOut(BaseModel):
    file_name: str
    file_size: int
    uploaded_at: datetime


class UploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    file_name: str
    file_size: int
    action: str
    timestamp: datetime


# ── Chunked upload schemas ────────────────────────────────────────────────────

class ChunkUploadInit(BaseModel):
    filename: str = Field(..., min_length=1, max_length=200)
    total_size: int = Field(..., gt=0, description="Total file size in bytes")
    sha256: str | None = Field(None, min_length=64, max_length=64, description="Expected SHA-256 hex of the complete file")


class ChunkUploadInitResponse(BaseModel):
    upload_id: str
    chunk_size: int
    total_chunks: int


class ChunkStatus(BaseModel):
    upload_id: str
    filename: str
    status: str
    total_chunks: int
    received_chunks: int
    missing_chunks: list[int]


# ── Admin ─────────────────────────────────────────────────────────────────────

class AdminStats(BaseModel):
    total_users: int
    total_licenses: int
    total_machines: int
    total_uploads: int
    disk_used_gb: float
    disk_total_gb: float
    disk_used_pct: float
    alert: bool


class AdminUserAction(BaseModel):
    user_id: int
    action: Literal["activate", "deactivate"]
