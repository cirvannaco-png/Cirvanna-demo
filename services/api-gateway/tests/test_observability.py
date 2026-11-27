from __future__ import annotations

from fastapi.testclient import TestClient

from app import main


METRICS_TOKEN = "gateway-internal-observability-test-token-over-32-bytes"
client = TestClient(main.app)


def test_gateway_metrics_are_not_exposed_when_disabled(monkeypatch):
    monkeypatch.delenv("METRICS_ENABLED", raising=False)
    monkeypatch.delenv("OBSERVABILITY_METRICS_TOKEN", raising=False)

    response = client.get("/internal/metrics")

    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"


def test_gateway_metrics_require_a_separate_internal_secret(monkeypatch):
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("OBSERVABILITY_METRICS_TOKEN", METRICS_TOKEN)

    response = client.get("/internal/metrics")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "METRICS_AUTH_REQUIRED"


def test_gateway_metrics_export_bounded_route_and_dependency_series(monkeypatch):
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("OBSERVABILITY_METRICS_TOKEN", METRICS_TOKEN)
    main.app.state.request_metrics.record_dependency("catalog", "GET", 200, 0.025)

    health = client.get("/health")
    assert health.status_code == 200
    assert len(health.headers["x-request-id"]) == 36

    response = client.get(
        "/internal/metrics",
        headers={"X-Observability-Token": METRICS_TOKEN},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    assert 'route="/health"' in response.text
    assert 'dependency="catalog"' in response.text
    assert "http_client_request_duration_seconds_bucket" in response.text
    assert METRICS_TOKEN not in response.text
    assert "subject-verified" not in response.text
