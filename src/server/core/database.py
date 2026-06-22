"""
Async SQLAlchemy engine + session factory.

Supports SQLite (dev/test) and PostgreSQL (production) via DB_BACKEND env.
PostgreSQL uses a tuned async connection pool (asyncpg).
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.server.core.config import settings

logger = logging.getLogger("nyxcore.db")


def _build_engine():
    url = settings.effective_database_url
    logger.info(
        f"Database backend: {settings.DB_BACKEND} — {url.split('@')[-1] if '@' in url else url}"
    )

    if settings.is_postgres:
        return create_async_engine(
            url,
            echo=settings.DEBUG,
            pool_size=settings.PG_POOL_SIZE,
            max_overflow=settings.PG_MAX_OVERFLOW,
            pool_timeout=settings.PG_POOL_TIMEOUT,
            pool_recycle=settings.PG_POOL_RECYCLE,
            pool_pre_ping=True,  # detect stale connections
        )
    else:
        # SQLite — single file, no pool needed
        return create_async_engine(
            url,
            echo=settings.DEBUG,
            connect_args={"check_same_thread": False},
        )


engine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Create all tables. Only used in dev/test (use Alembic in production)."""
    from src.server.models import license, machine, token, upload, user  # noqa: F401

    async with engine.begin() as conn:
        if not settings.is_postgres:
            # Enable WAL mode on SQLite for better concurrent reads
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialised")


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
