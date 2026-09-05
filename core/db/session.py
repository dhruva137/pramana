"""Async SQLAlchemy engine — sqlite+aiosqlite (demo) and Postgres (Render)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.db.models import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def normalize_database_url(url: str) -> str:
    """Convert Render-style postgres URLs to SQLAlchemy async psycopg driver."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    return url


def get_database_url() -> str:
    raw = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./pramana.db")
    return normalize_database_url(raw)


def get_engine(*, url: str | None = None, echo: bool = False) -> AsyncEngine:
    global _engine, _session_factory
    if url is not None:
        # Explicit URL: always build a fresh engine (tests).
        eng = create_async_engine(normalize_database_url(url), echo=echo)
        return eng
    if _engine is None:
        db_url = get_database_url()
        kwargs: dict = {"echo": echo}
        if db_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_async_engine(db_url, **kwargs)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def async_session_factory(
    *, url: str | None = None, engine: AsyncEngine | None = None
) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if engine is not None:
        return async_sessionmaker(engine, expire_on_commit=False)
    if url is not None:
        eng = get_engine(url=url)
        return async_sessionmaker(eng, expire_on_commit=False)
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


async def init_db(*, engine: AsyncEngine | None = None) -> None:
    """create_all for hackathon reliability (no Alembic required on Render demo)."""
    eng = engine or get_engine()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session(
    *, factory: async_sessionmaker[AsyncSession] | None = None
) -> AsyncIterator[AsyncSession]:
    fac = factory or async_session_factory()
    async with fac() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def reset_engine() -> None:
    """Test helper — drop cached global engine."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
