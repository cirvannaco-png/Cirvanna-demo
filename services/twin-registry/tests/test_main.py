from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import main

TOKEN = "twin-registry-test-token-that-is-at-least-thirty-two-bytes"
VALIDATION_SECRET = "twin-validation-attestation-secret-at-least-32-bytes"


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "registry.db")
    monkeypatch.setenv("TWIN_REGISTRY_DATABASE_URL", url)
    monkeypatch.setenv("TWIN_REGISTRY_API_TOKEN", TOKEN)
    monkeypatch.setenv("TWIN_REGISTRY_VALIDATION_HMAC_SECRET", VALIDATION_SECRET)
    main._engine.cache_clear()
    main._session_factory.cache_clear()
    main.Base.metadata.create_all(bind=main._engine(url))
    with TestClient(main.app) as test_client:
        yield test_client
    main._session_factory.cache_clear()
    main._engine.cache_clear()


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def register(client, **overrides):
    body = {
        "owner_subject_id": "customer-123",
        "tenant_id": "customer-123",
        "asset_kind": "twin_mesh",
        "access_scope": "private",
        "twin_id": "twin-123",
        "product_id": None,
        "storage_object_key": "object-key-" + str(len(overrides)),
        "content_type": "model/gltf-binary",
        "byte_size": 1024,
        "sha256": "a" * 64,
    }
    body.update(overrides)
    response = client.post("/internal/v1/assets/register", headers=auth(), json=body)
    assert response.status_code == 200, response.text
    return response.json()["asset_id"]


