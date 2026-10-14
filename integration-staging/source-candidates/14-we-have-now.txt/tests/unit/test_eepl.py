import pytest
from unittest.mock import AsyncMock, patch
from src.core.eepl import EEPL

@pytest.mark.asyncio
async def test_eepl_basic_flow():
    # Setup mocks
    user_repo = AsyncMock()
    item_repo = AsyncMock()
    segment_repo = AsyncMock()
    snapshot_repo = AsyncMock()
    feedback_repo = AsyncMock()
    climate_service = AsyncMock()
    virtual_twin = AsyncMock()
    cfrp_client = AsyncMock()
    fci_client = AsyncMock()
    cache = AsyncMock()
    cultural_validator = AsyncMock()
    trend_service = AsyncMock()
    ab_framework = AsyncMock()
    explainer = AsyncMock()

    eepl = EEPL(
        user_repo, item_repo, segment_repo, snapshot_repo,
        feedback_repo, climate_service, virtual_twin,
        cfrp_client, fci_client, cache, cultural_validator,
        trend_service, ab_framework, explainer
    )

    # mock data
    user_repo.get_user.return_value = None
    climate_service.get_environmental_signal.return_value = EnvironmentalSignalVector.neutral()
    cfrp_client.predict.return_value = 0.6

    result = await eepl.process(
        UUID("12345678-1234-1234-1234-123456789abc"),
        [],
        {}
    )
    assert isinstance(result, list)
