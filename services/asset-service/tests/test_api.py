from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main

TOKEN = "asset-service-test-token-with-more-than-32-bytes"


class FakeObjectStore:
    def __init__(self):
        self.objects = {}

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


def test_health_is_liveness_only(client):
    response, _ = client
    assert response.get("/health").json()["status"] == "alive"


def test_readiness_checks_database_and_object_store(client):
    response, _ = client
    result = response.get("/ready")
    assert result.status_code == 200
    assert result.json()["object_storage"] == "reachable"


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


def test_internal_authentication_is_required(client):
    response, _ = client
    result = response.post(
        "/internal/v1/assets/authorize",
        json={"subject_id": "subject-001", "asset_id": "00000000-0000-4000-8000-000000000001",
              "purpose": "twin_source_image", "parent_id": "twin-001"},
    )
    assert result.status_code == 401
