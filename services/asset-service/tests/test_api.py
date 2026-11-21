from __future__ import annotations

import io
import json
import struct
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.exc import IntegrityError

from app import main

TOKEN = "asset-service-test-token-with-more-than-32-bytes"


class FakeObjectStore:
    def __init__(self):
        self.objects = {}
        self.private_controls_valid = True
        self.versioning_status = None

    def put_object(self, *, Bucket, Key, Body, ContentType, Metadata):
        self.objects[(Bucket, Key)] = bytes(Body)

    def get_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise KeyError("not found")
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def head_bucket(self, *, Bucket):
        return {}

    def get_public_access_block(self, *, Bucket):
        value = self.private_controls_valid
        return {"PublicAccessBlockConfiguration": {
            "BlockPublicAcls": value,
            "IgnorePublicAcls": value,
            "BlockPublicPolicy": value,
            "RestrictPublicBuckets": value,
        }}

    def get_bucket_policy_status(self, *, Bucket):
        return {"PolicyStatus": {"IsPublic": not self.private_controls_valid}}

    def get_bucket_encryption(self, *, Bucket):
        rules = [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}] if self.private_controls_valid else []
        return {"ServerSideEncryptionConfiguration": {"Rules": rules}}

    def get_bucket_ownership_controls(self, *, Bucket):
        rules = [{"ObjectOwnership": "BucketOwnerEnforced"}] if self.private_controls_valid else []
        return {"OwnershipControls": {"Rules": rules}}

    def get_bucket_versioning(self, *, Bucket):
        return {"Status": self.versioning_status} if self.versioning_status else {}


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "assets.db")
    monkeypatch.setenv("ASSET_DATABASE_URL", url)
    monkeypatch.setenv("ASSET_SERVICE_TOKEN", TOKEN)
    monkeypatch.setenv("ASSET_S3_BUCKET", "cirvanna-test")
    monkeypatch.setenv("ASSET_S3_ACCESS_KEY_ID", "local-access")
    monkeypatch.setenv("ASSET_S3_SECRET_ACCESS_KEY", "local-secret-key-long-enough")
    fake = FakeObjectStore()
    monkeypatch.setattr(main, "_object_store", lambda: (fake, "cirvanna-test"))
    main._engine.cache_clear()
    main._sessions.cache_clear()
    main.Base.metadata.create_all(bind=main._engine(url))
    main.app.state.asset_test_database_url = url
    with TestClient(main.app) as test_client:
        yield test_client, fake
    main._sessions.cache_clear()
    main._engine.cache_clear()


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def png():
    output = io.BytesIO()
    Image.new("RGB", (128, 160), (80, 120, 180)).save(output, format="PNG")
    return output.getvalue()


def upload(client, **overrides):
    data = {
        "owner_user_id": "subject-001",
        "purpose": "twin_source_image",
        "parent_id": "twin-001",
    }
    data.update(overrides)
    return client.post(
        "/internal/v1/assets",
        headers=auth(),
        data=data,
        files={"file": ("portrait.png", png(), "image/png")},
    )


def glb(*, external_buffer_uri: str | None = None) -> bytes:
    binary = struct.pack("<9f", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    buffer = {"byteLength": len(binary)}
    if external_buffer_uri is not None:
        buffer["uri"] = external_buffer_uri
    document = {
        "asset": {"version": "2.0", "generator": "Cirvanna GLB contract test"},
        "buffers": [buffer],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(binary)}],
        "accessors": [{"bufferView": 0, "byteOffset": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "mode": 4}]}],
    }
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((-len(json_chunk)) % 4)
    total = 12 + 8 + len(json_chunk) + 8 + len(binary)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A) + json_chunk
        + struct.pack("<II", len(binary), 0x004E4942) + binary
    )


def upload_mesh(client, *, owner_user_id="subject-001", parent_id="twin-001", content=None, content_type="model/gltf-binary"):
    return client.post(
        "/internal/v1/twin-meshes",
        headers=auth(),
        data={"owner_user_id": owner_user_id, "parent_id": parent_id},
        files={"file": ("twin.glb", content if content is not None else glb(), content_type)},
    )


def test_health_is_liveness_only(client):
    response, _ = client
    assert response.get("/health").json()["status"] == "alive"


