# src/infrastructure/external/trend_service.py
import asyncio
from typing import List, Dict, Any
from datetime import datetime, timedelta
import logging

from src.core.domain.entities import Item
from src.infrastructure.database.postgres_repository import PostgreSQLItemRepository

logger = logging.getLogger(__name__)

class TrendService:
    def __init__(self, item_repo: PostgreSQLItemRepository):
        self.item_repo = item_repo
        self._trend_cache = {}
        self._last_update = None

    async def update_trend_scores(self):
        # Simulate computing trend scores from engagement data
        # In reality, would query feedback_events and compute
        items = await self.item_repo.get_trending_items(limit=1000)
        for item in items:
            # Dummy calculation: popularity based on views
            item.trend_score = 0.5 + 0.5 * (item.revival_score)  # placeholder
            await self.item_repo.save_item(item)
        self._last_update = datetime.now()
        logger.info("Updated trend scores")

    async def get_trending_items(self, limit: int = 100) -> List[Item]:
        # Refresh every hour
        if not self._last_update or (datetime.now() - self._last_update) > timedelta(hours=1):
            await self.update_trend_scores()
        return await self.item_repo.get_trending_items(limit)
