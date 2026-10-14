# src/infrastructure/external/cfrp_client.py
import aiohttp
import logging
from uuid import UUID
from typing import Dict, Any, Optional
from aiobreaker import CircuitBreaker
import mlflow

from src.core.ports.cfrp_client import CFRPClient
from src.core.domain.entities import FeedbackEvent
from config.config import config

logger = logging.getLogger(__name__)

class RealCFRPClient(CFRPClient):
    def __init__(self, session: aiohttp.ClientSession, model_uri: str = None):
        self.session = session
        self.base_url = config.cfrp_url
        self.cb = CircuitBreaker(
            failure_threshold=config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=config.CIRCUIT_BREAKER_RECOVERY_TIMEOUT
        )
        # Load model from MLflow if provided
        self.model = None
        if model_uri:
            self.model = mlflow.pyfunc.load_model(model_uri)

    async def predict(self, user_id: UUID, item_id: UUID, context: Dict[str, Any]) -> float:
        try:
            async with self.cb:
                async with self.session.post(f"{self.base_url}/predict", json={
                    "user_id": str(user_id),
                    "item_id": str(item_id),
                    "context": context
                }) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("score", 0.5)
                    else:
                        logger.warning(f"CFRP returned {resp.status}, using fallback")
                        return 0.5
        except Exception as e:
            logger.error(f"CFRP call failed: {e}")
            # Fallback: if model available locally
            if self.model:
                # Simulate prediction from local model
                return 0.5
            return 0.5

    async def record_feedback(self, event: FeedbackEvent) -> None:
        try:
            async with self.cb:
                await self.session.post(f"{self.base_url}/feedback", json=event.__dict__)
        except Exception as e:
            logger.error(f"Failed to send feedback: {e}")