def test_readiness_checks_database_and_object_store(client):
    response, _ = client
    result = response.get("/ready")
    assert result.status_code == 200
    assert result.json()["object_storage"] == "reachable"
    assert result.json()["object_versioning"] == "disabled"
    assert result.json()["private_access"] == "verified"


def test_readiness_fails_closed_when_bucket_privacy_controls_are_missing(client):
    response, fake = client
    fake.private_controls_valid = False
    result = response.get("/ready")
    assert result.status_code == 503
    assert result.json()["detail"]["reason"] == "private_bucket_controls_unverified"


@pytest.mark.parametrize("status", ["Enabled", "Suspended"])
def test_readiness_fails_closed_when_bucket_versioning_can_retain_old_objects(client, status):
    response, fake = client
    fake.versioning_status = status
    result = response.get("/ready")
    assert result.status_code == 503
    assert result.json()["detail"]["reason"] == "private_bucket_controls_unverified"


def test_upload_normalizes_and_returns_only_opaque_asset_metadata(client):
    response, fake = client
    result = upload(response)
    assert result.status_code == 201
    data = result.json()
    assert data["owner_user_id"] == "subject-001"
    assert data["purpose"] == "twin_source_image"
    assert data["parent_id"] == "twin-001"
    assert data["content_type"] == "image/png"
    assert len(data["sha256"]) == 64
    assert "object_key" not in data
    assert len(fake.objects) == 1


def test_twin_mesh_upload_stores_a_private_glb_without_image_normalization(client):
    response, fake = client
    raw = glb()
    result = upload_mesh(response, content=raw)
    assert result.status_code == 201, result.text
    metadata = result.json()
    assert metadata["purpose"] == "twin_representation"
    assert metadata["content_type"] == "model/gltf-binary"
    assert metadata["byte_size"] == len(raw)
    assert metadata["sha256"] == __import__("hashlib").sha256(raw).hexdigest()
    assert metadata["asset_role"] == "representation"
    assert metadata["publication_scope"] == "private_only"
    assert metadata["publication_state"] == "private_only"
    assert "object_key" not in metadata
    stored = next(iter(fake.objects.values()))
    assert stored == raw
    assert stored.startswith(b"glTF")


def test_twin_mesh_upload_rejects_non_glb_and_external_buffer_references(client):
    response, _ = client
    wrong_type = upload_mesh(response, content=glb(), content_type="application/octet-stream")
    wrong_magic = upload_mesh(response, content=b"not-a-glb-container", content_type="model/gltf-binary")
    external = upload_mesh(response, content=glb(external_buffer_uri="https://example.test/body.bin"))
    nonfinite_document = json.dumps({"asset": {"version": "2.0"}, "invalid": float("nan")}, separators=(",", ":")).encode()
    nonfinite_document += b" " * ((-len(nonfinite_document)) % 4)
    nonfinite_total = 12 + 8 + len(nonfinite_document)
    nonfinite = struct.pack("<4sII", b"glTF", 2, nonfinite_total) + struct.pack("<II", len(nonfinite_document), 0x4E4F534A) + nonfinite_document
    bad_json = upload_mesh(response, content=nonfinite)
    assert wrong_type.status_code == 415
    assert wrong_type.json()["detail"]["code"] == "UNSUPPORTED_TWIN_MESH_TYPE"
    assert wrong_magic.status_code == 422
    assert external.status_code == 422
    assert external.json()["detail"]["code"] == "INVALID_GLB_CONTAINER"
    assert bad_json.status_code == 422
    assert bad_json.json()["detail"]["code"] == "INVALID_GLB_CONTAINER"


def test_twin_mesh_upload_enforces_independent_size_limit(client, monkeypatch):
    response, _ = client
    monkeypatch.setattr(main, "MAX_TWIN_MESH_BYTES", 32)
    result = upload_mesh(response, content=b"g" * 33)
    assert result.status_code == 413
    assert result.json()["detail"]["code"] == "TWIN_MESH_SIZE_LIMIT_EXCEEDED"


def test_image_upload_route_cannot_store_a_twin_representation(client):
    response, _ = client
    result = upload(response, purpose="twin_representation")
    assert result.status_code == 422
    assert result.json()["detail"]["code"] == "MESH_UPLOAD_REQUIRES_GLB_ENDPOINT"


