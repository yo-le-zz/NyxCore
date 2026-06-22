"""
NyxCore Client — HTTP API service.

Upload protocol: chunked resumable (init → PUT chunks → complete).
Download protocol: HTTP Range requests for resume.
Token protocol: access + refresh with automatic rotation + reuse-safe storage.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from pathlib import Path

import requests

ProgressCallback = Callable[[int, int], None]  # (bytes_done, bytes_total)


class APIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class NyxCoreAPI:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_lock = threading.Lock()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1{path}"

    def _auth_header(self) -> dict:
        if not self._access_token:
            raise APIError("Not authenticated")
        return {"Authorization": f"Bearer {self._access_token}"}

    def _handle(self, response: requests.Response) -> dict | list:
        if response.ok:
            try:
                return response.json()
            except Exception:
                return {}
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise APIError(str(detail), response.status_code)

    def _refresh_tokens(self) -> bool:
        """Attempt silent token rotation. Returns True on success."""
        with self._token_lock:
            if not self._refresh_token:
                return False
            try:
                resp = self._session.post(
                    self._url("/auth/refresh"),
                    json={"refresh_token": self._refresh_token},
                    timeout=10,
                )
                if resp.ok:
                    data = resp.json()
                    self._access_token = data["access_token"]
                    self._refresh_token = data["refresh_token"]
                    return True
            except Exception:
                pass
            return False

    def _get(self, path: str, **kwargs) -> dict | list:
        headers = {**self._auth_header(), **kwargs.pop("headers", {})}
        r = self._session.get(self._url(path), headers=headers, **kwargs)
        if r.status_code == 401 and self._refresh_tokens():
            headers = {**self._auth_header(), **kwargs.pop("headers", {})}
            r = self._session.get(self._url(path), headers=headers, **kwargs)
        return self._handle(r)

    def _post(self, path: str, json: dict | None = None, **kwargs) -> dict | list:
        headers = {**self._auth_header(), **kwargs.pop("headers", {})}
        r = self._session.post(self._url(path), json=json, headers=headers, **kwargs)
        if r.status_code == 401 and self._refresh_tokens():
            headers = {**self._auth_header()}
            r = self._session.post(self._url(path), json=json, headers=headers, **kwargs)
        return self._handle(r)

    def _put_raw(self, path: str, data: bytes) -> dict:
        headers = {**self._auth_header(), "Content-Type": "application/octet-stream"}
        r = self._session.put(self._url(path), data=data, headers=headers, timeout=(10, 120))
        if r.status_code == 401 and self._refresh_tokens():
            headers = {**self._auth_header(), "Content-Type": "application/octet-stream"}
            r = self._session.put(self._url(path), data=data, headers=headers, timeout=(10, 120))
        return self._handle(r)

    # ── Auth ──────────────────────────────────────────────────────────────────

    def health(self) -> dict:
        r = self._session.get(self._url("/health"), timeout=5)
        return self._handle(r)

    def login(self, username: str, password: str) -> dict:
        r = self._session.post(
            self._url("/auth/login"),
            json={"username": username, "password": password},
            timeout=10,
        )
        data = self._handle(r)
        self._access_token = data["access_token"]
        self._refresh_token = data["refresh_token"]
        return data

    def register(self, username: str, password: str, license_key: str) -> dict:
        r = self._session.post(
            self._url("/auth/register"),
            json={"username": username, "password": password, "license_key": license_key},
            timeout=10,
        )
        return self._handle(r)

    def me(self) -> dict:
        return self._get("/auth/me", timeout=10)

    def logout(self):
        try:
            self._post("/auth/logout", json={}, timeout=10)
        except Exception:
            pass
        self._access_token = None
        self._refresh_token = None

    # ── Machines ──────────────────────────────────────────────────────────────

    def register_machine(self, hardware_id: str, hostname: str, os_info: str) -> dict:
        return self._post(
            "/machines/register",
            {
                "hardware_id": hardware_id,
                "hostname": hostname,
                "os_info": os_info,
            },
            timeout=10,
        )

    # ── ISOs — list / history ─────────────────────────────────────────────────

    def list_isos(self) -> list[dict]:
        return self._get("/isos/", timeout=15)

    def upload_history(self) -> list[dict]:
        return self._get("/isos/history", timeout=15)

    # ── ISOs — chunked upload ─────────────────────────────────────────────────

    def upload_iso(
        self,
        file_path: str,
        progress_callback: ProgressCallback | None = None,
        resume: bool = True,
    ) -> dict:
        """
        Chunked resumable upload:
          1. Compute SHA-256 of file
          2. Init session on server
          3. Upload missing chunks (skip already received if resuming)
          4. Complete + verify

        resume=True: re-use existing upload_id stored alongside the file if available.
        """
        path = Path(file_path)
        total_size = path.stat().st_size

        # ── SHA-256 of full file (fast pre-check + server-side verification) ──
        sha256 = _sha256_file(
            path, lambda done, tot: progress_callback(done // 2, tot) if progress_callback else None
        )

        # ── Try to resume existing session ────────────────────────────────────
        upload_id: str | None = None
        session_file = path.parent / f".nyxcore_{path.name}.upload_id"
        if resume and session_file.exists():
            upload_id = session_file.read_text().strip()
            # Verify session still valid on server
            try:
                status = self._get(f"/isos/upload/{upload_id}/status", timeout=10)
                if status.get("status") == "complete":
                    session_file.unlink(missing_ok=True)
                    return {"file_name": path.name, "status": "already_complete"}
                missing_chunks = status.get("missing_chunks", [])
            except APIError:
                upload_id = None  # session expired, start fresh

        # ── Init new session ──────────────────────────────────────────────────
        if upload_id is None:
            init_resp = self._post(
                "/isos/upload/init",
                {
                    "filename": path.name,
                    "total_size": total_size,
                    "sha256": sha256,
                },
                timeout=15,
            )
            upload_id = init_resp["upload_id"]
            session_file.write_text(upload_id)
            chunk_size = init_resp["chunk_size"]
            total_chunks = init_resp["total_chunks"]
            missing_chunks = list(range(total_chunks))
        else:
            init_resp = self._post(
                "/isos/upload/init",
                {
                    "filename": path.name,
                    "total_size": total_size,
                    "sha256": sha256,
                },
                timeout=15,
            )
            chunk_size = init_resp["chunk_size"]
            total_chunks = init_resp["total_chunks"]

        # ── Upload missing chunks ─────────────────────────────────────────────
        sent_bytes = (total_chunks - len(missing_chunks)) * chunk_size
        half_total = total_size // 2  # second half of progress (first half = sha256)

        with open(path, "rb") as f:
            for idx in missing_chunks:
                offset = idx * chunk_size
                f.seek(offset)
                data = f.read(chunk_size)

                # Retry logic per chunk (network blip tolerance)
                for attempt in range(3):
                    try:
                        self._put_raw(f"/isos/upload/{upload_id}/chunk/{idx}", data)
                        break
                    except (requests.ConnectionError, requests.Timeout) as e:
                        if attempt == 2:
                            raise APIError(f"Chunk {idx} failed after 3 attempts: {e}")
                        time.sleep(2**attempt)

                sent_bytes += len(data)
                if progress_callback:
                    progress_callback(total_size // 2 + sent_bytes // 2, total_size)

        # ── Complete ──────────────────────────────────────────────────────────
        result = self._post(f"/isos/upload/{upload_id}/complete", timeout=120)
        session_file.unlink(missing_ok=True)
        return result

    # ── ISOs — ranged download (resumable) ───────────────────────────────────

    def download_iso(
        self,
        filename: str,
        dest_path: str,
        progress_callback: ProgressCallback | None = None,
    ) -> str:
        """
        Streaming download with HTTP Range support for resume.
        If dest_path already exists, resumes from current file size.
        """
        dest = Path(dest_path)
        existing = dest.stat().st_size if dest.exists() else 0

        headers = {**self._auth_header()}
        if existing > 0:
            headers["Range"] = f"bytes={existing}-"

        r = self._session.get(
            self._url(f"/isos/download/{filename}"),
            headers=headers,
            stream=True,
            timeout=(10, None),
        )

        if r.status_code == 416:
            # Range not satisfiable → file already complete
            return str(dest)
        if not r.ok:
            if r.status_code == 401 and self._refresh_tokens():
                return self.download_iso(filename, dest_path, progress_callback)
            raise APIError(r.text, r.status_code)

        total = int(r.headers.get("Content-Length", 0)) + existing
        received = existing
        mode = "ab" if existing > 0 and r.status_code == 206 else "wb"

        with open(dest, mode) as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                received += len(chunk)
                if progress_callback:
                    progress_callback(received, total)

        return str(dest)


# ── Utility ───────────────────────────────────────────────────────────────────


def _sha256_file(path: Path, progress_callback: ProgressCallback | None = None) -> str:
    sha = hashlib.sha256()
    total = path.stat().st_size
    done = 0
    with open(path, "rb") as f:
        while block := f.read(1024 * 1024):
            sha.update(block)
            done += len(block)
            if progress_callback:
                progress_callback(done, total)
    return sha.hexdigest()
