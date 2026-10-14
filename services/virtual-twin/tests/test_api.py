import os

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_is_liveness_only():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_capabilities_do_not_claim_unimplemented_features():
    response = client.get("/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["twin_generation"] is False
    assert data["body_reconstruction"] is False
    assert data["skin_analysis"] is False
    assert data["ar_rendering"] is False


def test_readiness_fails_closed_without_model_adapter():
    response = client.get("/ready")
    assert response.status_code == 503


def test_twin_endpoint_requires_authentication():
    response = client.post(
        "/twin",
        data={"height_cm": "180", "weight_kg": "75"},
    )
    assert response.status_code == 401


def test_twin_endpoint_does_not_claim_generation_when_adapter_missing(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    response = client.post(
        "/twin",
        headers={"Authorization": "Bearer test-only-token"},
        data={"height_cm": "180", "weight_kg": "75"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MODEL_ADAPTER_NOT_CONFIGURED"


def test_twin_endpoint_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "expected-token")
    response = client.post(
        "/twin",
        headers={"Authorization": "Bearer wrong-token"},
        data={"height_cm": "180"},
    )
    assert response.status_code == 401
