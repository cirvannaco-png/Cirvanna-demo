from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from common.domain import IngestionMethod, PrimaryCategory, WardrobeObject
from app.repository import GraphRepository
from app.seeder import GraphSeeder


@pytest.fixture
def repo() -> GraphRepository:
    return AsyncMock(spec=GraphRepository)


@pytest.mark.asyncio
async def test_seed_creates_edges_for_compatible_pairs(repo: GraphRepository) -> None:
    repo.upsert_item = AsyncMock()
    repo.create_edge = AsyncMock()
    seeder = GraphSeeder(repo)

    top = WardrobeObject("u1", IngestionMethod.MANUAL, PrimaryCategory.TOP)
    bottom = WardrobeObject("u1", IngestionMethod.MANUAL, PrimaryCategory.BOTTOM)
    await seeder.seed_from_items([top, bottom])

    assert repo.create_edge.await_count == 2  # both directions
