# src/core/ports/cfrp_client.py
from abc import ABC, abstractmethod
from uuid import UUID
from typing import Dict, Any
from src.core.domain.entities import FeedbackEvent

class CFRPClient(ABC):
    @abstractmethod
    async def predict(self, user_id: UUID, item_id: UUID, context: Dict[str, Any]) -> float:
        pass

    @abstractmethod
    async def record_feedback(self, event: FeedbackEvent) -> None:
        pass
