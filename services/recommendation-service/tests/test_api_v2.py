import pytest
from fastapi.testclient import TestClient

from app import main

TOKEN = "complementer-v2-test-token-with-32-or-more-bytes"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("COMPLEMENTER_SERVICE_TOKEN", TOKEN)
    with TestClient(main.app) as test_client:
        yield test_client


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def personal_body():
    return {
        "request_id": "req-2",
        "user_id": "user-1",
        "preferences": {
            "aesthetics": ["elegant"],
            "favorite_colors": ["emerald"],
            "favorite_fragrance_families": ["woody"],
            "preferred_scent_notes": ["cedar"],
            "fragrance_intensity": "light",
            "fragrance_projection": "intimate",
            "fragrance_longevity": "long",
            "fragrance_budget_minor": 500000,
            "fragrance_budget_currency": "KES",
            "earrings_preference": "avoid",
            "necklace_preference": "avoid",
            "glasses_preference": "avoid",
        },
        "look": {"outfit_colors": ["emerald"], "climate": "hot_humid", "occasion": "work"},
    }


def test_capabilities_are_transparent_about_pending_integrations(client):
    result = client.get("/capabilities").json()
    assert result["personal_aesthetic_v2_contract"] is True
    assert result["profile_persistence_connected"] is False
    assert result["catalog_integration_connected"] is False
    assert result["skin_forecast_provider_validated"] is False


def test_v2_complementer_requires_auth_and_returns_coordinated_directions(client):
    assert client.post("/v2/complementer/compose", json=personal_body()).status_code == 401
    response = client.post("/v2/complementer/compose", headers=auth(), json=personal_body())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["aesthetic"]["direction"].startswith("Elegant")
    assert result["jewellery"]["earrings"]["status"] == "omitted_by_preference"
    assert result["look_completion"]["strategy"] == "minimal_change"


def test_product_intelligence_api_is_not_display_authorization(client):
    body = {
        "product": {"product_id": "p-1", "catalog_version": 2, "product_intelligence": None},
        "profile": {"climate": "hot_humid"},
    }
    response = client.post("/v1/marketplace/product-intelligence/evaluate", headers=auth(), json=body)
    assert response.status_code == 200, response.text
    assert response.json()["dimensions"]["climate_compatibility"]["status"] == "unknown"
    assert response.json()["display_authorized"] is False


def test_skin_endpoint_returns_not_validated_without_fake_forecast(client):
    body = {
        "request_id": "skin-1", "user_id": "user-1", "product_id": "p-1",
        "product_version": 1, "consent": True, "forecast_horizon_weeks": 4,
        "humidity_scenario": "high", "sleep_scenario": "disrupted",
    }
    response = client.post("/v1/skin-state/scenario", headers=auth(), json=body)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "not_validated"
    assert response.json()["forecast"] is None


def test_skin_cycle_context_requires_separate_consent(client):
    body = {
        "request_id": "skin-1", "user_id": "user-1", "product_id": "p-1",
        "product_version": 1, "consent": True, "forecast_horizon_weeks": 4,
        "humidity_scenario": "high", "sleep_scenario": "disrupted",
        "cycle_context": "luteal",
    }
    response = client.post("/v1/skin-state/scenario", headers=auth(), json=body)
    assert response.status_code == 422


def test_preference_feedback_api_only_proposes_event(client):
    body = {
        "event_id": "evt-1", "request_id": "req-1", "user_id": "user-1",
        "recommendation_id": "rec-1", "dimension": "aesthetic",
        "action": "rejected", "value": "bold", "learning_consent": True,
    }
    response = client.post("/v1/complementer/feedback", headers=auth(), json=body)
    assert response.status_code == 200, response.text
    assert response.json()["events"][0]["owner"] == "NPL"
    assert response.json()["persistence"] == "not_connected"
