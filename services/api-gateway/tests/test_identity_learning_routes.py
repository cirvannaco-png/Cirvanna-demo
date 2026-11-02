import pytest
from fastapi.testclient import TestClient

from app import main

TOKEN = "gateway-identity-routes-test-token-over-32-bytes"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", TOKEN)
    monkeypatch.setenv("CIRVANNA_AUDIT_DB", str(tmp_path / "audit.sqlite3"))
    return TestClient(main.app)


def headers():
    return {
        "Authorization": f"Bearer {TOKEN}",
        "X-End-User-Authorization": "Bearer user-provider-token",
    }


def test_profile_update_uses_verified_subject_not_body_subject(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_verified_actor_from_header", lambda token: "commerce-verified-subject")
    monkeypatch.setattr(main, "_identity_service_request", lambda method, path, subject, payload=None: (
        calls.append((method, path, subject, payload)) or {"subject_id": subject, "profile_version": 1}
    ))
    response = client.put("/v1/me/style-profile", headers=headers(), json={
        "expected_version": 0,
        "preferences": [{"preference_id": "p1", "attribute": "classic", "weight": 0.8, "active": True}],
    })
    assert response.status_code == 200
    assert calls[0][2] == "commerce-verified-subject"
    assert calls[0][3]["preferences"][0]["attribute"] == "classic"


def test_consent_and_tal_event_are_bound_to_verified_subject(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_verified_actor_from_header", lambda token: "commerce-verified-subject")
    monkeypatch.setattr(main, "_identity_service_request", lambda method, path, subject, payload=None: (
        calls.append((method, path, subject, payload)) or {"status": "recorded"}
    ))
    consent = client.post("/v1/me/consents", headers=headers(), json={
        "receipt_id": "receipt-0001", "scope": "style_learning", "consent_version": "2026-11-02", "granted": True,
    })
    event = client.post("/v1/me/tal/events", headers=headers(), json={
        "event_id": "event-0001", "idempotency_key": "idempotency-0001",
        "consent_receipt_id": "receipt-0001", "feature_key": "colour.preference",
        "value": "teal", "observed_at": "2026-11-02T09:00:00Z",
    })
    assert consent.status_code == 200
    assert event.status_code == 200
    assert all(call[2] == "commerce-verified-subject" for call in calls)


def test_export_and_deletion_use_verified_subject(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_verified_actor_from_header", lambda token: "commerce-verified-subject")
    monkeypatch.setattr(main, "_identity_service_request", lambda method, path, subject, payload=None: (
        calls.append((method, path, subject)) or {"status": "ok"}
    ))
    assert client.get("/v1/me/tal/export", headers=headers()).status_code == 200
    assert client.delete("/v1/me/tal/data", headers=headers()).status_code == 200
    assert calls == [
        ("GET", "/v1/tal/export/commerce-verified-subject", "commerce-verified-subject"),
        ("DELETE", "/v1/tal/users/commerce-verified-subject", "commerce-verified-subject"),
    ]


def test_user_data_routes_require_gateway_authentication(client):
    response = client.get("/v1/me/style-profile", headers={"X-End-User-Authorization": "Bearer user"})
    assert response.status_code == 401
