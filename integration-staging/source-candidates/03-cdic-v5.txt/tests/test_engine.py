import pytest
import asyncio
from cdic.core.engine import CDICEngine
from cdic.common.structs import DecisionContext
from cdic.config import CDICConfig

@pytest.fixture
def config():
    return CDICConfig(secret_key="test-secret-key-32-chars-12345678")

@pytest.fixture
def engine(config):
    return CDICEngine(config)

@pytest.mark.asyncio
async def test_simple_decision(engine):
    context = DecisionContext.create(
        intent="test_query",
        input_data={"query": "test"},
        user_id="user1",
        session_id="session1"
    )
    result = await engine.process_decision(context, {})
    assert result['state'] in (DecisionState.COMPLETED, DecisionState.CLARIFICATION_PENDING)
    assert 'decision' in result
