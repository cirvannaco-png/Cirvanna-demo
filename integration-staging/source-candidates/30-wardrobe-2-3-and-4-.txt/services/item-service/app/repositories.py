"""Repository layer — the only place that touches the DB."""
from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ItemRow, WearEventRow

logger = logging.getLogger(__name__)


class ItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, row: ItemRow) -> ItemRow:
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, item_id: str) -> ItemRow | None:
        stmt = select(ItemRow).where(ItemRow.id == item_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_by_owner(
        self, owner_id: str, skip: int, limit: int, category: str | None = None
    ) -> Sequence[ItemRow]:
        stmt = select(ItemRow).where(ItemRow.owner_id == owner_id)
        if category:
            stmt = stmt.where(ItemRow.primary_category == category)
        stmt = stmt.order_by(ItemRow.created_at.desc()).offset(skip).limit(limit)
        return (await self.session.execute(stmt)).scalars().all()

    async def count_by_owner(self, owner_id: str, category: str | None = None) -> int:
        stmt = select(func.count(ItemRow.id)).where(ItemRow.owner_id == owner_id)
        if category:
            stmt = stmt.where(ItemRow.primary_category == category)
        return int((await self.session.execute(stmt)).scalar() or 0)

    async def update(self, row: ItemRow) -> ItemRow:
        merged = await self.session.merge(row)
        await self.session.flush()
        return merged

    async def delete(self, item_id: str) -> bool:
        stmt = delete(ItemRow).where(ItemRow.id == item_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def list_all_for_owner(self, owner_id: str) -> Sequence[ItemRow]:
        stmt = select(ItemRow).where(ItemRow.owner_id == owner_id)
        return (await self.session.execute(stmt)).scalars().all()

    async def increment_wear_counters(self, item_id: str, accepted: bool) -> None:
        stmt = (
            update(ItemRow)
            .where(ItemRow.id == item_id)
            .values(
                total_wears=ItemRow.total_wears + 1,
                successful_wears=ItemRow.successful_wears + (1 if accepted else 0),
                updated_at=func.now(),
            )
        )
        await self.session.execute(stmt)


class WearRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, row: WearEventRow) -> WearEventRow:
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_for_item(self, item_id: str, limit: int = 100) -> Sequence[WearEventRow]:
        stmt = (
            select(WearEventRow)
            .where(WearEventRow.item_id == item_id)
            .order_by(WearEventRow.timestamp.desc())
            .limit(limit)
        )
        return (await self.session.execute(stmt)).scalars().all()
