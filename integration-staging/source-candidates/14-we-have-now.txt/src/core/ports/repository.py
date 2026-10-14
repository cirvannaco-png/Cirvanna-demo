# src/core/ports/repository.py
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from uuid import UUID

from src.core.domain.entities import UserProfile, Item, FeedbackEvent, CulturalTrend, SegmentPrior, StyleSnapshot

class UserRepository(ABC):
    @abstractmethod
    async def get_user(self, user_id: UUID) -> Optional[UserProfile]:
        pass

    @abstractmethod
    async def save_user(self, user: UserProfile) -> None:
        pass

    @abstractmethod
    async def delete(self, entity_id: UUID) -> None:
        pass

    @abstractmethod
    async def get_users_by_archetype(self, archetype: str, limit: int = 100) -> List[UserProfile]:
        pass

    @abstractmethod
    async def update_user_vector(self, user_id: UUID, vector: Any) -> None:
        pass


class ItemRepository(ABC):
    @abstractmethod
    async def get_item(self, item_id: UUID) -> Optional[Item]:
        pass

    @abstractmethod
    async def save_item(self, item: Item) -> None:
        pass

    @abstractmethod
    async def delete(self, entity_id: UUID) -> None:
        pass

    @abstractmethod
    async def get_items_by_category(self, category: str, limit: int = 100) -> List[Item]:
        pass

    @abstractmethod
    async def find_similar_items(self, vector: Any, limit: int = 100) -> List[Item]:
        pass

    @abstractmethod
    async def get_trending_items(self, limit: int = 100) -> List[Item]:
        pass


class FeedbackRepository(ABC):
    @abstractmethod
    async def save_feedback(self, event: FeedbackEvent) -> None:
        pass

    @abstractmethod
    async def get_recent_for_item(self, user_id: UUID, item_id: UUID, minutes: int) -> List[FeedbackEvent]:
        pass


class TrendRepository(ABC):
    @abstractmethod
    async def get_current_trends(self, limit: int = 100) -> List[CulturalTrend]:
        pass


class SegmentPriorRepository(ABC):
    @abstractmethod
    async def get_prior(self, segment_id: str) -> Optional[SegmentPrior]:
        pass

    @abstractmethod
    async def update_prior(self, prior: SegmentPrior) -> None:
        pass

    @abstractmethod
    async def apply_inactivity_decay(self, days_threshold: int = 30, decay_factor: float = 0.95):
        pass


class StyleSnapshotRepository(ABC):
    @abstractmethod
    async def save(self, snapshot: StyleSnapshot) -> None:
        pass

    @abstractmethod
    async def get_for_user(self, user_id: UUID, limit: int = 52) -> List[StyleSnapshot]:
        pass
