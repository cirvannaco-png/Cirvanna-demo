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
DELETE_TOKEN = "twin-registry-deletion-token-at-least-thirty-two-bytes"
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
    monkeypatch.setenv("TWIN_REGISTRY_DELETION_TOKEN", DELETE_TOKEN)
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
                "verified": True,
                "active": True,
                "subject_id": json_body["subject_id"],
                "consent_id": json_body["consent_id"],
                "resource_id": json_body["resource_id"],
                "consent_version": "media-v1",
                "granted_scopes": ["image_processing", "body_measurements", "virtual_twin_storage"],
            })
        ids = sorted(json_body["asset_ids"])
        return FakeResponse(payload={
            "authorized": True,
            "subject_id": json_body["subject_id"],
            "purpose": json_body["purpose"],
            "parent_id": json_body["parent_id"],
            "authorized_asset_ids": ids,
        })
    monkeypatch.setattr(main, "_json_request", fake_request)
    with TestClient(main.app) as test_client:
        yield test_client
    main._session_factory.cache_clear()
    main._engine.cache_clear()


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def deletion_auth():
    return {"X-Twin-Deletion-Token": DELETE_TOKEN}


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
    assert payload["version"] == 1
    assert foreign_owner.status_code == 403


def test_revoke_queues_asset_deletion_and_blocks_future_authorization(client):
    assert create(client).status_code == 200
    response = client.post(
        "/internal/v1/twins/revoke", headers=auth(),
        json={"subject_id": "customer-123", "twin_id": "twin-123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "deletion_pending"
    denied = client.post(
        "/internal/v1/twins/authorize", headers=auth(),
        json={"subject_id": "customer-123", "twin_id": "twin-123"},
    )
    assert denied.status_code == 403


def test_deactivation_is_versioned_owner_scoped_and_idempotent(client):
    assert create(client).status_code == 200
    wrong_owner = client.post(
        "/internal/v1/twins/deactivate",
        headers=auth(),
        json={
            "subject_id": "customer-999", "twin_id": "twin-123",
            "expected_version": 1, "command_id": "delete-twin-command-0001",
        },
    )
    stale = client.post(
        "/internal/v1/twins/deactivate",
        headers=auth(),
        json={
            "subject_id": "customer-123", "twin_id": "twin-123",
            "expected_version": 0, "command_id": "delete-twin-command-0002",
        },
    )
    accepted = client.post(
        "/internal/v1/twins/deactivate",
        headers=auth(),
        json={
            "subject_id": "customer-123", "twin_id": "twin-123",
            "expected_version": 1, "command_id": "delete-twin-command-0003",
        },
    )
    replay = client.post(
        "/internal/v1/twins/deactivate",
        headers=auth(),
        json={
            "subject_id": "customer-123", "twin_id": "twin-123",
            "expected_version": 1, "command_id": "delete-twin-command-0003",
        },
    )
    assert wrong_owner.status_code == 404
    assert stale.status_code == 409
    assert accepted.status_code == 202
    assert accepted.json()["status"] == "pending"
    assert replay.status_code == 202
    assert replay.json()["status"] == "pending"
    status = client.get(
        "/internal/v1/twins/twin-123/status?subject_id=customer-123",
        headers=auth(),
    )
    assert status.status_code == 200
    assert status.json()["status"] == "deletion_pending"
    assert status.json()["version"] == 2


def test_deletion_dispatch_requires_distinct_worker_token(client):
    response = client.post("/internal/v1/twins/deletions/dispatch", headers=auth())
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "TWIN_DELETION_AUTH_REQUIRED"


def test_deletion_dispatch_only_marks_deleted_after_asset_provider_confirms_exact_assets(client, monkeypatch):
    assert create(client).status_code == 200
    queued = client.post(
        "/internal/v1/twins/deactivate",
        headers=auth(),
        json={
            "subject_id": "customer-123", "twin_id": "twin-123",
            "expected_version": 1, "command_id": "delete-twin-command-0004",
        },
    )
    assert queued.status_code == 202
    seen = {}

    async def deleted(subject_id, twin_id, asset_ids, idempotency_key):
        seen.update(subject_id=subject_id, twin_id=twin_id, asset_ids=asset_ids, idempotency_key=idempotency_key)

    monkeypatch.setattr(main, "_delete_assets", deleted)
    result = client.post("/internal/v1/twins/deletions/dispatch", headers=deletion_auth())
    status = client.get(
        "/internal/v1/twins/twin-123/status?subject_id=customer-123",
        headers=auth(),
    )
    assert result.status_code == 200
    assert result.json() == {"processed": 1, "completed": 1, "failed": 0}
    assert set(seen["asset_ids"]) == {MESH, SOURCE}
    assert seen["idempotency_key"].startswith("twin-delete:")
    assert status.json()["status"] == "deleted"
    assert status.json()["deleted_at"]


def test_failed_asset_deletion_remains_pending_and_retries(client, monkeypatch):
    assert create(client).status_code == 200
    client.post(
        "/internal/v1/twins/deactivate",
        headers=auth(),
        json={
            "subject_id": "customer-123", "twin_id": "twin-123",
            "expected_version": 1, "command_id": "delete-twin-command-0005",
        },
    )

    async def failed(*_args, **_kwargs):
        raise main.HTTPException(503, detail={"code": "TWIN_ASSET_DELETION_UNAVAILABLE"})

    monkeypatch.setattr(main, "_delete_assets", failed)
    result = client.post("/internal/v1/twins/deletions/dispatch", headers=deletion_auth())
    status = client.get(
        "/internal/v1/twins/twin-123/status?subject_id=customer-123",
        headers=auth(),
    )
    assert result.json() == {"processed": 1, "completed": 0, "failed": 1}
    assert status.json()["status"] == "deletion_pending"


def test_consent_withdrawal_queues_every_owner_scoped_twin_for_that_receipt(client):
    first = body()
    second = body(
        twin_id="twin-456",
        mesh_asset_id="00000000-0000-4000-8000-000000000003",
        source_image_asset_ids=["00000000-0000-4000-8000-000000000004"],
    )
    assert client.post("/internal/v1/twins", headers=auth(), json=first).status_code == 200
    assert client.post("/internal/v1/twins", headers=auth(), json=second).status_code == 200
    withdrawal = client.post(
        "/internal/v1/twins/revoke-consent",
        headers=auth(),
        json={
            "subject_id": "customer-123",
            "consent_id": "consent-twin-0001",
            "command_id": "withdraw-consent-command-001",
        },
    )
    first_status = client.get("/internal/v1/twins/twin-123/status?subject_id=customer-123", headers=auth())
    second_status = client.get("/internal/v1/twins/twin-456/status?subject_id=customer-123", headers=auth())
    assert withdrawal.status_code == 202
    assert withdrawal.json()["twins_queued"] == 2
    assert first_status.json()["status"] == "deletion_pending"
    assert second_status.json()["status"] == "deletion_pending"


def test_readiness_does_not_claim_ready_without_providers(client, monkeypatch):
    monkeypatch.delenv("ASSET_SERVICE_URL", raising=False)
    result = client.get("/ready", headers=auth())
    assert result.status_code == 503
    assert result.json()["detail"]["code"] == "ASSET_SERVICE_NOT_CONFIGURED"
