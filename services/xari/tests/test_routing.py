from __future__ import annotations

import os
from fastapi.testclient import TestClient

from xari.routing import plan_route
from app.main import app

client = TestClient(app)
TOKEN = "xari-test-token-that-is-at-least-32-bytes-long"

def test_route_requires_explicit_consent_before_checking_upstream():
    plan = plan_route("virtual_try_on", {}, environment={})
    assert plan.status == "blocked"
    assert plan.code == "XARI_REQUIRED_CONSENT_MISSING"
    assert set(plan.missing_consents) == {"image_processing", "virtual_try_on"}

def test_route_plan_is_configured_but_never_claims_execution():
    plan = plan_route(
        "virtual_try_on",
        {"image_processing": True, "virtual_try_on": True},
        environment={"VIRTUAL_TRY_ON_API_URL": "https://tryon.internal"},
    )
    assert plan.status == "route_configured"
    assert plan.configured is True
    assert plan.execution_supported is False
    assert plan.code == "XARI_ROUTE_CONFIGURED_NOT_EXECUTED"

def test_invalid_or_untrusted_upstream_is_unavailable():
    for url in ("http://example.com", "https://example.com?url=x"):
        plan = plan_route(
            "marketplace_search", {}, environment={"MARKETPLACE_BFF_URL": url}
        )
        assert plan.status == "unavailable"
        assert plan.code == "XARI_UPSTREAM_URL_INVALID"

def test_unknown_intents_and_consent_fields_are_rejected():
    try:
        plan_route("execute-arbitrary-url", {})
    except ValueError:
        pass
    else:
        raise AssertionError("unknown intent must be rejected")
    try:
        plan_route("wardrobe", {"infer_culture": True})
    except ValueError:
        pass
    else:
        raise AssertionError("unknown consent field must be rejected")

def test_health_is_liveness_and_capabilities_are_honest():
    assert client.get("/health").json()["status"] == "alive"
    data = client.get("/capabilities").json()
    assert data["canonical_name"] == "PNELLY"
    assert data["legacy_names"] == ["Xari", "Tari", "Xyra"]
    assert data["contract_compatibility"]["xari_routes_preserved"] is True
    assert data["execution_enabled"] is False

def test_unknown_consent_field_is_a_client_error_not_a_server_error(monkeypatch):
    monkeypatch.setenv("PNELLY_API_TOKEN", TOKEN)
    response = client.post(
        "/v1/route",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"request_id": "req-2", "intent": "wardrobe", "consents": {"infer_culture": True}},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_ROUTE_REQUEST"

def test_routes_require_auth_and_do_not_claim_success(monkeypatch):
    monkeypatch.setenv("XARI_API_TOKEN", TOKEN)
    no_auth = client.post("/v1/route", json={"request_id": "req-1", "intent": "marketplace_search"})
    assert no_auth.status_code == 401
    response = client.post(
        "/v1/route",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"request_id": "req-1", "intent": "marketplace_search"},
    )
    assert response.status_code == 200
    assert response.json()["execution_supported"] is False
    assert response.json()["status"] == "unavailable"
    assert "not execute" in response.json()["detail"]