def test_twin_mesh_bytes_require_exact_owner_purpose_and_parent(client):
    response, _ = client
    mesh = upload_mesh(response).json()["asset_id"]
    allowed = response.get(
        f"/internal/v1/assets/{mesh}/content", headers=auth(),
        params={"subject_id": "subject-001", "purpose": "twin_representation", "parent_id": "twin-001"},
    )
    wrong_owner = response.get(
        f"/internal/v1/assets/{mesh}/content", headers=auth(),
        params={"subject_id": "subject-002", "purpose": "twin_representation", "parent_id": "twin-001"},
    )
    wrong_parent = response.get(
        f"/internal/v1/assets/{mesh}/content", headers=auth(),
        params={"subject_id": "subject-001", "purpose": "twin_representation", "parent_id": "twin-002"},
    )
    assert allowed.status_code == 200
    assert allowed.headers["cache-control"] == "no-store, private"
    assert allowed.headers["content-type"].startswith("model/gltf-binary")
    assert allowed.content == glb()
    assert wrong_owner.status_code == 404
    assert wrong_parent.status_code == 404


def test_authorization_requires_exact_subject_purpose_and_parent(client):
    response, _ = client
    asset_id = upload(response).json()["asset_id"]
    allowed = response.post("/internal/v1/assets/authorize", headers=auth(), json={
        "subject_id": "subject-001", "asset_id": asset_id,
        "purpose": "twin_source_image", "parent_id": "twin-001",
    })
    cross_user = response.post("/internal/v1/assets/authorize", headers=auth(), json={
        "subject_id": "subject-002", "asset_id": asset_id,
        "purpose": "twin_source_image", "parent_id": "twin-001",
    })
    wrong_parent = response.post("/internal/v1/assets/authorize", headers=auth(), json={
        "subject_id": "subject-001", "asset_id": asset_id,
        "purpose": "twin_source_image", "parent_id": "twin-002",
    })
    wrong_purpose = response.post("/internal/v1/assets/authorize", headers=auth(), json={
        "subject_id": "subject-001", "asset_id": asset_id,
        "purpose": "try_on_output", "parent_id": "twin-001",
    })
    assert allowed.status_code == 200
    assert allowed.json()["asset_role"] == "source"
    assert allowed.json()["publication_scope"] == "private_only"
    assert allowed.json()["publication_state"] == "private_only"
    assert allowed.json()["consent_receipt_id"] is None
    assert cross_user.status_code == 404
    assert wrong_parent.status_code == 404
    assert wrong_purpose.status_code == 404


def test_appearance_source_and_render_assets_are_owner_parent_bound(client):
    response, _ = client
    source = upload(response, purpose="appearance_source_image", parent_id="look-001").json()["asset_id"]
    render = upload(response, purpose="appearance_render_output", parent_id="look-001").json()["asset_id"]
    for asset_id, purpose in ((source, "appearance_source_image"), (render, "appearance_render_output")):
        allowed = response.post("/internal/v1/assets/authorize", headers=auth(), json={
            "subject_id": "subject-001", "asset_id": asset_id,
            "purpose": purpose, "parent_id": "look-001",
        })
        wrong_parent = response.post("/internal/v1/assets/authorize", headers=auth(), json={
            "subject_id": "subject-001", "asset_id": asset_id,
            "purpose": purpose, "parent_id": "look-002",
        })
        assert allowed.status_code == 200
        assert wrong_parent.status_code == 404

def test_bulk_twin_authorization_requires_exact_owner_parent_and_asset_purposes(client):
    response, _ = client
    source = upload(response).json()["asset_id"]
    mesh = upload_mesh(response).json()["asset_id"]
    allowed = response.post("/internal/v1/assets/authorize", headers=auth(), json={
        "subject_id": "subject-001", "asset_ids": [source, mesh],
        "purpose": "virtual_twin_storage", "parent_id": "twin-001",
    })
    wrong_parent = response.post("/internal/v1/assets/authorize", headers=auth(), json={
        "subject_id": "subject-001", "asset_ids": [source, mesh],
        "purpose": "virtual_twin_storage", "parent_id": "twin-002",
    })
    wrong_owner = response.post("/internal/v1/assets/authorize", headers=auth(), json={
        "subject_id": "subject-002", "asset_ids": [source, mesh],
        "purpose": "virtual_twin_storage", "parent_id": "twin-001",
    })
    assert allowed.status_code == 200
    assert allowed.json()["authorized_asset_ids"] == sorted([source, mesh])
    assert all(asset["publication_state"] == "private_only" for asset in allowed.json()["assets"])
    assert wrong_parent.status_code == 404
    assert wrong_owner.status_code == 404

