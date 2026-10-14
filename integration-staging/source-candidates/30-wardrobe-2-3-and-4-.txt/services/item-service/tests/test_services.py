"""Service-layer tests with mocked dependencies."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models import GeometryData, ItemCreate, SurfaceData, WearRequest
from app.repositories import ItemRepository, WearRepository
from app.services import ItemService


@pytest.fixture
def svc() -> ItemService:
    return ItemService(AsyncMock(spec=ItemRepository), AsyncMock(spec=WearRepository))


@pytest.mark.asyncio
async def test_create_item_publishes_event(svc: ItemService) -> None:
    svc.items.insert = AsyncMock(return_value=None)
    with patch("app.services.EventPublisher.publish", new=AsyncMock()) as pub:
        payload = ItemCreate(
            owner_id="u1", ingestion_method="manual", primary_category="top"
        )
        item = await svc.create(payload)
        assert item.owner_id == "u1"
        pub.assert_called_once()


@pytest.mark.asyncio
async def test_create_item_with_geometry_and_surface(svc: ItemService) -> None:
    svc.items.insert = AsyncMock(return_value=None)
    with patch("app.services.EventPublisher.publish", new=AsyncMock()):
        payload = ItemCreate(
            owner_id="u1",
            ingestion_method="manual",
            primary_category="top",
            geometry_data=GeometryData(
                silhouette_class="fitted",
                length_profile="hip",
                volume_distribution=[0.4, 0.3, 0.3],
                stretch_behavior="semi_flexible",
            ),
            surface_data=SurfaceData(
                dominant_color={"l": 50, "a": 0, "b": 0},
                color_variance=0.1,
                texture_class="smooth",
                pattern_density=0.0,
            ),
        )
        item = await svc.create(payload)
        assert item.geometry_profile is not None
        assert item.surface_properties is not None


@pytest.mark.asyncio
async def test_record_wear_updates_counters(svc: ItemService) -> None:
    from common.domain import IngestionMethod, PrimaryCategory, WardrobeObject
    from app.models import ItemRow

    domain = WardrobeObject("u1", IngestionMethod.MANUAL, PrimaryCategory.TOP)
    row = ItemRow.from_domain(domain)

    svc.items.get = AsyncMock(return_value=row)
    svc.items.update = AsyncMock()
    svc.wears.insert = AsyncMock()

    with patch("app.services.EventPublisher.publish", new=AsyncMock()), \
         patch("app.services.RedisCache.delete", new=AsyncMock()):
        result = await svc.record_wear(
            domain.id,
            WearRequest(accepted=True, duration_minutes=90),
        )
        assert result.total_wears == 1
        svc.wears.insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_raises_not_found(svc: ItemService) -> None:
    from common.errors import NotFoundError

    svc.items.get = AsyncMock(return_value=None)
    with patch("app.services.RedisCache.get_json", new=AsyncMock(return_value=None)):
        with pytest.raises(NotFoundError):
            await svc.get("nonexistent")
