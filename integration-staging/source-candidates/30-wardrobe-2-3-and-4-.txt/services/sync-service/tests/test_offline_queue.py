from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base
from app.offline_queue import OfflineQueue


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_enqueue_and_replay(session: AsyncSession) -> None:
    q = OfflineQueue(session)
    await q.enqueue("u1", "wear_event", {"item_id": "1", "accepted": True, "duration_minutes": 60})
    await session.commit()
    assert len(await q.pending("u1")) == 1

    calls: list = []

    async def handler(uid, etype, payload):
        calls.append((uid, etype, payload))

    stats = await q.replay("u1", handler)
    assert stats == {"attempted": 1, "succeeded": 1, "failed": 0}
    assert calls[0][0] == "u1"
    assert len(await q.pending("u1")) == 0
