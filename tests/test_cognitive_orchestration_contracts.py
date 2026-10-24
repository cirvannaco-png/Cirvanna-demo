"""Contract tests for PAMASMMA-derived cognitive service boundary."""
import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "cognitive-orchestration"
sys.path.insert(0, str(SERVICE))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_ten_cognitive_domains_are_declared():
    contracts = _load("contracts", SERVICE / "contracts.py")
    assert len(list(contracts.CognitiveSystem)) == 10


def test_unconfigured_domain_fails_closed():
    contracts = _load("contracts", SERVICE / "contracts.py")
    registry = _load("cognitive_registry", SERVICE / "registry.py")
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
    contracts = _load("contracts", SERVICE / "contracts.py")
    registry = _load("cognitive_registry", SERVICE / "registry.py")

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
        registry.register_handler(system, handler)
    except ValueError:
        pass
    else:
        raise AssertionError("Duplicate handler registration must be rejected")
    finally:
        registry.clear_handlers_for_tests()
