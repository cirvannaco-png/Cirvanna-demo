"""Async engine for the sync service's persistent queue."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from common.config import settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=5
        )
    return _engine


def get_factory() -> async_sessionmaker[AsyncSession]:
    global _factory
    if _factory is None:
        _factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    return _factory


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_factory()() as s:
        try:
            yield s
        except Exception:
            await s.rollback()
            raise


async def dispose() -> None:
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _factory = None
