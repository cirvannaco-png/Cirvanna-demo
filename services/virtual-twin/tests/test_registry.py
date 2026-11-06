from __future__ import annotations

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app import main, registry

TOKEN = "virtual-twin-registry-test-token-with-more-than-32-bytes"
DELETE_TOKEN = "virtual-twin-deletion-test-token-with-more-than-32-bytes"


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'virtual-twin-registry.db'}"
    monkeypatch.setenv("VIRTUAL_TWIN_DATABASE_URL", database_url)
    monkeypatch.setenv("VIRTUAL_TWIN_REGISTRY_TOKEN", TOKEN)
    monkeypatch.setenv("VIRTUAL_TWIN_DELETION_TOKEN", DELETE_TOKEN)
    registry.create_schema_for_tests(database_url)

    async def consent_ok(*_args, **_kwargs):
        return None

    async def assets_ok(*_args, **_kwargs):
        return None

    monkeypatch.setattr(registry, "_verify_consent", consent_ok)
    monkeypatch.setattr(registry, "_authorize_assets", assets_ok)
    return TestClient(main.app)


def headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def registration(**overrides):
    value = {
        "subject_id": "subject-registry-001",
        "twin_id": "twin-registry-001",
        "representation_type": "full_body_mesh",
        "artifact_asset_id": "mesh-asset-001",
        "source_image_asset_ids": ["source-image-001", "source-image-002"],
        "model_version": "mesh-model@sha256:abc123",
        "consent_id": "consent-receipt-0001",
        "consent_version": "privacy-2026-11-v1",
        "idempotency_key": "register-twin-command-001",
    }
    value.update(overrides)
    return value


def test_register_persists_only_full_body_mesh_after_consent_and_asset_checks(client, monkeypatch):
    checked = {"consent": 0, "assets": 0}

    async def consent(*_args, **_kwargs):
        checked["consent"] += 1

    async def assets(*_args, **_kwargs):
        checked["assets"] += 1

    monkeypatch.setattr(registry, "_verify_consent", consent)
    monkeypatch.setattr(registry, "_authorize_assets", assets)

    response = client.post("/internal/v1/twins/register", json=registration(), headers=headers())
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "registered"
    assert data["representation_type"] == "full_body_mesh"
    assert data["version"] == 1
    assert checked == {"consent": 1, "assets": 1}


def test_registry_rejects_pose_skeleton_as_a_persistent_twin(client):
    response = client.post(
        "/internal/v1/twins/register",
        json=registration(representation_type="3d_pose_skeleton"),
        headers=headers(),
    )
    assert response.status_code == 422


@pytest.mark.parametrize("asset_id", [
    "https://example.com/image.png",
    "../private/image.png",
    "/tmp/image.png",
    "file-private-image-001",
])
def test_registry_rejects_external_or_path_asset_references(client, asset_id):
    response = client.post(
        "/internal/v1/twins/register",
        json=registration(artifact_asset_id=asset_id),
        headers=headers(),
    )
    assert response.status_code == 422


def test_registry_requires_matching_verified_consent(client, monkeypatch):
    async def denied(*_args, **_kwargs):
        raise HTTPException(403, detail={"code": "CONSENT_NOT_VERIFIED"})

    monkeypatch.setattr(registry, "_verify_consent", denied)
    response = client.post("/internal/v1/twins/register", json=registration(), headers=headers())
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CONSENT_NOT_VERIFIED"


def test_registry_requires_every_asset_to_be_authorized(client, monkeypatch):
    async def denied(*_args, **_kwargs):
        raise HTTPException(403, detail={"code": "TWIN_ASSET_ACCESS_DENIED"})

    monkeypatch.setattr(registry, "_authorize_assets", denied)
    response = client.post("/internal/v1/twins/register", json=registration(), headers=headers())
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "TWIN_ASSET_ACCESS_DENIED"


def test_registration_idempotency_replays_same_payload_and_rejects_changed_payload(client):
    first = client.post("/internal/v1/twins/register", json=registration(), headers=headers())
    replay = client.post("/internal/v1/twins/register", json=registration(), headers=headers())
    conflict = client.post(
        "/internal/v1/twins/register",
        json=registration(artifact_asset_id="mesh-asset-002"),
        headers=headers(),
    )
    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["status"] == "replayed"
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "TWIN_REGISTRATION_IDEMPOTENCY_CONFLICT"


