# 🌑 NyxCore v1.0.0

**ISO / OS HUB Platform** — License management, user control, machine tracking, secure ISO distribution.

[![CI/CD](https://github.com/yolezz/nyxcore/actions/workflows/ci.yml/badge.svg)](https://github.com/yolezz/nyxcore/actions)

---

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/yo-le-zz/NyxCore.git
cd NyxCore
uv sync

# 2. Configure
cp .env.example .env
# Edit .env — set SECRET_KEY and MASTER_PASSWORD

# 3. Run server
uv run python main.py
# or
uv run nyxcore-server --port 8000
```

Server starts on `http://localhost:8000`

---

## Admin Web Panel

> **URL : `http://localhost:8000/admin/`**
> Password = `MASTER_PASSWORD` from your `.env`

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | `/admin/` | Stats, disk usage, recent transfers |
| Users | `/admin/users` | List users, enable/disable accounts |
| **Licenses** | `/admin/licenses` | **Create licenses here** ← |
| Machines | `/admin/machines` | List machines, ban/unban |
| ISOs | `/admin/isos` | Browse ISO repository |

### First-time setup

1. Go to `http://localhost:8000/admin/`  → redirects to `/admin/login`
2. Enter your `MASTER_PASSWORD` (default: `change_me_in_env` if not set in `.env`)
3. Go to **Licenses** → fill in Owner + Machine Limit → click **Generate License**
4. Copy the license key → give it to your user
5. User registers via the client or `POST /api/v1/auth/register`

---

## Client

```bash
uv run nyxcore-client
# or
uv run python src/client/main.py
```

---

## REST API

All API endpoints are prefixed with `/api/v1`.

### Auth

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/register` | — | Register (requires valid license key) |
| POST | `/api/v1/auth/login` | — | Login → JWT tokens |
| POST | `/api/v1/auth/refresh` | — | Rotate refresh token |
| POST | `/api/v1/auth/logout` | Bearer | Revoke all sessions |
| GET | `/api/v1/auth/me` | Bearer | Current user info |

### Licenses

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/licenses/` | Admin | Create license |
| GET | `/api/v1/licenses/` | Admin | List all licenses |
| GET | `/api/v1/licenses/{id}` | Admin | Get one license |
| PATCH | `/api/v1/licenses/{id}` | Admin | Update owner / limit |
| POST | `/api/v1/licenses/revoke` | Admin | Revoke license |
| POST | `/api/v1/licenses/{id}/restore` | Admin | Restore revoked license |
| DELETE | `/api/v1/licenses/{id}` | Admin | Delete license |
| GET | `/api/v1/licenses/check/{key}` | Bearer | Check a key |
| GET | `/api/v1/licenses/my` | Bearer | My license info |

### Machines

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/machines/register` | Bearer | Register / heartbeat |
| GET | `/api/v1/machines/` | Bearer | My machines |
| GET | `/api/v1/machines/{id}` | Bearer | One machine |
| DELETE | `/api/v1/machines/{id}` | Bearer | Unregister |
| GET | `/api/v1/machines/admin/all` | Admin | All machines |
| POST | `/api/v1/machines/admin/ban` | Admin | Ban machine |
| POST | `/api/v1/machines/admin/unban/{id}` | Admin | Unban machine |
| DELETE | `/api/v1/machines/admin/{id}` | Admin | Force delete |

### ISOs

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/isos/` | Bearer | List ISOs |
| POST | `/api/v1/isos/upload/init` | Bearer | Init chunked upload |
| PUT | `/api/v1/isos/upload/{id}/chunk/{n}` | Bearer | Upload chunk |
| GET | `/api/v1/isos/upload/{id}/status` | Bearer | Missing chunks (resume) |
| POST | `/api/v1/isos/upload/{id}/complete` | Bearer | Assemble + verify |
| GET | `/api/v1/isos/download/{filename}` | Bearer | Download (Range supported) |
| DELETE | `/api/v1/isos/{filename}` | Bearer | Delete ISO |
| GET | `/api/v1/isos/history` | Bearer | My transfer history |

### Admin REST

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/admin/api/stats` | Admin | Platform stats |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | DB ping, disk, uptime |
| GET | `/api/v1/info` | App version info |

> **Admin auth** = `Authorization: Bearer <MASTER_PASSWORD>`

---

## Architecture

```
NyxCore/
├── src/
│   ├── server/
│   │   ├── main.py                   FastAPI app entry point
│   │   ├── core/
│   │   │   ├── config.py             Settings (.env)
│   │   │   ├── database.py           SQLAlchemy async (SQLite / PostgreSQL)
│   │   │   └── security.py           JWT, SHA-512, token rotation
│   │   ├── models/                   SQLAlchemy ORM models
│   │   ├── routers/                  FastAPI routers (auth/licenses/machines/isos/admin/health)
│   │   ├── services/                 Schemas + ISO storage backend
│   │   ├── middleware/               Rate limiter + security headers
│   │   └── templates/admin/          Jinja2 HTML admin panel
│   └── client/
│       ├── main.py                   PySide6 entry point
│       ├── ui/                       auth_dialog, main_window, server_dialog
│       ├── services/                 API client + QThread workers
│       └── utils/                    hardware ID, session store
├── tests/server/test_api.py          15 tests
├── alembic/                          DB migrations
├── .github/workflows/ci.yml          CI + build + release
└── scripts/                          build_deb.sh, build_msi.sh
```

---

## Configuration (.env)

```env
SECRET_KEY=<64 random chars>
MASTER_PASSWORD=<strong password>
PORT=8000
HOST=0.0.0.0

# Database (default: SQLite)
DB_BACKEND=sqlite
# For PostgreSQL:
# DB_BACKEND=postgresql
# PG_HOST=localhost
# PG_USER=nyxcore
# PG_PASSWORD=changeme
# PG_DATABASE=nyxcore

ISO_STORAGE_PATH=./isos
MAX_UPLOAD_SIZE_MB=8192
DISK_ALERT_THRESHOLD_PCT=90
DEBUG=false
```

---

## Development

```bash
uv run pytest tests/ -v          # run tests
uv run ruff check src/           # lint
uv run alembic upgrade head      # run migrations (PostgreSQL)
```

---

## License

MIT © yolezz
