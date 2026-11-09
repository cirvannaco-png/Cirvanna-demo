from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import main

TOKEN = "twin-registry-test-token-that-is-at-least-thirty-two-bytes"
VALIDATION_SECRET = "twin-validation-attestation-secret-at-least-32-bytes"
CONSENT_TOKEN = "identity-consent-internal-token-at-least-32-bytes"
ASSET_TOKEN = "private-asset-service-token-at-least-thirty-two-bytes"
MESH = "00000000-0000-4000-8000-000000000001"
SOURCE = "00000000-0000-4000-8000-000000000002"


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "registry.db")
    monkeypatch.setenv("TWIN_REGISTRY_DATABASE_URL", url)
    monkeypatch.setenv("TWIN_REGISTRY_API_TOKEN", TOKEN)
    monkeypatch.setenv("TWIN_REGISTRY_VALIDATION_HMAC_SECRET", VALIDATION_SECRET)
    monkeypatch.setenv("CONSENT_API_URL", "https://identity.example.test")
    monkeypatch.setenv("CONSENT_API_TOKEN", CONSENT_TOKEN)
    monkeypatch.setenv("ASSET_SERVICE_URL", "https://assets.example.test")
    monkeypatch.setenv("ASSET_SERVICE_TOKEN", ASSET_TOKEN)
    main._engine.cache_clear()
    main._session_factory.cache_clear()
    main.Base.metadata.create_all(bind=main._engine(url))
    async def fake_request(method, base, path, token, *, json_body=None):
        if base == "https://identity.example.test":
            return FakeResponse(payload={
                "verified": True, "active": True, "subject_id": "customer-123",
                "consent_id": "consent-twin-0001", "resource_id": "twin-123",
                "consent_version": "media-v1",
                "granted_scopes": ["image_processing", "body_measurements", "virtual_twin_storage"],
            })
        ids = sorted(json_body["asset_ids"])
        return FakeResponse(payload={
            "authorized": True, "subject_id": "customer-123",
            "purpose": "virtual_twin_storage", "parent_id": "twin-123",
            "authorized_asset_ids": ids,
        })
    monkeypatch.setattr(main, "_json_request", fake_request)
    with TestClient(main.app) as test_client:
        yield test_client
    main._session_factory.cache_clear()
    main._engine.cache_clear()


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def body(**overrides):
    payload = {
        "twin_id": "twin-123",
        "subject_id": "customer-123",
        "mesh_asset_id": MESH,
        "source_image_asset_ids": [SOURCE],
        "consent_id": "consent-twin-0001",
        "model_id": "cirvanna-full-body-mesh",
        "model_revision": "b" * 40,
        "model_release_sha256": "c" * 64,
        "validation_report_sha256": "d" * 64,
    }
    payload.update(overrides)
    attestation = {
        key: payload[key] for key in (
            "twin_id", "subject_id", "mesh_asset_id", "source_image_asset_ids",
            "consent_id", "model_id", "model_revision", "model_release_sha256",
            "validation_report_sha256",
        )
    }
    attestation["source_image_asset_ids"] = sorted(attestation["source_image_asset_ids"])
    attestation["representation_type"] = "full_body_mesh"
    canonical = json.dumps(attestation, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload["validation_attestation_hmac"] = hmac.new(
        VALIDATION_SECRET.encode(), canonical.encode(), hashlib.sha256
    ).hexdigest()
    return payload


def create(client, **overrides):
    return client.post("/internal/v1/twins", headers=auth(), json=body(**overrides))


def test_internal_auth_is_required(client):
    assert client.post("/internal/v1/twins", json=body()).status_code == 401


def test_twin_is_created_only_after_consent_asset_and_model_attestation(client):
    response = create(client)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "active"
    assert result["representation_type"] == "full_body_mesh"
    assert result["source_image_asset_ids"] == [SOURCE]
    replay = create(client)
    assert replay.status_code == 200
    assert replay.json()["status"] == "replayed"


def test_invalid_validation_attestation_is_rejected(client):
    payload = body()
    payload["validation_attestation_hmac"] = "0" * 64
    result = client.post("/internal/v1/twins", headers=auth(), json=payload)
    assert result.status_code == 403
    assert result.json()["detail"]["code"] == "TWIN_VALIDATION_ATTESTATION_INVALID"


def test_duplicate_or_mesh_as_source_asset_is_rejected_by_schema(client):
    duplicate = client.post("/internal/v1/twins", headers=auth(), json=body(
        source_image_asset_ids=[SOURCE, SOURCE],
    ))
    overlap = client.post("/internal/v1/twins", headers=auth(), json=body(
        source_image_asset_ids=[MESH],
    ))
    assert duplicate.status_code == 422
    assert overlap.status_code == 422


def test_consent_failure_blocks_registration_and_authorization(client, monkeypatch):
    original = main._verify_consent
    async def denied(*args, **kwargs):
        from fastapi import HTTPException
        raise HTTPException(403, detail={"code": "TWIN_CONSENT_NOT_ACTIVE"})
    monkeypatch.setattr(main, "_verify_consent", denied)
    denied_create = create(client)
    assert denied_create.status_code == 403
    monkeypatch.setattr(main, "_verify_consent", original)
    created = create(client)
    assert created.status_code == 200
    monkeypatch.setattr(main, "_verify_consent", denied)
    denied_auth = client.post(
        "/internal/v1/twins/authorize", headers=auth(),
        json={"subject_id": "customer-123", "twin_id": "twin-123"},
    )
    assert denied_auth.status_code == 403


def test_asset_service_failure_blocks_registration(client, monkeypatch):
    async def denied(*args, **kwargs):
        from fastapi import HTTPException
        raise HTTPException(503, detail={"code": "ASSET_SERVICE_UNAVAILABLE"})
    monkeypatch.setattr(main, "_authorize_assets", denied)
    result = create(client)
    assert result.status_code == 503


def test_authorization_rechecks_owner_consent_and_assets(client):
    assert create(client).status_code == 200
    same_owner = client.post(
        "/internal/v1/twins/authorize", headers=auth(),
        json={"subject_id": "customer-123", "twin_id": "twin-123"},
    )
    foreign_owner = client.post(
        "/internal/v1/twins/authorize", headers=auth(),
        json={"subject_id": "customer-456", "twin_id": "twin-123"},
    )
    assert same_owner.status_code == 200
    payload = same_owner.json()
    assert payload["authorized"] is True
    assert payload["source_image_asset_ids"] == [SOURCE]
    assert payload["representation_type"] == "full_body_mesh"
    assert foreign_owner.status_code == 403


def test_revoke_blocks_future_authorization(client):
    assert create(client).status_code == 200
    response = client.post(
        "/internal/v1/twins/revoke", headers=auth(),
        json={"subject_id": "customer-123", "twin_id": "twin-123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
    denied = client.post(
        "/internal/v1/twins/authorize", headers=auth(),
        json={"subject_id": "customer-123", "twin_id": "twin-123"},
    )
    assert denied.status_code == 403


def test_readiness_does_not_claim_ready_without_providers(client, monkeypatch):
    monkeypatch.delenv("ASSET_SERVICE_URL", raising=False)
    result = client.get("/ready", headers=auth())
    assert result.status_code == 503
    assert result.json()["detail"]["code"] == "ASSET_SERVICE_NOT_CONFIGURED"
