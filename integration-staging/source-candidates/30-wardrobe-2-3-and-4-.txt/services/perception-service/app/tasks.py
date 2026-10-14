"""Celery worker tasks for async image analysis."""
from __future__ import annotations

import asyncio
import logging

from celery import Celery

from common.config import settings
from common.events import EventPublisher

from .perception import CLIPPerception

logger = logging.getLogger(__name__)

celery_app = Celery(
    "perception",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=300,
    task_soft_time_limit=240,
)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, name="perception.analyze")
def analyze_image(self, item_id: str, image_url: str, category_hint: str | None = None) -> dict:
    try:
        model = CLIPPerception()
        geometry, surface, embedding = asyncio.run(model.analyze(image_url, category_hint))

        async def _emit() -> None:
            await EventPublisher.init()
            await EventPublisher.publish(
                "perception.completed",
                {
                    "item_id": item_id,
                    "geometry": geometry,
                    "surface": surface,
                    "embedding": embedding,
                },
            )
            await EventPublisher.close()

        asyncio.run(_emit())
        logger.info(f"Perception completed for {item_id}")
        return {"item_id": item_id, "status": "done"}
    except Exception as exc:
        logger.exception(f"Perception failed for {item_id}")
        raise self.retry(exc=exc)
