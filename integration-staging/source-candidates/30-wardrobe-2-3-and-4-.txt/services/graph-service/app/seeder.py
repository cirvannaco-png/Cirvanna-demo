"""Seeds and incrementally updates graph edges from item data."""
from __future__ import annotations

import asyncio
import logging

import httpx

from common.domain import (
    PrimaryCategory,
    WardrobeObject,
    categories_are_compatible,
    rule_based_compatibility,
)

from .config import ITEM_SERVICE_URL
from .repository import GraphRepository

logger = logging.getLogger(__name__)


class GraphSeeder:
    def __init__(self, repo: GraphRepository) -> None:
        self.repo = repo

    async def seed_from_items(self, items: list[WardrobeObject]) -> int:
        for it in items:
            await self.repo.upsert_item(
                it.id, it.owner_id, it.category_constraints["primary_category"]
            )

        coros = []
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if categories_are_compatible(a, b):
                    w = rule_based_compatibility(a, b)
                    coros.append(self.repo.create_edge(a.id, b.id, w, 0.15))
                    coros.append(self.repo.create_edge(b.id, a.id, w, 0.15))
        if coros:
            await asyncio.gather(*coros)
        logger.info(f"Seeded edges for {len(items)} items ({len(coros)} edges)")
        return len(coros)

    async def update_for_item(self, item_id: str) -> int:
        """Recompute edges for one item against its owner's other items."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{ITEM_SERVICE_URL}/items/{item_id}")
            if r.status_code != 200:
                logger.warning(f"Item {item_id} not found for edge update")
                return 0
            item = WardrobeObject.from_dict(r.json())

            r = await client.get(
                f"{ITEM_SERVICE_URL}/items",
                params={"skip": 0, "limit": 500},
            )
            r.raise_for_status()
            others = [
                WardrobeObject.from_dict(x)
                for x in r.json()["items"]
                if x["id"] != item_id
            ]

        await self.repo.upsert_item(
            item.id, item.owner_id, item.category_constraints["primary_category"]
        )

        coros = []
        for o in others:
            if categories_are_compatible(item, o):
                w = rule_based_compatibility(item, o)
                coros.append(self.repo.create_edge(item.id, o.id, w, 0.3))
                coros.append(self.repo.create_edge(o.id, item.id, w, 0.3))
        if coros:
            await asyncio.gather(*coros)
        logger.info(f"Updated {len(coros)} edges for item {item_id}")
        return len(coros)
