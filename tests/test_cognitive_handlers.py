"""Tests for real, bounded PAMASMMA-derived handler behavior."""
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


contracts = _load("contracts", SERVICE / "contracts.py")
registry = _load("registry", SERVICE / "registry.py")
handlers = _load("handlers", SERVICE / "handlers.py")


def _request(system, context):
    return contracts.CognitiveRequest(system=system, context=context)


def test_critical_incident_is_triaged_without_remediation():
    response = asyncio.run(handlers.executive_operations(_request(
        contracts.CognitiveSystem.EXECUTIVE_OPERATIONS,
        {"severity": "critical", "incident_type": "service_down", "affected_service": "catalog"},
    )))
    assert response.outputs["queue_priority"] == 1
    assert response.outputs["automated_remediation"] is False
    assert response.requires_founder_approval is True


def test_unknown_incident_severity_fails_closed():
    response = asyncio.run(handlers.executive_operations(_request(
        contracts.CognitiveSystem.EXECUTIVE_OPERATIONS, {"severity": "catastrophic"}
    )))
    assert response.action == "request_more_information"
    assert response.requires_founder_approval is True


def test_support_routing_uses_declared_category_only():
    response = asyncio.run(handlers.relationship_management(_request(
        contracts.CognitiveSystem.RELATIONSHIP_MANAGEMENT,
        {"category": "privacy", "urgency": "normal"},
    )))
    assert response.outputs["queue"] == "privacy_support"
    assert response.requires_founder_approval is True
    assert response.outputs["message_sent"] is False


def test_narrative_missing_required_term_is_held():
    response = asyncio.run(handlers.narrative_governance(_request(
        contracts.CognitiveSystem.NARRATIVE_GOVERNANCE,
        {"content": "New styles for everyday wear", "required_terms": ["Cirvanna"]},
    )))
    assert response.action == "hold_for_revision"
    assert response.outputs["published"] is False


def test_persuasion_governance_never_self_approves():
    response = asyncio.run(handlers.persuasion_governance(_request(
        contracts.CognitiveSystem.PERSUASION_GOVERNANCE,
        {"content": "Guaranteed results, only today!"},
    )))
    assert response.outputs["policy_pass"] is False
    assert response.outputs["human_review_required"] is True
    assert response.outputs["published"] is False


def test_empty_campaign_content_fails_closed():
    response = asyncio.run(handlers.persuasion_governance(_request(
        contracts.CognitiveSystem.PERSUASION_GOVERNANCE, {}
    )))
    assert response.action == "hold_for_review"
    assert response.outputs["policy_pass"] is False
