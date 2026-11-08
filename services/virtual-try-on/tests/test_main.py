from __future__ import annotations

import io
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app import main
from app.store import Base, engine, session_factory

TOKEN = "virtual-try-on-test-token-with-more-than-32-bytes"
PERSON_ASSET = "5e7a22a4-2f3b-4fb7-86a2-4a0e83dcf26d"
GARMENT_ASSET = "6e7a22a4-2f3b-4fb7-86a2-4a0e83dcf26d"
OUTPUT_ASSET = "7e7a22a4-2f3b-4fb7-86a2-4a0e83dcf26d"
MODEL_COMMIT = "a" * 40


def png_bytes(color=(30, 90, 150)):
    output = io.BytesIO()
    Image.new("RGB", (128, 160), color).save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "try-on.db")
    monkeypatch.setenv("VIRTUAL_TRY_ON_DATABASE_URL", url)
    monkeypatch.setenv("VIRTUAL_TRY_ON_API_TOKEN", TOKEN)
    engine.cache_clear()
    session_factory.cache_clear()
    Base.metadata.create_all(bind=engine(url))
    test_client = TestClient(main.app)
    yield test_client
    session_factory.cache_clear()
    engine.cache_clear()


def headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def payload(**overrides):
    value = {
        "request_id": "request-test-0001",
        "subject_id": "subject-test-001",
        "twin_id": "twin-test-001",
        "product_id": "product-test-001",
        "person_image_asset_id": PERSON_ASSET,
        "garment_image_asset_id": GARMENT_ASSET,
        "garment_asset_purpose": "catalog_garment_image",
        "garment_category": "upper_body",
        "consent": {
            "consent_id": "consent-test-0001",
            "image_processing": True,
            "virtual_try_on": True,
            "retention_policy": "ephemeral",
        },
    }
    value.update(overrides)
    return value


def install_providers(monkeypatch, *, twin_asset=PERSON_ASSET):
    render_calls = {"count": 0}
    verify_calls = {"count": 0}

    def trusted_base(url_key, token_key):
        return ("https://internal.example.test", "service-token-with-more-than-32-bytes")

    async def verify(request):
        verify_calls["count"] += 1
        return {
            "verified": True,
            "active": True,
            "subject_id": request.subject_id,
            "consent_id": request.consent.consent_id,
            "resource_id": request.twin_id,
            "granted_scopes": ["image_processing", "virtual_try_on", "twin_storage"],
            "consent_version": "consent-v1",
        }

    async def resolve(request):
        return {
            "twin_id": request.twin_id,
            "subject_id": request.subject_id,
            "source_asset_id": twin_asset,
            "status": "active",
        }

    async def read_asset(*, subject_id, asset_id, purpose, parent_id):
        assert subject_id == "subject-test-001"
        if purpose in {"twin_source_image", "try_on_output"}:
            assert parent_id == "twin-test-001"
            return png_bytes(), "image/png"
        assert purpose == "catalog_garment_image"
        assert parent_id == "product-test-001"
        return png_bytes((180, 20, 40)), "image/png"

    async def render(request, person, garment):
        render_calls["count"] += 1
        assert request.garment_category == "upper_body"
        assert person[1] == "image/png"
        assert garment[1] == "image/png"
        return png_bytes((20, 200, 80)), "fashn-vton-1.5@" + MODEL_COMMIT

    async def save_output(request, image_bytes):
        assert image_bytes.startswith(b"\x89PNG")
        return OUTPUT_ASSET

    deleted = []

    async def delete_output(subject_id, twin_id, asset_id):
        deleted.append((subject_id, twin_id, asset_id))

    async def verify_bundle(subject_id, consent_id, twin_id):
        verify_calls["count"] += 1
        assert subject_id == "subject-test-001"
        assert consent_id == "consent-test-0001"
        assert twin_id == "twin-test-001"
        return {"verified": True}

    async def resolve_by_ids(subject_id, twin_id):
        assert subject_id == "subject-test-001"
        assert twin_id == "twin-test-001"
        return {
            "twin_id": twin_id, "subject_id": subject_id,
            "source_image_asset_ids": [twin_asset], "status": "active",
        }

    monkeypatch.setattr(main, "_trusted_base", trusted_base)
    monkeypatch.setattr(main, "_worker_ready", lambda: _ready())
    monkeypatch.setattr(main, "_verify_consent", verify)
    monkeypatch.setattr(main, "_verify_consent_bundle", verify_bundle)
    monkeypatch.setattr(main, "_resolve_twin", resolve)
    monkeypatch.setattr(main, "_resolve_twin_by_ids", resolve_by_ids)
    monkeypatch.setattr(main, "_read_authorized_asset", read_asset)
    monkeypatch.setattr(main, "_render_with_worker", render)
    monkeypatch.setattr(main, "_persist_output_asset", save_output)
    monkeypatch.setattr(main, "_delete_output_asset", delete_output)
    return {"render_calls": render_calls, "verify_calls": verify_calls, "deleted": deleted}


