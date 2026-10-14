# src/infrastructure/external/feedback_repository.py
import asyncpg
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta
import json

from src.core.ports.repository import FeedbackRepository
from src.core.domain.entities import FeedbackEvent

class PostgreSQLFeedbackRepository(FeedbackRepository):
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def save_feedback(self, event: FeedbackEvent) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO feedback_events (event_id, user_id, item_id, event_type, timestamp, context,
                                             recency_weight, engagement_weight, effective_weight)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                str(event.event_id), str(event.user_id), str(event.item_id),
                event.event_type, event.timestamp, json.dumps(event.context),
                event.recency_weight, event.engagement_weight, event.effective_weight
            )

    async def get_recent_for_item(self, user_id: UUID, item_id: UUID, minutes: int) -> List[FeedbackEvent]:
        cutoff = datetime.now() - timedelta(minutes=minutes)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT event_id, user_id, item_id, event_type, timestamp, context,
                       recency_weight, engagement_weight, effective_weight
                FROM feedback_events
                WHERE user_id = $1 AND item_id = $2 AND timestamp > $3
                ORDER BY timestamp DESC
                """,
                str(user_id), str(item_id), cutoff
            )
            return [
                FeedbackEvent(
                    event_id=UUID(row['event_id']),
                    user_id=UUID(row['user_id']),
                    item_id=UUID(row['item_id']),
                    event_type=row['event_type'],
                    timestamp=row['timestamp'],
                    context=json.loads(row['context']),
                    recency_weight=row['recency_weight'],
                    engagement_weight=row['engagement_weight'],
                    effective_weight=row['effective_weight']
                )
                for row in rows
            ]