def test_bulk_twin_authorization_requires_one_glb_and_source_images(client):
    response, _ = client
    source = upload(response).json()["asset_id"]
    first_mesh = upload_mesh(response).json()["asset_id"]
    second_mesh = upload_mesh(response).json()["asset_id"]
    result = response.post("/internal/v1/assets/authorize", headers=auth(), json={
        "subject_id": "subject-001", "asset_ids": [source, first_mesh, second_mesh],
        "purpose": "virtual_twin_storage", "parent_id": "twin-001",
    })
    assert result.status_code == 404
    assert result.json()["detail"]["code"] == "ASSET_NOT_FOUND"


def test_bulk_twin_deletion_cascades_derived_assets_and_is_idempotent(client):
    response, fake = client
    source = upload(response).json()["asset_id"]
    mesh = upload_mesh(response).json()["asset_id"]
    output = upload(response, purpose="try_on_output", retention_days="1").json()["asset_id"]
    payload = {
        "subject_id": "subject-001", "asset_ids": [source, mesh],
        "parent_id": "twin-001", "purpose": "virtual_twin_deletion",
        "cascade_derived_assets": True, "idempotency_key": "delete-twin-command-001",
    }
    first = response.post("/internal/v1/assets/delete", headers=auth(), json=payload)
    replay = response.post("/internal/v1/assets/delete", headers=auth(), json=payload)
    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json()["deleted"] is True
    assert set(first.json()["deleted_asset_ids"]) == {source, mesh, output}
    assert first.json()["deleted_asset_ids"] == replay.json()["deleted_asset_ids"]
    assert fake.objects == {}
def test_asset_bytes_are_returned_only_with_owner_and_resource_binding(client):
    response, _ = client
    asset_id = upload(response).json()["asset_id"]
    allowed = response.get(
        f"/internal/v1/assets/{asset_id}/content",
        headers=auth(),
        params={"subject_id": "subject-001", "purpose": "twin_source_image", "parent_id": "twin-001"},
    )
    denied = response.get(
        f"/internal/v1/assets/{asset_id}/content",
        headers=auth(),
        params={"subject_id": "subject-002", "purpose": "twin_source_image", "parent_id": "twin-001"},
    )
    assert allowed.status_code == 200
    assert allowed.headers["cache-control"] == "no-store, private"
    assert allowed.content.startswith(b"\x89PNG")
    assert denied.status_code == 404


def test_delete_is_owner_scoped_and_idempotent(client):
    response, fake = client
    asset_id = upload(response).json()["asset_id"]
    headers = {**auth(), "X-Asset-Owner-ID": "subject-001", "Idempotency-Key": "delete-command-001"}
    first = response.delete(f"/v1/assets/{asset_id}", headers=headers)
    second = response.delete(f"/v1/assets/{asset_id}", headers=headers)
    assert first.status_code == 204
    assert second.status_code == 204
    assert fake.objects == {}
    read = response.get(
        f"/internal/v1/assets/{asset_id}/content", headers=auth(),
        params={"subject_id": "subject-001", "purpose": "twin_source_image", "parent_id": "twin-001"},
    )
    assert read.status_code == 404


