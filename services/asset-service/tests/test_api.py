from __future__ import annotations

import io
import json
import struct
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main

TOKEN = "asset-service-test-token-with-more-than-32-bytes"


class FakeObjectStore:
    def __init__(self):
        self.objects = {}
        self.private_controls_valid = True

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
    assert result.json()["private_access"] == "verified"


def test_readiness_fails_closed_when_bucket_privacy_controls_are_missing(client):
    response, fake = client
    fake.private_controls_valid = False
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
