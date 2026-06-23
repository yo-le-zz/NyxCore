"""
ISO router — /api/v1/isos

Chunked resumable upload protocol:
  1. POST /isos/upload/init
       → { upload_id, chunk_size, total_chunks }
  2. PUT  /isos/upload/{upload_id}/chunk/{index}   (body = raw bytes, repeat per chunk)
       → { received, total_chunks, missing: [...] }
  3. POST /isos/upload/{upload_id}/complete
       → { file_name, file_size, sha256 }
  Cancel at any point before completion:
  DELETE /isos/upload/{upload_id}      → cleans up staging chunks + DB record

Resume: skip chunks where chunk_exists() returns True.
Client can query GET /isos/upload/{upload_id}/status to see which chunks are missing.

Download with HTTP Range:
  GET /isos/download/{filename}              → full file
  GET /isos/download/{filename} + Range header → partial content (resume)

Reporting an ISO (feature 5):
  POST /isos/{filename}/report  { description }
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime

import aiofiles
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.core.config import settings
from src.server.core.database import get_db
from src.server.core.security import get_current_user
from src.server.models.iso_chunk import ISOChunkUpload
from src.server.models.report import Report
from src.server.models.upload import Upload
from src.server.models.user import User
from src.server.services import iso_storage
from src.server.services.schemas import (
    CancelUploadResponse,
    ChunkStatus,
    ChunkUploadInit,
    ChunkUploadInitResponse,
    ISOOut,
    ReportCreate,
    ReportOut,
    UploadOut,
)

router = APIRouter()

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_\-\.]{1,200}$")


def _safe_filename(filename: str) -> str:
    if not _SAFE_NAME.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    # Extra guard: no path separators
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Path traversal detected")
    return filename


# ── List ──────────────────────────────────────────────────────────────────────


@router.get("/", response_model=list[ISOOut])
async def list_isos(_: User = Depends(get_current_user)):
    files = iso_storage.list_complete()
    return [
        ISOOut(
            file_name=f["file_name"],
            file_size=f["file_size"],
            uploaded_at=datetime.fromtimestamp(f["mtime"], tz=UTC),
        )
        for f in files
    ]


# ── Chunked upload — init ─────────────────────────────────────────────────────


@router.post(
    "/upload/init", response_model=ChunkUploadInitResponse, status_code=status.HTTP_201_CREATED
)
async def init_chunked_upload(
    body: ChunkUploadInit,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _safe_filename(body.filename)

    if body.total_size > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413, detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit"
        )

    chunk_size = settings.chunk_size_bytes
    total_chunks = max(1, -(-body.total_size // chunk_size))  # ceiling division

    upload_id = secrets.token_urlsafe(32)

    record = ISOChunkUpload(
        upload_id=upload_id,
        user_id=user.id,
        filename=body.filename,
        total_size=body.total_size,
        total_chunks=total_chunks,
        checksum_sha256=body.sha256,
        status="pending",
    )
    db.add(record)
    await db.flush()

    return ChunkUploadInitResponse(
        upload_id=upload_id,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
    )


# ── Chunked upload — PUT chunk ─────────────────────────────────────────────────


@router.put("/upload/{upload_id}/chunk/{chunk_index}", status_code=status.HTTP_200_OK)
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ISOChunkUpload).where(
            ISOChunkUpload.upload_id == upload_id,
            ISOChunkUpload.user_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if record.status == "cancelled":
        raise HTTPException(status_code=409, detail="Upload was cancelled")
    if record.status == "complete":
        raise HTTPException(status_code=409, detail="Upload already complete")
    if chunk_index < 0 or chunk_index >= record.total_chunks:
        raise HTTPException(
            status_code=400, detail=f"chunk_index must be 0..{record.total_chunks - 1}"
        )

    # Skip if chunk already received (idempotent — safe for retries)
    if iso_storage.chunk_exists(upload_id, chunk_index):
        missing = [
            i for i in range(record.total_chunks) if not iso_storage.chunk_exists(upload_id, i)
        ]
        return {
            "received": record.received_chunks,
            "total_chunks": record.total_chunks,
            "missing": missing,
        }

    # Read raw body
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Empty chunk body")
    if len(data) > settings.chunk_size_bytes * 2:  # 2× headroom for last chunk
        raise HTTPException(status_code=413, detail="Chunk too large")

    await iso_storage.save_chunk(upload_id, chunk_index, data)

    record.received_chunks += 1
    record.status = "uploading"
    record.updated_at = datetime.now(UTC)
    await db.flush()

    missing = [i for i in range(record.total_chunks) if not iso_storage.chunk_exists(upload_id, i)]

    return {
        "received": record.received_chunks,
        "total_chunks": record.total_chunks,
        "missing": missing,
    }


# ── Chunked upload — status (resume query) ────────────────────────────────────


@router.get("/upload/{upload_id}/status", response_model=ChunkStatus)
async def upload_status(
    upload_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ISOChunkUpload).where(
            ISOChunkUpload.upload_id == upload_id,
            ISOChunkUpload.user_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Upload session not found")

    received = [i for i in range(record.total_chunks) if iso_storage.chunk_exists(upload_id, i)]
    missing = [i for i in range(record.total_chunks) if i not in received]

    return ChunkStatus(
        upload_id=upload_id,
        filename=record.filename,
        status=record.status,
        total_chunks=record.total_chunks,
        received_chunks=len(received),
        missing_chunks=missing,
    )


# ── Chunked upload — cancel (feature 3) ────────────────────────────────────────


@router.delete("/upload/{upload_id}", response_model=CancelUploadResponse)
async def cancel_upload(
    upload_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Cancel an in-progress chunked upload.

    - Removes every staged chunk already received for this upload_id
    - Marks the DB record as "cancelled" (kept for a short audit trail rather
      than hard-deleted, but no longer resumable and not shown anywhere)
    - Safe to call even if the upload is already complete/cancelled (idempotent)
    """
    result = await db.execute(
        select(ISOChunkUpload).where(
            ISOChunkUpload.upload_id == upload_id,
            ISOChunkUpload.user_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Upload session not found")

    if record.status == "complete":
        raise HTTPException(status_code=409, detail="Cannot cancel a completed upload")

    iso_storage.cleanup_staging(upload_id)

    record.status = "cancelled"
    record.updated_at = datetime.now(UTC)
    await db.flush()

    return CancelUploadResponse(upload_id=upload_id, status="cancelled")


# ── Chunked upload — complete (assemble + verify) ─────────────────────────────


@router.post("/upload/{upload_id}/complete")
async def complete_upload(
    upload_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ISOChunkUpload).where(
            ISOChunkUpload.upload_id == upload_id,
            ISOChunkUpload.user_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if record.status == "cancelled":
        raise HTTPException(status_code=409, detail="Upload was cancelled")
    if record.status == "complete":
        return {"file_name": record.filename, "status": "already_complete"}

    # Verify all chunks present
    missing = [i for i in range(record.total_chunks) if not iso_storage.chunk_exists(upload_id, i)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing chunks: {missing[:20]}{'...' if len(missing) > 20 else ''}",
        )

    record.status = "assembling"
    record.updated_at = datetime.now(UTC)
    await db.flush()

    try:
        dest, actual_sha256 = await iso_storage.assemble_chunks(
            upload_id,
            record.filename,
            record.total_chunks,
            expected_sha256=record.checksum_sha256,
        )
    except ValueError as e:
        record.status = "failed"
        raise HTTPException(status_code=422, detail=str(e))
    except FileNotFoundError as e:
        record.status = "failed"
        raise HTTPException(status_code=400, detail=str(e))

    record.status = "complete"
    record.updated_at = datetime.now(UTC)

    file_size = dest.stat().st_size

    log = Upload(
        user_id=user.id,
        file_name=record.filename,
        file_size=file_size,
        action="upload",
    )
    db.add(log)

    # Separate upload/download counters (feature 1)
    user.total_uploads += 1
    user.total_upload_bytes += file_size

    await db.flush()

    return {
        "file_name": record.filename,
        "file_size": file_size,
        "sha256": actual_sha256,
        "status": "complete",
    }


# ── Download with HTTP Range support ─────────────────────────────────────────


@router.get("/download/{filename}")
async def download_iso(
    filename: str,
    range: str | None = Header(default=None, alias="Range"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _safe_filename(filename)
    path = iso_storage.complete_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="ISO not found")

    file_size = path.stat().st_size
    media_type = "application/octet-stream"

    # Only the initial request (no Range, or Range starting at 0) counts toward
    # the download counter — repeated Range requests during a resumed transfer
    # must not inflate "total_downloads".
    is_first_request = range is None or range.strip().startswith("bytes=0-")
    if is_first_request:
        log = Upload(user_id=user.id, file_name=filename, file_size=file_size, action="download")
        db.add(log)
        user.total_downloads += 1
        user.total_download_bytes += file_size
        await db.flush()

    # ── Range request (resume / seek) ─────────────────────────────────────────
    if range:
        start, end = _parse_range(range, file_size)
        length = end - start + 1

        async def _range_gen():
            async with aiofiles.open(path, "rb") as f:
                await f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = await f.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        return StreamingResponse(
            _range_gen(), status_code=206, headers=headers, media_type=media_type
        )

    # ── Full download ──────────────────────────────────────────────────────────
    async def _full_gen():
        async with aiofiles.open(path, "rb") as f:
            while chunk := await f.read(1024 * 1024):
                yield chunk

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    return StreamingResponse(_full_gen(), status_code=200, headers=headers, media_type=media_type)


def _parse_range(range_header: str, file_size: int) -> tuple[int, int]:
    """Parse 'bytes=start-end' header. Returns (start, end) inclusive."""
    try:
        unit, rng = range_header.split("=", 1)
        if unit.strip() != "bytes":
            raise ValueError
        start_s, end_s = rng.strip().split("-", 1)
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else file_size - 1
    except Exception:
        raise HTTPException(status_code=416, detail="Invalid Range header")

    if start > end or start < 0 or end >= file_size:
        raise HTTPException(
            status_code=416,
            detail=f"Range {start}-{end} out of bounds for file size {file_size}",
            headers={"Content-Range": f"bytes */{file_size}"},
        )
    return start, end


# ── Delete ────────────────────────────────────────────────────────────────────


@router.delete("/{filename}")
async def delete_iso(
    filename: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _safe_filename(filename)
    path = iso_storage.complete_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="ISO not found")

    size = iso_storage.delete_iso(filename)
    log = Upload(user_id=user.id, file_name=filename, file_size=size, action="delete")
    db.add(log)
    return {"detail": f"{filename} deleted"}


# ── History ───────────────────────────────────────────────────────────────────


@router.get("/history", response_model=list[UploadOut])
async def upload_history(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Upload).where(Upload.user_id == user.id).order_by(Upload.timestamp.desc()).limit(100)
    )
    return result.scalars().all()


# ── Reports (feature 5) ────────────────────────────────────────────────────────


@router.post("/{filename}/report", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def report_iso(
    filename: str,
    body: ReportCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _safe_filename(filename)
    if filename != body.file_name:
        raise HTTPException(status_code=400, detail="filename mismatch")

    path = iso_storage.complete_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="ISO not found")

    report = Report(
        file_name=filename,
        reporter_id=user.id,
        description=body.description,
    )
    db.add(report)
    await db.flush()
    return report
