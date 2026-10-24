"""Contract tests for PAMASMMA-derived cognitive service boundary."""
import asyncio
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "cognitive-orchestration"
sys.path.insert(0, str(SERVICE))
contracts = importlib.import_module("contracts")
registry = importlib.import_module("registry")


def test_ten_cognitive_domains_are_declared():
    assert len(list(contracts.CognitiveSystem)) == 10


def test_unconfigured_domain_fails_closed():
    request = contracts.CognitiveRequest(
        system=contracts.CognitiveSystem.MARKETING_INTELLIGENCE,
        context={"event": "BRAND_ONBOARDED"},
    )
    try:
        asyncio.run(registry.dispatch(request))
    except registry.CognitiveSystemUnavailable as exc:
        assert "marketing_intelligence" in str(exc)
    else:
        raise AssertionError("Unconfigured cognitive domain must not fabricate a result")


def test_duplicate_handler_registration_is_rejected():
    async def handler(request):
        return contracts.CognitiveResponse(
            request_id=request.event_id,
            system=request.system,
            action="test",
            rationale="test handler",
            requires_founder_approval=True,
            estimated_impact="test",
        )

    system = contracts.CognitiveSystem.EXECUTIVE_OPERATIONS
    registry.clear_handlers_for_tests()
    registry.register_handler(system, handler)
    try:
        try:
            registry.register_handler(system, handler)
        except ValueError:
            pass
        else:
            raise AssertionError("Duplicate handler registration must be rejected")
    finally:
        registry.clear_handlers_for_tests()
