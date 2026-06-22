"""Persistent session (server URL, token) stored in user config dir."""

from __future__ import annotations

import json
from pathlib import Path

_CONFIG_DIR = Path.home() / ".nyxcore"
_SESSION_FILE = _CONFIG_DIR / "session.json"


def save_session(server_url: str, access_token: str, refresh_token: str, username: str):
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _SESSION_FILE.write_text(
        json.dumps(
            {
                "server_url": server_url,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "username": username,
            }
        ),
        encoding="utf-8",
    )


def load_session() -> dict | None:
    if not _SESSION_FILE.exists():
        return None
    try:
        return json.loads(_SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def clear_session():
    _SESSION_FILE.unlink(missing_ok=True)
