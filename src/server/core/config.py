"""NyxCore — centralised settings (pydantic-settings)."""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import ClassVar, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config: ClassVar = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── General ───────────────────────────────────────────────────────────────
    APP_NAME: str = "NyxCore"
    VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Network ───────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: list[str] = ["*"]

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = secrets.token_urlsafe(64)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15      # short-lived access tokens
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    MASTER_PASSWORD: str = "change_me_in_env"

    # ── Database ──────────────────────────────────────────────────────────────
    # Switch between backends via DB_BACKEND env var:
    #   sqlite     → sqlite+aiosqlite:///./nyxcore.db   (dev/test)
    #   postgresql → postgresql+asyncpg://user:pass@host/db  (production)
    DB_BACKEND: Literal["sqlite", "postgresql"] = "sqlite"

    # Individual PG params (ignored when DB_BACKEND=sqlite)
    PG_HOST: str = "localhost"
    PG_PORT: int = 5432
    PG_USER: str = "nyxcore"
    PG_PASSWORD: str = "changeme"
    PG_DATABASE: str = "nyxcore"

    # PG pool settings
    PG_POOL_SIZE: int = 20
    PG_MAX_OVERFLOW: int = 10
    PG_POOL_TIMEOUT: int = 30
    PG_POOL_RECYCLE: int = 1800   # recycle connections every 30 min

    # Override entire URL (takes precedence over individual params)
    DATABASE_URL: str = ""

    # ── Storage ───────────────────────────────────────────────────────────────
    ISO_STORAGE_PATH: str = "./isos"
    ISO_CHUNK_SIZE_MB: int = 8              # chunk size for resumable uploads
    MAX_UPLOAD_SIZE_MB: int = 8192
    DISK_ALERT_THRESHOLD_PCT: float = 90.0

    @property
    def effective_database_url(self) -> str:
        """Resolve the actual async DB URL from config."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.DB_BACKEND == "postgresql":
            return (
                f"postgresql+asyncpg://{self.PG_USER}:{self.PG_PASSWORD}"
                f"@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DATABASE}"
            )
        return "sqlite+aiosqlite:///./nyxcore.db"

    @property
    def sync_database_url(self) -> str:
        """Synchronous URL for Alembic migrations."""
        url = self.effective_database_url
        # asyncpg → psycopg2, aiosqlite → pysqlite
        return (
            url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
               .replace("sqlite+aiosqlite://", "sqlite://")
        )

    @property
    def is_postgres(self) -> bool:
        return "postgresql" in self.effective_database_url

    @property
    def iso_path(self) -> Path:
        p = Path(self.ISO_STORAGE_PATH)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def chunk_size_bytes(self) -> int:
        return self.ISO_CHUNK_SIZE_MB * 1024 * 1024

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


settings = Settings()
