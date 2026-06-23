"""Server integration tests — covers security, token rotation, chunked ISO upload."""
from __future__ import annotations

import io
import hashlib
import pytest
from httpx import ASGITransport, AsyncClient

from src.server.main import app
from src.server.core.database import engine, Base
from src.server.core.config import settings


import asyncio
import pytest

from src.server.core.database import engine, Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def admin_headers():
    return {"Authorization": f"Bearer {settings.MASTER_PASSWORD}"}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _create_license(client, admin_headers) -> str:
    r = await client.post("/api/v1/licenses/", json={"machines_limit": 3}, headers=admin_headers)
    assert r.status_code == 201
    return r.json()["key"]


async def _register_and_login(client, admin_headers, username="alice") -> tuple[dict, str]:
    key = await _create_license(client, admin_headers)
    await client.post("/api/v1/auth/register", json={
        "username": username, "password": "SecurePass1", "license_key": key,
    })
    r = await client.post("/api/v1/auth/login", json={
        "username": username, "password": "SecurePass1",
    })
    return r.json(), key


# ── Health ────────────────────────────────────────────────────────────────────

async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Auth — basic flow ─────────────────────────────────────────────────────────

async def test_register_requires_license(client):
    r = await client.post("/api/v1/auth/register", json={
        "username": "bob", "password": "Password1", "license_key": "fake-key",
    })
    assert r.status_code == 400


async def test_full_auth_flow(client, admin_headers):
    tokens, _ = await _register_and_login(client, admin_headers)
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    auth = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = await client.get("/api/v1/auth/me", headers=auth)
    assert r.status_code == 200
    assert r.json()["username"] == "alice"


async def test_duplicate_username(client, admin_headers):
    key = await _create_license(client, admin_headers)
    payload = {"username": "charlie", "password": "Password1", "license_key": key}
    await client.post("/api/v1/auth/register", json=payload)
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 409


async def test_wrong_password(client, admin_headers):
    await _register_and_login(client, admin_headers, "dave")
    r = await client.post("/api/v1/auth/login", json={"username": "dave", "password": "wrong"})
    assert r.status_code == 401


# ── Security — token rotation & reuse detection ───────────────────────────────

async def test_token_rotation(client, admin_headers):
    """Each refresh should return a NEW pair and invalidate the old refresh token."""
    tokens, _ = await _register_and_login(client, admin_headers)
    old_refresh = tokens["refresh_token"]

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 200
    new_tokens = r.json()
    assert new_tokens["refresh_token"] != old_refresh

    # Old refresh token must now be invalid (one-time use)
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 401
    assert "reuse" in r2.json()["detail"].lower() or r2.status_code == 401


async def test_refresh_reuse_revokes_all_sessions(client, admin_headers):
    """Presenting a revoked refresh token (token theft scenario) nukes all sessions."""
    tokens, _ = await _register_and_login(client, admin_headers, "eve")
    stolen_refresh = tokens["refresh_token"]

    # Legitimate rotation — stolen token is now revoked
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": stolen_refresh})
    assert r.status_code == 200
    legit_new = r.json()["refresh_token"]

    # Attacker replays the stolen (now revoked) token → all sessions nuked
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": stolen_refresh})
    assert r2.status_code == 401

    # The legitimate new token must now also be invalid (all sessions wiped)
    r3 = await client.post("/api/v1/auth/refresh", json={"refresh_token": legit_new})
    assert r3.status_code == 401


async def test_logout_invalidates_tokens(client, admin_headers):
    tokens, _ = await _register_and_login(client, admin_headers, "frank")
    auth = {"Authorization": f"Bearer {tokens['access_token']}"}

    r = await client.post("/api/v1/auth/logout", json={}, headers=auth)
    assert r.status_code == 204

    # Refresh token must now be revoked
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 401


async def test_access_token_not_accepted_as_refresh(client, admin_headers):
    tokens, _ = await _register_and_login(client, admin_headers, "grace")
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert r.status_code == 401


# ── Admin ─────────────────────────────────────────────────────────────────────

