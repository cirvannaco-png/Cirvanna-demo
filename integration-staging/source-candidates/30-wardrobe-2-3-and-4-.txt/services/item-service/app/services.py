"""Item service business logic."""
from __future__ import annotations

import logging
import uuid

from common.cache import RedisCache
from common.domain import (
    ColorVector,
    EventType,
    GeometryProfile,
    IngestionMethod,
    PrimaryCategory,
    SilhouetteClass,
    SurfaceProperties,
    TextureClass,
    WardrobeObject,
)
from common.errors import NotFoundError, ValidationError
from common.events import EventPublisher

from .config import CACHE_TTL_SECONDS
from .models import (
    GeometryData,
    ItemCreate,
    ItemRow,
    ItemSummary,
    SurfaceData,
    WearEventRow,
    WearRequest,
)
from .repositories import ItemRepository, WearRepository

logger = logging.getLogger(__name__)


class ItemService:
    """Orchestrates domain objects, persistence, cache, and events."""

    def __init__(self, item_repo: ItemRepository, wear_repo: WearRepository) -> None:
        self.items = item_repo
        self.wears = wear_repo

    # ─────────────────────────────────────────────────────────────
    # Create
    # ─────────────────────────────────────────────────────────────
    async def create(self, payload: ItemCreate) -> WardrobeObject:
        domain = WardrobeObject(
            owner_id=payload.owner_id,
            ingestion_method=IngestionMethod(payload.ingestion_method),
            primary_category=PrimaryCategory(payload.primary_category),
            bootstrap_confidence=payload.bootstrap_confidence,
        )

        if payload.geometry_data:
            domain.geometry_profile = self._build_geometry(payload.geometry_data)
        if payload.surface_data:
            domain.surface_properties = self._build_surface(payload.surface_data)
        if payload.catalog_metadata:
            domain.catalog_metadata = payload.catalog_metadata

        row = ItemRow.from_domain(domain)
        await self.items.insert(row)

        await EventPublisher.publish(
            "item.created",
            {
                "item_id": domain.id,
                "owner_id": domain.owner_id,
                "primary_category": domain.category_constraints["primary_category"],
            },
        )
        logger.info(f"Created item {domain.id} for owner {domain.owner_id}")
        return domain

    # ─────────────────────────────────────────────────────────────
    # Read
    # ─────────────────────────────────────────────────────────────
    async def get(self, item_id: str, *, use_cache: bool = True) -> WardrobeObject:
        cache_key = f"item:{item_id}"
        if use_cache:
            cached = await RedisCache.get_json(cache_key)
            if cached:
                return WardrobeObject.from_dict(cached)

        row = await self.items.get(item_id)
        if row is None:
            raise NotFoundError(f"Item {item_id} not found")

        domain = row.to_domain()
        if use_cache:
            await RedisCache.set_json(cache_key, domain.to_dict(), ttl=CACHE_TTL_SECONDS)
        return domain

    async def list_for_owner(
        self,
        owner_id: str,
        skip: int = 0,
        limit: int = 20,
        category: str | None = None,
    ) -> tuple[list[ItemSummary], int]:
        rows = await self.items.list_by_owner(owner_id, skip, limit, category)
        total = await self.items.count_by_owner(owner_id, category)
        summaries = [
            ItemSummary(
                id=r.id,
                owner_id=r.owner_id,
                primary_category=r.primary_category,
                lifecycle_state=r.lifecycle_state,
                confidence=r.confidence_envelope.get("geometry_confidence", 0.0),
                total_wears=r.total_wears,
                last_worn=r.last_worn,
            )
            for r in rows
        ]
        return summaries, total

    # ─────────────────────────────────────────────────────────────
    # Update
    # ─────────────────────────────────────────────────────────────
    async def record_wear(self, item_id: str, payload: WearRequest) -> WardrobeObject:
        row = await self.items.get(item_id)
        if row is None:
            raise NotFoundError(f"Item {item_id} not found")

        domain = row.to_domain()

        # Atomic domain mutation
        domain.record_wear_event(
            accepted=payload.accepted,
            duration_estimate=payload.duration_minutes,
            event_type=EventType(payload.event_type),
            context_snapshot_id=str(uuid.uuid4()),
        )

        # Persist updated aggregate
        await self.items.update(ItemRow.from_domain(domain))

        # Persist event log
        await self.wears.insert(
            WearEventRow(
                item_id=item_id,
                owner_id=row.owner_id,
                accepted=payload.accepted,
                duration_minutes=payload.duration_minutes,
                event_type=payload.event_type,
                context_snapshot=payload.context_snapshot,
            )
        )

        await RedisCache.delete(f"item:{item_id}")
        await EventPublisher.publish(
            "wear.recorded",
            {
                "item_id": item_id,
                "owner_id": row.owner_id,
                "accepted": payload.accepted,
                "duration_minutes": payload.duration_minutes,
                "event_type": payload.event_type,
            },
        )
        logger.info(f"Recorded {payload.event_type} for {item_id} accepted={payload.accepted}")
        return domain

    async def retire(self, item_id: str) -> None:
        row = await self.items.get(item_id)
        if row is None:
            raise NotFoundError(f"Item {item_id} not found")
        domain = row.to_domain()
        domain.retire()
        await self.items.update(ItemRow.from_domain(domain))
        await RedisCache.delete(f"item:{item_id}")
        await EventPublisher.publish("item.retired", {"item_id": item_id})

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def _build_geometry(data: GeometryData) -> GeometryProfile:
        try:
            return GeometryProfile(
                silhouette_class=SilhouetteClass(data.silhouette_class),
                length_profile=data.length_profile,
                volume_distribution=data.volume_distribution,
                stretch_behavior=data.stretch_behavior,
            )
        except (ValueError, KeyError) as exc:
            raise ValidationError(f"Invalid geometry data: {exc}")

    @staticmethod
    def _build_surface(data: SurfaceData) -> SurfaceProperties:
        try:
            return SurfaceProperties(
                dominant_color=ColorVector.from_dict(data.dominant_color),
                color_variance=data.color_variance,
                texture_class=TextureClass(data.texture_class),
                pattern_density=data.pattern_density,
                lighting_risk=data.lighting_risk,
            )
        except (ValueError, KeyError) as exc:
            raise ValidationError(f"Invalid surface data: {exc}")