def test_authorization_is_scoped_to_the_record_owner_and_live_consent(client):
    registered = client.post("/internal/v1/twins/register", json=registration(), headers=headers())
    assert registered.status_code == 201

    wrong_owner = client.post(
        "/internal/v1/twins/authorize",
        json={"subject_id": "subject-registry-999", "twin_id": "twin-registry-001"},
        headers=headers(),
    )
    correct_owner = client.post(
        "/internal/v1/twins/authorize",
        json={"subject_id": "subject-registry-001", "twin_id": "twin-registry-001"},
        headers=headers(),
    )
    assert wrong_owner.status_code == 403
    assert correct_owner.status_code == 200
    assert correct_owner.json()["authorized"] is True
    assert correct_owner.json()["artifact_asset_id"] == "mesh-asset-001"


def test_deactivation_immediately_blocks_authorization_and_queues_asset_deletion(client):
    client.post("/internal/v1/twins/register", json=registration(), headers=headers())
    response = client.post(
        "/internal/v1/twins/deactivate",
        json={
            "subject_id": "subject-registry-001",
            "twin_id": "twin-registry-001",
            "expected_version": 1,
            "command_id": "delete-twin-command-001",
        },
        headers=headers(),
    )
    denied = client.post(
        "/internal/v1/twins/authorize",
        json={"subject_id": "subject-registry-001", "twin_id": "twin-registry-001"},
        headers=headers(),
    )
    status_response = client.get(
        "/internal/v1/twins/twin-registry-001/status?subject_id=subject-registry-001",
        headers=headers(),
    )
    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert denied.status_code == 403
    assert status_response.json()["status"] == "deletion_pending"


def test_deletion_dispatch_marks_complete_only_after_provider_confirms_all_assets(client, monkeypatch):
    client.post("/internal/v1/twins/register", json=registration(), headers=headers())
    client.post(
        "/internal/v1/twins/deactivate",
        json={
            "subject_id": "subject-registry-001",
            "twin_id": "twin-registry-001",
            "expected_version": 1,
            "command_id": "delete-twin-command-002",
        },
        headers=headers(),
    )
    observed = {}

    async def delete_assets(subject_id, asset_ids, idempotency_key):
        observed.update(subject_id=subject_id, asset_ids=asset_ids, idempotency_key=idempotency_key)

    monkeypatch.setattr(registry, "_delete_assets", delete_assets)
    dispatched = client.post(
        "/internal/v1/twins/deletions/dispatch",
        headers={"X-Twin-Deletion-Token": DELETE_TOKEN},
    )
    status_response = client.get(
        "/internal/v1/twins/twin-registry-001/status?subject_id=subject-registry-001",
        headers=headers(),
    )
    assert dispatched.status_code == 200
    assert dispatched.json() == {"processed": 1, "completed": 1, "failed": 0}
    assert set(observed["asset_ids"]) == {"mesh-asset-001", "source-image-001", "source-image-002"}
    assert status_response.json()["status"] == "deleted"


def test_failed_asset_deletion_stays_pending_and_does_not_claim_completion(client, monkeypatch):
    client.post("/internal/v1/twins/register", json=registration(), headers=headers())
    client.post(
        "/internal/v1/twins/deactivate",
        json={
            "subject_id": "subject-registry-001",
            "twin_id": "twin-registry-001",
            "expected_version": 1,
            "command_id": "delete-twin-command-003",
        },
        headers=headers(),
    )

    async def failed(*_args, **_kwargs):
        raise HTTPException(503, detail={"code": "TWIN_ASSET_DELETION_UNAVAILABLE"})

    monkeypatch.setattr(registry, "_delete_assets", failed)
    response = client.post(
        "/internal/v1/twins/deletions/dispatch",
        headers={"X-Twin-Deletion-Token": DELETE_TOKEN},
    )
    status_response = client.get(
        "/internal/v1/twins/twin-registry-001/status?subject_id=subject-registry-001",
        headers=headers(),
    )
    assert response.status_code == 200
    assert response.json()["failed"] == 1
    assert status_response.json()["status"] == "deletion_pending"


def test_consent_revocation_queues_all_active_twins_for_the_receipt(client):
    for idx in (1, 2):
        payload = registration(
            twin_id=f"twin-registry-00{idx}",
            artifact_asset_id=f"mesh-asset-00{idx}",
            idempotency_key=f"register-twin-command-00{idx}",
        )
        assert client.post("/internal/v1/twins/register", json=payload, headers=headers()).status_code == 201

    response = client.post(
        "/internal/v1/twins/revoke-consent",
        json={
            "subject_id": "subject-registry-001",
            "consent_id": "consent-receipt-0001",
            "command_id": "privacy-withdrawal-001",
        },
        headers=headers(),
    )
    assert response.status_code == 202
    assert response.json()["twins_queued"] == 2