def test_unsupported_and_invalid_image_data_are_rejected(client):
    response, _ = client
    bad_type = response.post(
        "/internal/v1/assets", headers=auth(),
        data={"owner_user_id": "subject-001", "purpose": "twin_source_image", "parent_id": "twin-001"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    bad_image = response.post(
        "/internal/v1/assets", headers=auth(),
        data={"owner_user_id": "subject-001", "purpose": "twin_source_image", "parent_id": "twin-001"},
        files={"file": ("portrait.png", b"not-image", "image/png")},
    )
    assert bad_type.status_code == 415
    assert bad_image.status_code == 422




def test_parent_delete_removes_all_assets_for_one_owner_and_parent(client):
    response, fake = client
    first = upload(response, parent_id="twin-batch-001").json()["asset_id"]
    second = upload(response, parent_id="twin-batch-001", purpose="twin_person_image").json()["asset_id"]
    other_owner = upload(response, owner_user_id="subject-002", parent_id="twin-batch-001").json()["asset_id"]
    deleted = response.delete(
        "/internal/v1/assets/by-parent/twin-batch-001",
        headers=auth(),
        params={"owner_user_id": "subject-001"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted_count"] == 2
    assert len(fake.objects) == 1
    still_owned = response.get(
        f"/internal/v1/assets/{other_owner}/content",
        headers=auth(),
        params={"subject_id": "subject-002", "purpose": "twin_source_image", "parent_id": "twin-batch-001"},
    )
    assert still_owned.status_code == 200
    for deleted_id in (first, second):
        not_found = response.get(
            f"/internal/v1/assets/{deleted_id}/content",
            headers=auth(),
            params={"subject_id": "subject-001", "purpose": "twin_source_image", "parent_id": "twin-batch-001"},
        )
        assert not_found.status_code == 404


def test_expiry_sweeper_physically_deletes_expired_output_assets(client, monkeypatch):
    response, fake = client
    created = upload(
        response,
        purpose="try_on_output",
        parent_id="twin-expiring-001",
        retention_days="1",
    )
    assert created.status_code == 201
    asset_id = created.json()["asset_id"]
    database_url = response.app.state.asset_test_database_url
    with main._sessions(database_url)() as db:
        row = db.get(main.AssetRow, asset_id)
        row.retention_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    monkeypatch.setenv("ASSET_CRON_TOKEN", "asset-cron-token-with-at-least-32-bytes")
    purged = response.post(
        "/internal/v1/assets/purge-expired",
        headers={**auth(), "X-Asset-Cron-Token": "asset-cron-token-with-at-least-32-bytes"},
    )
    assert purged.status_code == 200
    assert purged.json()["purged_count"] == 1
    assert fake.objects == {}
    read = response.get(
        f"/internal/v1/assets/{asset_id}/content",
        headers=auth(),
        params={"subject_id": "subject-001", "purpose": "try_on_output", "parent_id": "twin-expiring-001"},
    )
    assert read.status_code == 404


def test_internal_authentication_is_required(client):
    response, _ = client
    result = response.post(
        "/internal/v1/assets/authorize",
        json={"subject_id": "subject-001", "asset_id": "00000000-0000-4000-8000-000000000001",
              "purpose": "twin_source_image", "parent_id": "twin-001"},
    )
    assert result.status_code == 401



def test_asset_lifecycle_metadata_classifies_assets_and_defaults_to_private_only(client):
    response, _ = client
    source_result = upload(response)
    derivative_result = upload(
        response, purpose="try_on_output", parent_id="try-on-001", retention_days="2"
    )
    assert source_result.status_code == 201
    assert derivative_result.status_code == 201
    source = source_result.json()
    derivative = derivative_result.json()

    assert source["asset_role"] == "source"
    assert len(source["source_sha256"]) == 64
    assert source["publication_scope"] == "private_only"
    assert source["publication_state"] == "private_only"

    assert derivative["asset_role"] == "derivative"
    assert derivative["source_sha256"] is None
    assert derivative["publication_scope"] == "private_only"
    assert derivative["publication_state"] == "private_only"

    database_url = response.app.state.asset_test_database_url
    with main._sessions(database_url)() as db:
        stored = db.get(main.AssetRow, derivative["asset_id"])
        assert stored.source_asset_id is None
        assert stored.transformation_name is None
        assert stored.transformation_version is None
        assert stored.consent_receipt_id is None
        assert stored.masking_attestation_id is None
        assert stored.revoked_at is None


def test_personal_media_cannot_be_marked_public_without_consent_and_masking_evidence(client):
    response, _ = client
    created = upload(response, purpose="appearance_source_image", parent_id="look-private-001")
    assert created.status_code == 201
    asset_id = created.json()["asset_id"]
    database_url = response.app.state.asset_test_database_url

    with main._sessions(database_url)() as db:
        row = db.get(main.AssetRow, asset_id)
        row.publication_scope = "approved_public"
        row.publication_state = "approved"
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    with main._sessions(database_url)() as db:
        unchanged = db.get(main.AssetRow, asset_id)
        assert unchanged.publication_scope == "private_only"
        assert unchanged.publication_state == "private_only"


def test_revocation_state_requires_revocation_timestamp(client):
    response, _ = client
    created = upload(response)
    asset_id = created.json()["asset_id"]
    database_url = response.app.state.asset_test_database_url

    with main._sessions(database_url)() as db:
        row = db.get(main.AssetRow, asset_id)
        row.publication_state = "revoked"
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()



def test_publication_approval_requires_exact_asset_consent_attestation_and_surface(client, monkeypatch):
    response, _ = client
    created = upload(response, purpose="appearance_source_image", parent_id="look-public-001")
    assert created.status_code == 201
    asset = created.json()
    calls = []

    async def approve(payload):
        calls.append(payload)
        return {
            "decision": "PASS",
            "asset_id": asset["asset_id"],
            "asset_sha256": asset["sha256"],
            "subject_id": "subject-001",
            "consent_id": "consent-public-001",
            "consent_resource_id": asset["asset_id"],
            "photographed_people_status": "no_people",
            "consent_version": "click-it-privacy-v1",
            "human_privacy_review_passed": True,
            "masking_model_sha256": "a" * 64,
            "human_privacy_review_receipt_id": "human-review-receipt-001",
            "human_privacy_reviewer_ref": "reviewer-ref-001",
            "human_privacy_reviewed_at": datetime.now(timezone.utc).isoformat(),
            "masking_attestation_id": "masking-attestation-001",
            "target_surface": "shared_link",
        }

    monkeypatch.setattr(main, "_evaluate_publication_with_privacy_governance", approve)
    approved = response.post(
        f"/internal/v1/assets/{asset['asset_id']}/publication/approve",
        headers=auth(),
        json={
            "subject_id": "subject-001",
            "consent_id": "consent-public-001",
            "masking_attestation_id": "masking-attestation-001",
            "target_surface": "shared_link",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["decision"] == "APPROVED"
    assert approved.json()["publication_state"] == "approved"
    assert approved.json()["publication_surface"] == "shared_link"
    assert approved.json()["consent_receipt_id"] == "consent-public-001"
    assert approved.json()["masking_attestation_id"] == "masking-attestation-001"
    assert approved.json()["consent_version"] == "click-it-privacy-v1"
    assert approved.json()["masking_model_sha256"] == "a" * 64
    assert approved.json()["human_privacy_review_receipt_id"] == "human-review-receipt-001"
    assert approved.json()["human_privacy_reviewer_ref"] == "reviewer-ref-001"
    assert approved.json()["human_privacy_reviewed_at"] is not None
    assert calls[0]["asset_sha256"] == asset["sha256"]

    database_url = response.app.state.asset_test_database_url
    with main._sessions(database_url)() as db:
        stored = db.get(main.AssetRow, asset["asset_id"])
        assert stored.publication_surface == "shared_link"
        assert stored.publication_state == "approved"


def test_publication_approval_rejects_a_mismatched_privacy_gate_decision(client, monkeypatch):
    response, _ = client
    asset = upload(response, purpose="appearance_source_image", parent_id="look-public-002").json()

    async def mismatched(_payload):
        return {
            "decision": "PASS",
            "asset_id": asset["asset_id"],
            "asset_sha256": "0" * 64,
            "subject_id": "subject-001",
            "consent_id": "consent-public-002",
            "consent_resource_id": asset["asset_id"],
            "photographed_people_status": "no_people",
            "consent_version": "click-it-privacy-v1",
            "human_privacy_review_passed": True,
            "masking_model_sha256": "a" * 64,
            "human_privacy_review_receipt_id": "human-review-receipt-001",
            "human_privacy_reviewer_ref": "reviewer-ref-001",
            "human_privacy_reviewed_at": datetime.now(timezone.utc).isoformat(),
            "masking_attestation_id": "masking-attestation-002",
            "target_surface": "marketplace",
        }

    monkeypatch.setattr(main, "_evaluate_publication_with_privacy_governance", mismatched)
    result = response.post(
        f"/internal/v1/assets/{asset['asset_id']}/publication/approve",
        headers=auth(),
        json={
            "subject_id": "subject-001",
            "consent_id": "consent-public-002",
            "masking_attestation_id": "masking-attestation-002",
            "target_surface": "marketplace",
        },
    )
    assert result.status_code == 403
    assert result.json()["detail"]["code"] == "PUBLICATION_PRIVACY_DECISION_MISMATCH"


def test_publication_revocation_is_idempotent_and_removes_public_scope(client, monkeypatch):
    response, _ = client
    asset = upload(response, purpose="appearance_source_image", parent_id="look-public-003").json()

    async def approve(payload):
        return {
            "decision": "PASS",
            "asset_id": asset["asset_id"],
            "asset_sha256": asset["sha256"],
            "subject_id": "subject-001",
            "consent_id": "consent-public-003",
            "consent_resource_id": asset["asset_id"],
            "photographed_people_status": "no_people",
            "consent_version": "click-it-privacy-v1",
            "human_privacy_review_passed": True,
            "masking_model_sha256": "a" * 64,
            "human_privacy_review_receipt_id": "human-review-receipt-001",
            "human_privacy_reviewer_ref": "reviewer-ref-001",
            "human_privacy_reviewed_at": datetime.now(timezone.utc).isoformat(),
            "masking_attestation_id": "masking-attestation-003",
            "target_surface": "public_profile",
        }

    monkeypatch.setattr(main, "_evaluate_publication_with_privacy_governance", approve)
    approved = response.post(
        f"/internal/v1/assets/{asset['asset_id']}/publication/approve",
        headers=auth(),
        json={
            "subject_id": "subject-001",
            "consent_id": "consent-public-003",
            "masking_attestation_id": "masking-attestation-003",
            "target_surface": "public_profile",
        },
    )
    assert approved.status_code == 200
    revoke = response.post(
        f"/internal/v1/assets/{asset['asset_id']}/publication/revoke",
        headers=auth(),
        json={"subject_id": "subject-001", "reason_code": "consent_revoked"},
    )
    again = response.post(
        f"/internal/v1/assets/{asset['asset_id']}/publication/revoke",
        headers=auth(),
        json={"subject_id": "subject-001", "reason_code": "consent_revoked"},
    )
    assert revoke.status_code == 200
    assert revoke.json()["publication_scope"] == "private_only"
    assert revoke.json()["publication_state"] == "revoked"
    assert revoke.json()["revoked_at"] is not None
    assert again.status_code == 200
    assert again.json()["revoked_at"] == revoke.json()["revoked_at"]



def test_expired_asset_cannot_enter_publication_approval(client, monkeypatch):
    response, _ = client
    asset = upload(
        response, purpose="appearance_source_image",
        parent_id="look-expired-001", retention_days="1",
    ).json()
    database_url = response.app.state.asset_test_database_url
    with main._sessions(database_url)() as db:
        row = db.get(main.AssetRow, asset["asset_id"])
        row.retention_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

    async def must_not_call(_payload):
        raise AssertionError("expired asset must be rejected before privacy gate invocation")

    monkeypatch.setattr(main, "_evaluate_publication_with_privacy_governance", must_not_call)
    result = response.post(
        f"/internal/v1/assets/{asset['asset_id']}/publication/approve",
        headers=auth(),
        json={
            "subject_id": "subject-001",
            "consent_id": "consent-expired-001",
            "masking_attestation_id": "masking-attestation-expired",
            "target_surface": "shared_link",
        },
    )
    assert result.status_code == 404
    assert result.json()["detail"]["code"] == "ASSET_NOT_FOUND"



def test_deleting_approved_asset_revokes_publication_metadata(client, monkeypatch):
    response, _ = client
    asset = upload(response, purpose="appearance_source_image", parent_id="look-delete-published-001").json()

    async def approve(_payload):
        return {
            "decision": "PASS",
            "asset_id": asset["asset_id"],
            "asset_sha256": asset["sha256"],
            "subject_id": "subject-001",
            "consent_id": "consent-delete-published-001",
            "consent_resource_id": asset["asset_id"],
            "photographed_people_status": "no_people",
            "consent_version": "click-it-privacy-v1",
            "human_privacy_review_passed": True,
            "masking_model_sha256": "a" * 64,
            "human_privacy_review_receipt_id": "human-review-receipt-001",
            "human_privacy_reviewer_ref": "reviewer-ref-001",
            "human_privacy_reviewed_at": datetime.now(timezone.utc).isoformat(),
            "masking_attestation_id": "masking-delete-published-001",
            "target_surface": "shared_link",
        }

    monkeypatch.setattr(main, "_evaluate_publication_with_privacy_governance", approve)
    approved = response.post(
        f"/internal/v1/assets/{asset['asset_id']}/publication/approve",
        headers=auth(),
        json={
            "subject_id": "subject-001",
            "consent_id": "consent-delete-published-001",
            "masking_attestation_id": "masking-delete-published-001",
            "target_surface": "shared_link",
        },
    )
    assert approved.status_code == 200
    deleted = response.delete(
        f"/v1/assets/{asset['asset_id']}",
        headers={
            **auth(),
            "X-Asset-Owner-ID": "subject-001",
            "Idempotency-Key": "delete-published-001",
        },
    )
    assert deleted.status_code == 204
    database_url = response.app.state.asset_test_database_url
    with main._sessions(database_url)() as db:
        stored = db.get(main.AssetRow, asset["asset_id"])
        assert stored.status == "deleted"
        assert stored.publication_scope == "private_only"
        assert stored.publication_state == "revoked"
        assert stored.revoked_at is not None



def test_twin_mesh_representation_can_never_be_approved_for_publication(client):
    response, _ = client
    mesh = upload_mesh(response).json()
    database_url = response.app.state.asset_test_database_url
    with main._sessions(database_url)() as db:
        row = db.get(main.AssetRow, mesh["asset_id"])
        row.publication_scope = "approved_public"
        row.publication_state = "approved"
        row.publication_surface = "public_profile"
        row.consent_receipt_id = "consent-mesh-public-001"
        row.consent_version = "click-it-privacy-v1"
        row.masking_attestation_id = "masking-mesh-public-001"
        row.masking_model_sha256 = "a" * 64
        row.human_privacy_review_receipt_id = "human-review-mesh-001"
        row.human_privacy_reviewer_ref = "reviewer-mesh-001"
        row.human_privacy_reviewed_at = datetime.now(timezone.utc)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()



def test_publication_approval_uses_authenticated_nonredirecting_privacy_service_call(client, monkeypatch):
    response, _ = client
    asset = upload(response, purpose="appearance_source_image", parent_id="look-http-gate-001").json()
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_URL", "https://privacy-governance.internal")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_TOKEN", "privacy-governance-token-with-more-than-32-bytes")
    calls = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "decision": "PASS",
                "asset_id": asset["asset_id"],
                "asset_sha256": asset["sha256"],
                "subject_id": "subject-001",
                "consent_id": "consent-http-gate-001",
                "consent_resource_id": asset["asset_id"],
                "photographed_people_status": "no_people",
                "consent_version": "click-it-privacy-v1",
                "human_privacy_review_passed": True,
                "masking_model_sha256": "a" * 64,
                "human_privacy_review_receipt_id": "human-review-http-001",
                "human_privacy_reviewer_ref": "reviewer-http-001",
                "human_privacy_reviewed_at": datetime.now(timezone.utc).isoformat(),
                "masking_attestation_id": "masking-http-gate-001",
                "target_surface": "marketplace",
            }

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False
            assert kwargs["follow_redirects"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse()

    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)
    result = response.post(
        f"/internal/v1/assets/{asset['asset_id']}/publication/approve",
        headers=auth(),
        json={
            "subject_id": "subject-001",
            "consent_id": "consent-http-gate-001",
            "masking_attestation_id": "masking-http-gate-001",
            "target_surface": "marketplace",
        },
    )
    assert result.status_code == 200, result.text
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == "https://privacy-governance.internal/internal/v1/privacy/assets/publication/evaluate"
    assert kwargs["headers"]["Authorization"] == "Bearer privacy-governance-token-with-more-than-32-bytes"
    assert kwargs["json"]["asset_id"] == asset["asset_id"]
    assert kwargs["json"]["asset_sha256"] == asset["sha256"]
    assert kwargs["json"]["consent_id"] == "consent-http-gate-001"
