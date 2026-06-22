# Changelog

All notable changes to NyxCore are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.0.0] — 2025-06-21

### Added

**Server**
- FastAPI + SQLAlchemy async backend on SQLite (aiosqlite)
- JWT authentication (HS256, 60-min access + 7-day refresh tokens)
- User registration gated behind valid license keys
- SHA-512 password hashing with per-user 32-byte random salt
- License system: create, revoke, check, expiry date support, per-license machine limits
- Machine tracking: hardware ID registration, ban/unban, heartbeat, per-machine IP logging
- ISO repository: streaming upload/download with 1 MB chunked I/O, path traversal guard
- Upload/download audit log (`uploads` table)
- Admin REST API protected by `MASTER_PASSWORD` env variable
- Disk usage monitor with configurable alert threshold (default 90 %)
- Rate limiting middleware: 60 req/min sliding window per IP
- Strict security headers: HSTS, X-Frame-Options, X-Content-Type-Options, Cache-Control
- Full input validation via Pydantic v2 on all endpoints
- Configurable port via `--port` CLI argument
- Health endpoint (`/api/v1/health`)

**Client**
- PySide6 GUI for Windows and Linux
- Server URL selection dialog with connectivity pre-check
- Login / Register with inline validation and clear error messages
- Session persistence (`~/.nyxcore/session.json`) with automatic token refresh
- Machine auto-registration on first login (hardware fingerprint via MAC + hostname hash)
- ISO listing, streaming upload, multi-threaded streaming download
- QThread-based workers for all network operations (non-blocking UI)
- Progress bar for uploads and downloads (byte-accurate)
- Logout with session clear

**Tooling & CI/CD**
- GitHub Actions: lint (ruff), pytest with coverage, auto PR dev → main
- Nuitka + PySide6 compilation: Linux standalone + Windows standalone
- `.deb` packaging with systemd unit for server
- `.msi` packaging via WiX Toolset
- Auto GitHub Release with version extracted from commit message
- Auto changelog generation from git log between tags
- `pyproject.toml` with Hatchling build backend, uv lock file

---

## [Unreleased]

- Web-based admin panel (Jinja2 templates)
- Two-factor authentication (TOTP)
- PostgreSQL support via env switch
- S3-compatible ISO backend
- CLI admin tool (`nyxcore-admin`)
