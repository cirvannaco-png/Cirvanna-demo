from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
METRICS_TOKEN = "internal-observability-test-token-longer-than-thirty-two-bytes"


def test_metrics_are_not_exposed_when_disabled(monkeypatch):
    monkeypatch.delenv("METRICS_ENABLED", raising=False)
    monkeypatch.delenv("OBSERVABILITY_METRICS_TOKEN", raising=False)

    response = client.get("/internal/metrics")

    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"


def test_metrics_require_a_separate_internal_secret(monkeypatch):
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("OBSERVABILITY_METRICS_TOKEN", METRICS_TOKEN)

    response = client.get("/internal/metrics")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "METRICS_AUTH_REQUIRED"


def test_metrics_export_only_low_cardinality_route_and_latency_series(monkeypatch):
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("OBSERVABILITY_METRICS_TOKEN", METRICS_TOKEN)

    health = client.get("/health")
    assert health.status_code == 200
    assert len(health.headers["x-request-id"]) == 36

    response = client.get(
        "/internal/metrics",
        headers={"X-Observability-Token": METRICS_TOKEN},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    assert "http_server_requests_total" in response.text
    assert "http_server_request_duration_seconds_bucket" in response.text
    assert 'route="/health"' in response.text
    assert METRICS_TOKEN not in response.text


def test_dependency_metrics_reject_unbounded_labels():
    from app.observability import RequestMetrics

    metrics = RequestMetrics("test-service", dependency_names=("catalog",))
    metrics.record_dependency("customer-123", "GET", 200, 0.01)

    rendered = metrics.render()
    assert 'dependency="other"' in rendered
    assert "customer-123" not in rendered
