"""Persistent offline queue with replay + retry semantics."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .config import BATCH_SIZE, MAX_RETRIES
from .models import OfflineEvent

logger = logging.getLogger(__name__)

Handler = Callable[[str, str, dict[str, Any]], Awaitable[None]]


class OfflineQueue:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(self, user_id: str, event_type: str, payload: dict[str, Any]) -> int:
        ev = OfflineEvent(user_id=user_id, event_type=event_type, payload=payload)
        self.session.add(ev)
        await self.session.flush()
        return ev.id

    async def pending(self, user_id: str, limit: int = BATCH_SIZE) -> list[OfflineEvent]:
        stmt = (
            select(OfflineEvent)
            .where(OfflineEvent.user_id == user_id, OfflineEvent.status == "pending")
            .order_by(OfflineEvent.created_at)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def mark_success(self, event_id: int) -> None:
        await self.session.execute(
            update(OfflineEvent)
            .where(OfflineEvent.id == event_id)
            .values(status="success")
        )
        await self.session.flush()

    async def mark_failure(self, event_id: int, error: str) -> None:
        stmt = select(OfflineEvent).where(OfflineEvent.id == event_id)
        ev = (await self.session.execute(stmt)).scalar_one_or_none()
        if ev is None:
            return
        ev.retry_count += 1
        ev.last_error = error[:1000]
        if ev.retry_count >= MAX_RETRIES:
            ev.status = "dead"
        await self.session.flush()

    async def replay(self, user_id: str, handler: Handler) -> dict[str, int]:
        events = await self.pending(user_id)
        stats = {"attempted": len(events), "succeeded": 0, "failed": 0}
        for ev in events:
            try:
                await handler(ev.user_id, ev.event_type, ev.payload)
                await self.mark_success(ev.id)
                stats["succeeded"] += 1
            except Exception as exc:
                logger.warning(f"Replay failed for event {ev.id}: {exc}")
                await self.mark_failure(ev.id, str(exc))
                stats["failed"] += 1
        await self.session.commit()
        return stats

    async def stats(self, user_id: str) -> dict[str, int]:
        from sqlalchemy import func as sqlfunc

        stmt = (
            select(OfflineEvent.status, sqlfunc.count(OfflineEvent.id))
            .where(OfflineEvent.user_id == user_id)
            .group_by(OfflineEvent.status)
        )
        rows = (await self.session.execute(stmt)).all()
        return {status: count for status, count in rows}
