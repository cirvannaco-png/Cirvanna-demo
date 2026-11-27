from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import SERVICE_NAME, app


def test_gateway_metrics_endpoint_requires_explicit_enablement(monkeypatch):
    monkeypatch.delenv("METRICS_ENABLED", raising=False)
    monkeypatch.setenv("OBSERVABILITY_METRICS_TOKEN", "m" * 48)
    response = TestClient(app).get("/internal/metrics")
    assert response.status_code == 404


def test_gateway_metrics_are_authenticated_private_and_low_cardinality(monkeypatch):
    token = "gateway-observability-test-token-" + ("x" * 24)
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("OBSERVABILITY_METRICS_TOKEN", token)
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.headers.get("X-Request-ID")
    denied = client.get("/internal/metrics", headers={"X-Observability-Token": "wrong"})
    assert denied.status_code == 401
    response = client.get("/internal/metrics", headers={"X-Observability-Token": token})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store, private"
    assert "http_server_requests_total" in response.text
    assert 'service="' + SERVICE_NAME + '"' in response.text
    assert 'route="/health"' in response.text
    assert "user_id" not in response.text
    assert "Authorization" not in response.text