async def test_admin_stats(client, admin_headers):
    r = await client.get("/admin/api/stats", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert "total_users" in data
    assert "disk_used_pct" in data


async def test_admin_requires_auth(client):
    r = await client.get("/admin/api/stats")
    assert r.status_code in (401, 403)


# ── Chunked ISO upload ────────────────────────────────────────────────────────

async def test_chunked_upload_full_flow(client, admin_headers, tmp_path):
    tokens, _ = await _register_and_login(client, admin_headers, "heidi")
    auth = {"Authorization": f"Bearer {tokens['access_token']}"}

    # 3 MB synthetic file
    data = b"X" * (3 * 1024 * 1024)
    sha256 = hashlib.sha256(data).hexdigest()
    filename = "test.iso"

    # Init
    r = await client.post("/api/v1/isos/upload/init", json={
        "filename": filename,
        "total_size": len(data),
        "sha256": sha256,
    }, headers=auth)
    assert r.status_code == 201
    init = r.json()
    upload_id = init["upload_id"]
    chunk_size = init["chunk_size"]
    total_chunks = init["total_chunks"]

    # Upload each chunk
    for i in range(total_chunks):
        chunk = data[i * chunk_size: (i + 1) * chunk_size]
        r = await client.put(
            f"/api/v1/isos/upload/{upload_id}/chunk/{i}",
            content=chunk,
            headers={**auth, "Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 200

    # Status check
    r = await client.get(f"/api/v1/isos/upload/{upload_id}/status", headers=auth)
    assert r.status_code == 200
    assert r.json()["missing_chunks"] == []

    # Complete
    r = await client.post(f"/api/v1/isos/upload/{upload_id}/complete", headers=auth)
    assert r.status_code == 200
    result = r.json()
    assert result["sha256"] == sha256
    assert result["status"] == "complete"


async def test_chunked_upload_wrong_sha256(client, admin_headers):
    tokens, _ = await _register_and_login(client, admin_headers, "ivan")
    auth = {"Authorization": f"Bearer {tokens['access_token']}"}

    data = b"Y" * (1024 * 1024)

    r = await client.post("/api/v1/isos/upload/init", json={
        "filename": "bad.iso",
        "total_size": len(data),
        "sha256": "a" * 64,  # wrong checksum
    }, headers=auth)
    upload_id = r.json()["upload_id"]
    chunk_size = r.json()["chunk_size"]
    total_chunks = r.json()["total_chunks"]

    for i in range(total_chunks):
        chunk = data[i * chunk_size: (i + 1) * chunk_size]
        await client.put(
            f"/api/v1/isos/upload/{upload_id}/chunk/{i}",
            content=chunk,
            headers={**auth, "Content-Type": "application/octet-stream"},
        )

    r = await client.post(f"/api/v1/isos/upload/{upload_id}/complete", headers=auth)
    assert r.status_code == 422  # Unprocessable — checksum mismatch


async def test_download_range(client, admin_headers):
    """After a full upload, download with Range header should return 206."""
    tokens, _ = await _register_and_login(client, admin_headers, "judy")
    auth = {"Authorization": f"Bearer {tokens['access_token']}"}

    data = b"Z" * (2 * 1024 * 1024)
    sha256 = hashlib.sha256(data).hexdigest()

    r = await client.post("/api/v1/isos/upload/init", json={
        "filename": "range_test.iso", "total_size": len(data), "sha256": sha256,
    }, headers=auth)
    init = r.json()
    upload_id, chunk_size, total_chunks = init["upload_id"], init["chunk_size"], init["total_chunks"]

    for i in range(total_chunks):
        chunk = data[i * chunk_size: (i + 1) * chunk_size]
        await client.put(
            f"/api/v1/isos/upload/{upload_id}/chunk/{i}",
            content=chunk,
            headers={**auth, "Content-Type": "application/octet-stream"},
        )

    await client.post(f"/api/v1/isos/upload/{upload_id}/complete", headers=auth)

    # Range download
    r = await client.get(
        "/api/v1/isos/download/range_test.iso",
        headers={**auth, "Range": "bytes=0-1023"},
    )
    assert r.status_code == 206
    assert len(r.content) == 1024
    assert r.headers["content-range"].startswith("bytes 0-1023/")


async def test_rate_limit(client):
    hits_429 = 0
    for _ in range(65):
        r = await client.get("/api/v1/health")
        if r.status_code == 429:
            hits_429 += 1
    assert hits_429 > 0