def create_twin(client, mesh_id, **overrides):
    body = {
        "twin_id": "twin-123",
        "subject_id": "customer-123",
        "mesh_asset_id": mesh_id,
        "model_id": "cirvanna-avatar-mesh",
        "model_revision": "b" * 40,
        "model_release_sha256": "c" * 64,
        "validation_report_sha256": "d" * 64,
    }
    body.update(overrides)
    attested = {
        "twin_id": body["twin_id"],
        "subject_id": body["subject_id"],
        "mesh_asset_id": body["mesh_asset_id"],
        "model_id": body["model_id"],
        "model_revision": body["model_revision"],
        "model_release_sha256": body["model_release_sha256"],
        "validation_report_sha256": body["validation_report_sha256"],
    }
    canonical = json.dumps(attested, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    body["validation_attestation_hmac"] = hmac.new(
        VALIDATION_SECRET.encode(), canonical.encode(), hashlib.sha256
    ).hexdigest()
    return client.post("/internal/v1/twins", headers=auth(), json=body)


def register_person(client, **overrides):
    return register(
        client,
        asset_kind="person_reference",
        storage_object_key="person-reference-key",
        content_type="image/jpeg",
        twin_id="twin-123",
        **overrides,
    )


def register_garment(client, **overrides):
    return register(
        client,
        owner_subject_id=None,
        tenant_id="catalog:merchant-1",
        asset_kind="catalog_garment",
        access_scope="catalog",
        twin_id=None,
        product_id="product-123",
        storage_object_key="catalog-garment-key",
        content_type="image/webp",
        **overrides,
    )


def test_internal_registry_requires_machine_auth(client):
    response = client.post(
        "/internal/v1/assets/register",
        json={
            "owner_subject_id": "customer-123",
            "tenant_id": "customer-123",
            "asset_kind": "person_reference",
            "access_scope": "private",
            "twin_id": "twin-123",
            "storage_object_key": "object-key-1",
            "content_type": "image/jpeg",
            "byte_size": 100,
            "sha256": "a" * 64,
        },
    )
    assert response.status_code == 401


def test_twin_requires_a_private_mesh_asset_owned_by_same_subject(client):
    foreign_mesh = register(
        client,
        owner_subject_id="customer-456",
        tenant_id="customer-456",
        storage_object_key="foreign-mesh-key",
    )
    response = create_twin(client, foreign_mesh)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "TWIN_MESH_OWNERSHIP_REQUIRED"


def test_twin_registers_only_after_mesh_asset_and_validation_release_are_bound(client):
    mesh = register(client)
    response = create_twin(client, mesh)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"
    assert response.json()["subject_id"] == "customer-123"

    replay = create_twin(client, mesh)
    assert replay.status_code == 200
    assert replay.json()["status"] == "replayed"

    changed = create_twin(client, mesh, model_revision="e" * 40)
    assert changed.status_code == 409
    assert changed.json()["detail"]["code"] == "TWIN_ID_IMMUTABLE"


def test_twin_authorization_is_owner_scoped_and_revocable(client):
    mesh = register(client)
    assert create_twin(client, mesh).status_code == 200

    allowed = client.post(
        "/internal/v1/twins/authorize",
        headers=auth(),
        json={"subject_id": "customer-123", "twin_id": "twin-123"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["authorized"] is True

    foreign = client.post(
        "/internal/v1/twins/authorize",
        headers=auth(),
        json={"subject_id": "customer-456", "twin_id": "twin-123"},
    )
    assert foreign.status_code == 403

    revoked = client.post(
        "/internal/v1/twins/revoke",
        headers=auth(),
        json={"subject_id": "customer-123", "twin_id": "twin-123"},
    )
    assert revoked.status_code == 200

    denied = client.post(
        "/internal/v1/twins/authorize",
        headers=auth(),
        json={"subject_id": "customer-123", "twin_id": "twin-123"},
    )
    assert denied.status_code == 403


def test_asset_authorization_binds_person_to_owned_twin_and_garment_to_product(client):
    mesh = register(client)
    assert create_twin(client, mesh).status_code == 200
    person_response = register_person(client)
    assert person_response.status_code == 200
    person_id = person_response.json()["asset_id"]
    garment_response = register_garment(client)
    assert garment_response.status_code == 200
    garment_id = garment_response.json()["asset_id"]

    body = {
        "subject_id": "customer-123",
        "twin_id": "twin-123",
        "product_id": "product-123",
        "person_image_asset_id": person_id,
        "garment_image_asset_id": garment_id,
    }
    allowed = client.post("/internal/v1/assets/authorize", headers=auth(), json=body)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["authorized"] is True

    wrong_product = client.post(
        "/internal/v1/assets/authorize", headers=auth(), json={**body, "product_id": "product-else"}
    )
    assert wrong_product.status_code == 403

    foreign_subject = client.post(
        "/internal/v1/assets/authorize", headers=auth(), json={**body, "subject_id": "customer-456"}
    )
    assert foreign_subject.status_code == 403


def test_private_asset_cannot_cross_tenant_or_be_registered_as_remote_url(client):
    wrong_tenant = client.post(
        "/internal/v1/assets/register",
        headers=auth(),
        json={
            "owner_subject_id": "customer-123",
            "tenant_id": "customer-456",
            "asset_kind": "person_reference",
            "access_scope": "private",
            "twin_id": "twin-123",
            "storage_object_key": "bad-private-key",
            "content_type": "image/jpeg",
            "byte_size": 1024,
            "sha256": "a" * 64,
        },
    )
    remote_key = client.post(
        "/internal/v1/assets/register",
        headers=auth(),
        json={
            "owner_subject_id": "customer-123",
            "tenant_id": "customer-123",
            "asset_kind": "person_reference",
            "access_scope": "private",
            "twin_id": "twin-123",
            "storage_object_key": "https://attacker.invalid/photo.jpg",
            "content_type": "image/jpeg",
            "byte_size": 1024,
            "sha256": "a" * 64,
        },
    )
    assert wrong_tenant.status_code == 422
    assert remote_key.status_code == 422


def test_revoking_owned_mesh_asset_revokes_twin(client):
    mesh = register(client)
    assert create_twin(client, mesh).status_code == 200
    revoked = client.post(
        "/internal/v1/assets/revoke",
        headers=auth(),
        json={"subject_id": "customer-123", "asset_id": mesh},
    )
    assert revoked.status_code == 200
    denied = client.post(
        "/internal/v1/twins/authorize",
        headers=auth(),
        json={"subject_id": "customer-123", "twin_id": "twin-123"},
    )
    assert denied.status_code == 403


def test_readiness_is_not_claimed_without_database(client, monkeypatch):
    monkeypatch.delenv("TWIN_REGISTRY_DATABASE_URL", raising=False)
    response = client.get("/ready", headers=auth())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "TWIN_REGISTRY_DATABASE_NOT_CONFIGURED"



def test_twin_creation_requires_configured_validation_attestation_secret(client, monkeypatch):
    mesh = register(client)
    monkeypatch.delenv("TWIN_REGISTRY_VALIDATION_HMAC_SECRET", raising=False)
    response = create_twin(client, mesh)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "TWIN_VALIDATION_ATTESTATION_NOT_CONFIGURED"


def test_twin_creation_rejects_invalid_validation_attestation(client):
    mesh = register(client)
    body = {
        "twin_id": "twin-invalid",
        "subject_id": "customer-123",
        "mesh_asset_id": mesh,
        "model_id": "cirvanna-avatar-mesh",
        "model_revision": "b" * 40,
        "model_release_sha256": "c" * 64,
        "validation_report_sha256": "d" * 64,
        "validation_attestation_hmac": "0" * 64,
    }
    response = client.post("/internal/v1/twins", headers=auth(), json=body)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "TWIN_VALIDATION_ATTESTATION_INVALID"
