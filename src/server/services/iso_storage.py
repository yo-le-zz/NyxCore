"""
ISO storage backend.

Abstracts filesystem operations so switching to S3 later only requires
implementing the same interface. Current implementation: local filesystem
with per-upload chunk staging directories.

Layout on disk:
  ISO_STORAGE_PATH/
    ├── complete/            ← finished, verified ISOs
    │   └── debian-12.iso
    └── staging/
        └── <upload_id>/     ← temporary chunk dir
            ├── 000000
            ├── 000001
            └── ...
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

import aiofiles

from src.server.core.config import settings

logger = logging.getLogger("nyxcore.iso_storage")


def _complete_dir() -> Path:
    p = settings.iso_path / "complete"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _staging_dir(upload_id: str) -> Path:
    p = settings.iso_path / "staging" / upload_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _chunk_path(upload_id: str, chunk_index: int) -> Path:
    return _staging_dir(upload_id) / f"{chunk_index:06d}"


# ── Write ─────────────────────────────────────────────────────────────────────


async def save_chunk(upload_id: str, chunk_index: int, data: bytes) -> None:
    path = _chunk_path(upload_id, chunk_index)
    async with aiofiles.open(path, "wb") as f:
        await f.write(data)
    logger.debug(f"Chunk {chunk_index} saved for {upload_id} ({len(data)} bytes)")


def chunk_exists(upload_id: str, chunk_index: int) -> bool:
    return _chunk_path(upload_id, chunk_index).exists()


async def assemble_chunks(
    upload_id: str,
    filename: str,
    total_chunks: int,
    expected_sha256: str | None = None,
) -> tuple[Path, str]:
    """
    Concatenate all chunks in order → complete ISO file.
    Verifies SHA-256 if expected_sha256 is provided.
    Returns (dest_path, actual_sha256).
    Raises ValueError on checksum mismatch.
    """
    dest = _complete_dir() / filename
    sha = hashlib.sha256()

    async with aiofiles.open(dest, "wb") as out:
        for i in range(total_chunks):
            chunk_path = _chunk_path(upload_id, i)
            if not chunk_path.exists():
                raise FileNotFoundError(f"Missing chunk {i} for upload {upload_id}")
            async with aiofiles.open(chunk_path, "rb") as f:
                while block := await f.read(1024 * 1024):
                    await out.write(block)
                    sha.update(block)

    actual = sha.hexdigest()
    if expected_sha256 and actual != expected_sha256.lower():
        dest.unlink(missing_ok=True)
        raise ValueError(f"SHA-256 mismatch: expected {expected_sha256}, got {actual}")

    # Clean up staging
    cleanup_staging(upload_id)
    logger.info(f"Assembled {filename} ({total_chunks} chunks) sha256={actual}")
    return dest, actual


def cleanup_staging(upload_id: str) -> None:
    staging = settings.iso_path / "staging" / upload_id
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)


# ── Read ──────────────────────────────────────────────────────────────────────


def complete_path(filename: str) -> Path:
    return _complete_dir() / filename


def list_complete() -> list[dict]:
    files = []
    for f in _complete_dir().iterdir():
        if f.is_file():
            stat = f.stat()
            files.append(
                {
                    "file_name": f.name,
                    "file_size": stat.st_size,
                    "mtime": stat.st_mtime,
                }
            )
    return sorted(files, key=lambda x: x["mtime"], reverse=True)


def delete_iso(filename: str) -> int:
    """Delete a complete ISO. Returns file size before deletion."""
    p = complete_path(filename)
    size = p.stat().st_size
    p.unlink()
    return size