async def _ready():
    return ("https://worker.example.test", "worker-token-with-more-than-32-bytes")


def test_health_is_liveness_only(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == main.SERVICE_NAME


def test_readiness_fails_closed_without_live_dependencies(client, monkeypatch):
    monkeypatch.setattr(main, "_trusted_base", lambda *_args: None)
    monkeypatch.setattr(main, "_worker_ready", _not_ready)
    response = client.get("/ready")
    assert response.status_code == 503
    assert "gpu_renderer" in response.json()["detail"]["missing_dependencies"]
    assert "consent_provider" in response.json()["detail"]["missing_dependencies"]


async def _not_ready():
    return None


def test_capabilities_never_claim_live_rendering_without_dependencies(client, monkeypatch):
    monkeypatch.setattr(main, "_trusted_base", lambda *_args: None)
    monkeypatch.setattr(main, "_worker_ready", _not_ready)
    data = client.get("/capabilities").json()
    assert data["orchestration_api"] is True
    assert data["renderer_configured"] is False
    assert data["consent_verifier_configured"] is False
    assert data["asset_service_configured"] is False
    assert data["output_persistence"] is False


def test_try_on_requires_authentication(client):
    response = client.post("/v1/try-ons", json=payload())
    assert response.status_code == 401


@pytest.mark.parametrize("field", ["image_processing", "virtual_try_on"])
def test_try_on_requires_explicit_consent_flags(client, field):
    body = payload()
    body["consent"][field] = False
    response = client.post("/v1/try-ons", json=body, headers=headers())
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CONSENT_REQUIRED"


@pytest.mark.parametrize("asset_id", [
    "https://example.com/person.jpg",
    "../private/person.jpg",
    "/tmp/person.jpg",
    "file:///tmp/person.jpg",
    "not-a-uuid",
])
def test_external_urls_paths_and_non_opaque_asset_ids_are_rejected(client, asset_id):
    body = payload(person_image_asset_id=asset_id)
    response = client.post("/v1/try-ons", json=body, headers=headers())
    assert response.status_code == 422


def test_wardrobe_asset_requires_exact_parent_binding(client):
    body = payload(garment_asset_purpose="wardrobe_garment_image")
    response = client.post("/v1/try-ons", json=body, headers=headers())
    assert response.status_code == 422


def test_pnelly_look_requires_look_and_wardrobe_versions(client):
    body = payload(look_id="look-001")
    response = client.post("/v1/try-ons", json=body, headers=headers())
    assert response.status_code == 422


def test_try_on_persists_real_renderer_result_and_is_idempotent(client, monkeypatch):
    providers = install_providers(monkeypatch)
    first = client.post("/v1/try-ons", json=payload(), headers=headers())
    replay = client.post("/v1/try-ons", json=payload(), headers=headers())
    assert first.status_code == 200
    assert first.json()["status"] == "complete"
    assert first.json()["renderer_id"] == "fashn-vton-1.5"
    assert first.json()["renderer_version"] == "fashn-vton-1.5@" + MODEL_COMMIT
    assert first.json()["output_asset_id"] == OUTPUT_ASSET
    assert first.json()["output_expires_after_hours"] == 24
    assert replay.status_code == 200
    assert replay.json()["output_asset_id"] == OUTPUT_ASSET
    assert providers["render_calls"]["count"] == 1
    # Consent is verified for both original creation and replay.
    assert providers["verify_calls"]["count"] == 4


def test_changed_payload_under_same_request_id_conflicts(client, monkeypatch):
    install_providers(monkeypatch)
    first = client.post("/v1/try-ons", json=payload(), headers=headers())
    changed = payload(product_id="different-product")
    second = client.post("/v1/try-ons", json=changed, headers=headers())
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "TRY_ON_IDEMPOTENCY_CONFLICT"


def test_try_on_rejects_a_different_twin_source_asset(client, monkeypatch):
    install_providers(monkeypatch, twin_asset="8e7a22a4-2f3b-4fb7-86a2-4a0e83dcf26d")
    response = client.post("/v1/try-ons", json=payload(), headers=headers())
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "TWIN_PERSON_ASSET_MISMATCH"


def test_try_on_requires_resource_bound_active_consent(client, monkeypatch):
    install_providers(monkeypatch)

    async def no_consent(_request):
        raise HTTPException(403, detail={"code": "CONSENT_NOT_VERIFIED"})

    monkeypatch.setattr(main, "_verify_consent", no_consent)
    response = client.post("/v1/try-ons", json=payload(), headers=headers())
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CONSENT_NOT_VERIFIED"


def test_readback_rechecks_consent_and_current_twin_source(client, monkeypatch):
    install_providers(monkeypatch)
    created = client.post("/v1/try-ons", json=payload(), headers=headers())
    assert created.status_code == 200
    request_id = payload()["request_id"]
    result = client.get(
        f"/v1/try-ons/{request_id}",
        headers=headers(),
        params={"subject_id": "subject-test-001"},
    )
    assert result.status_code == 200
    assert result.json()["output_asset_id"] == OUTPUT_ASSET

    async def revoked(*_args):
        raise HTTPException(403, detail={"code": "CONSENT_NOT_VERIFIED"})

    monkeypatch.setattr(main, "_verify_consent_bundle", revoked)
    denied = client.get(
        f"/v1/try-ons/{request_id}",
        headers=headers(),
        params={"subject_id": "subject-test-001"},
    )
    assert denied.status_code == 403


def test_look_render_binds_versions_and_wardrobe_asset_owner(client, monkeypatch):
    install_providers(monkeypatch)

    async def read_asset(*, subject_id, asset_id, purpose, parent_id):
        assert purpose == "wardrobe_garment_image"
        assert parent_id == "wardrobe-item-001"
        return png_bytes(), "image/png"

    monkeypatch.setattr(main, "_read_authorized_asset", read_asset)
    body = payload(
        garment_asset_purpose="wardrobe_garment_image",
        garment_asset_parent_id="wardrobe-item-001",
        look_id="pnelly-look-001",
        look_version=2,
        wardrobe_snapshot_version=17,
    )
    response = client.post("/v1/try-ons", json=body, headers=headers())
    assert response.status_code == 200


def test_private_asset_storage_failure_never_returns_complete(client, monkeypatch):
    install_providers(monkeypatch)

    async def broken_save(*_args):
        raise HTTPException(503, detail={"code": "VTON_OUTPUT_STORAGE_UNAVAILABLE"})

    monkeypatch.setattr(main, "_persist_output_asset", broken_save)
    response = client.post("/v1/try-ons", json=payload(), headers=headers())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "VTON_OUTPUT_STORAGE_UNAVAILABLE"


def test_output_record_persistence_failure_rolls_back_private_output(client, monkeypatch):
    providers = install_providers(monkeypatch)
    from app.store import TryOnStore

    def broken_create(self, data):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(TryOnStore, "complete", broken_create)
    response = client.post("/v1/try-ons", json=payload(), headers=headers())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "TRY_ON_RESULT_PERSISTENCE_FAILED"
    assert providers["deleted"] == [
        ("subject-test-001", "twin-test-001", OUTPUT_ASSET)
    ]


def test_invalid_retention_policy_is_rejected(client):
    body = payload()
    body["consent"]["retention_policy"] = "permanent"
    response = client.post("/v1/try-ons", json=body, headers=headers())
    assert response.status_code == 422
