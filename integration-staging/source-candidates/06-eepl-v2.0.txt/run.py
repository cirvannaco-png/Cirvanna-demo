# run.py
import asyncio
import logging
import os
import numpy as np
from datetime import datetime
from uuid import UUID

import asyncpg

from config.config import config
from src.core.domain.entities import UserProfile, Vector, Item, ItemFeatures
from src.core.eepl import EEPL
from src.core.ports.cfrp_client import CFRPClient
from src.infrastructure.database.postgres_repository import (
    PostgreSQLUserRepository,
    PostgreSQLItemRepository,
    PostgreSQLSegmentPriorRepository,
    PostgreSQLStyleSnapshotRepository,
)
from src.infrastructure.external.climate_service import ClimateService
from src.infrastructure.external.virtual_twin_service import VirtualTwinService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StubCFRPClient(CFRPClient):
    async def predict(self, user_id: UUID, item_id: UUID, context: dict) -> float:
        import hashlib
        hash_val = int(hashlib.md5(str(item_id).encode()).hexdigest(), 16)
        return (hash_val % 100) / 100.0

    async def record_feedback(self, event) -> None:
        logger.info(f"Recording feedback: {event}")


async def main():
    dsn = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/eepl")
    pool = await asyncpg.create_pool(dsn, min_size=5, max_size=20)

    try:
        user_repo = PostgreSQLUserRepository(pool)
        item_repo = PostgreSQLItemRepository(pool)
        segment_repo = PostgreSQLSegmentPriorRepository(pool)
        snapshot_repo = PostgreSQLStyleSnapshotRepository(pool)

        climate_service = ClimateService()
        vt_service = VirtualTwinService(item_repo=item_repo)

        cfrp_client = StubCFRPClient()

        eepl = EEPL(
            user_repo=user_repo,
            item_repo=item_repo,
            segment_repo=segment_repo,
            snapshot_repo=snapshot_repo,
            climate_service=climate_service,
            virtual_twin=vt_service,
            cfrp_client=cfrp_client,
        )

        user_id = UUID("12345678-1234-1234-1234-123456789abc")
        user = await user_repo.get_user(user_id)
        if not user:
            logger.warning(f"User {user_id} not found, creating dummy user.")
            dummy_user = UserProfile(
                user_id=user_id,
                style_vector=Vector(values=np.random.randn(config.vector_dimensions).astype(np.float32)),
                archetype="casual",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                negative_preferences=set(),
                cultural_constraints={},
                location={"lat": 40.0, "lon": -74.0},
                style_history=[],
                engagement_rate=0.5,
                exploration_rate=0.5,
            )
            await user_repo.save_user(dummy_user)
            user = dummy_user

        candidate_items = await item_repo.get_trending_items(limit=10)
        if not candidate_items:
            logger.warning("No items found in DB; creating dummy items.")
            candidate_items = []
            for i in range(5):
                item = Item(
                    item_id=UUID(int=i+1),
                    category="top",
                    features=ItemFeatures(
                        color="blue",
                        material="cotton",
                        style_tags=["casual"],
                        thermal_rating=0.6,
                        water_resistance=0.1,
                        uv_protection=0.3,
                    ),
                    embedding=Vector(values=np.random.randn(config.vector_dimensions).astype(np.float32)),
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    confidence=0.8,
                )
                candidate_items.append(item)

        context = {
            "location": user.location or {"lat": 40.0, "lon": -74.0},
            "season": "summer",
            "cultural_profile": user.cultural_constraints,
        }

        logger.info("Calling EEPL.process...")
        ranked_items = await eepl.process(user_id, candidate_items, context)

        logger.info("Ranked items (top 5):")
        for idx, item in enumerate(ranked_items[:5]):
            logger.info(f"{idx+1}. {item.item_id} - category: {item.category}")

    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
