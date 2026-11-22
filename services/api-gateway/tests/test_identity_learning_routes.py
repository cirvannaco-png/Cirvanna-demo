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
        "consent_receipt_id": "profile-receipt-verified-001",
        "preferences": [{
            "preference_id": "p1", "attribute": "style:classic", "weight": 0.8, "active": True,
            "source": "pnelly_user_confirmed", "source_request_id": "pnelly-request-001",
        }],
    })
    assert response.status_code == 200
    assert calls[0][2] == "commerce-verified-subject"
    assert calls[0][3]["preferences"][0]["attribute"] == "style:classic"
    assert calls[0][3]["preferences"][0]["source"] == "pnelly_user_confirmed"
    assert calls[0][3]["preferences"][0]["source_request_id"] == "pnelly-request-001"
    assert calls[0][3]["consent_receipt_id"] == "profile-receipt-verified-001"


def test_consent_and_tal_event_are_bound_to_verified_subject(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_verified_actor_from_header", lambda token: "commerce-verified-subject")
    monkeypatch.setattr(main, "_identity_service_request", lambda method, path, subject, payload=None: (
        calls.append((method, path, subject, payload)) or {"status": "recorded"}
    ))
    consent = client.post("/v1/me/consents", headers=headers(), json={
        "receipt_id": "receipt-0001", "scope": "style_learning",
        "consent_id": "bundle-0001", "resource_id": "twin-resource-1",
        "consent_version": "2026-11-02", "granted": True,
    })
    event = client.post("/v1/me/tal/events", headers=headers(), json={
        "event_id": "event-0001", "idempotency_key": "idempotency-0001",
        "consent_receipt_id": "receipt-0001", "feature_key": "colour.preference",
        "value": "teal", "observed_at": "2026-11-02T09:00:00Z",
    })
    assert consent.status_code == 200
    assert event.status_code == 200
    assert all(call[2] == "commerce-verified-subject" for call in calls)
    assert calls[0][3]["consent_id"] == "bundle-0001"
    assert calls[0][3]["resource_id"] == "twin-resource-1"


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


def test_skin_analysis_consent_must_be_resource_bound_and_expiring(client):
    missing = client.post("/v1/me/consents", headers=headers(), json={
        "receipt_id": "skin-consent-0001",
        "scope": "skin_analysis",
        "consent_id": "skin-bundle-0001",
        "consent_version": "skin-v1",
        "granted": True,
    })
    assert missing.status_code == 422

    no_resource = client.post("/v1/me/consents", headers=headers(), json={
        "receipt_id": "skin-consent-0002",
        "scope": "skin_analysis",
        "consent_id": "skin-bundle-0002",
        "consent_version": "skin-v1",
        "granted": True,
        "expires_at": "2027-01-01T00:00:00Z",
    })
    assert no_resource.status_code == 422

    expired = client.post("/v1/me/consents", headers=headers(), json={
        "receipt_id": "skin-consent-0003",
        "scope": "skin_analysis",
        "consent_id": "skin-bundle-0003",
        "resource_id": "skin-resource-0003",
        "consent_version": "skin-v1",
        "granted": True,
        "expires_at": "2020-01-01T00:00:00Z",
    })
    assert expired.status_code == 422


def test_skin_analysis_consent_forwards_expiry_to_canonical_identity_store(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_verified_actor_from_header", lambda token: "commerce-verified-adult-subject")
    monkeypatch.setattr(
        main,
        "_identity_service_request",
        lambda method, path, subject, payload=None: (
            calls.append((method, path, subject, payload)) or {"status": "recorded"}
        ),
    )
    expiry = "2027-01-01T00:00:00Z"
    response = client.post("/v1/me/consents", headers=headers(), json={
        "receipt_id": "skin-consent-expiring",
        "scope": "skin_analysis",
        "consent_id": "skin-bundle-expiring",
        "resource_id": "skin-resource-expiring",
        "consent_version": "skin-v1",
        "granted": True,
        "expires_at": expiry,
    })
    assert response.status_code == 200
    assert calls[0][0] == "POST"
    assert calls[0][1] == "/v1/tal/consents"
    assert calls[0][2] == "commerce-verified-adult-subject"
    assert calls[0][3]["resource_id"] == "skin-resource-expiring"
    assert calls[0][3]["expires_at"].startswith("2027-01-01T00:00:00")
