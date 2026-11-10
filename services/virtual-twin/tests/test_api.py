from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app import main
from app.main import app

client = TestClient(app)
SUBJECT = "customer-123"
CONSENT = "consent-record-0001"
TOKEN = "virtual-twin-test-bearer-token-longer-than-thirty-two-bytes"


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def identity_fields():
    return {"subject_id": SUBJECT, "consent_id": CONSENT, "resource_id": "resource-click-it-123", "photographed_people_status": "no_people"}


def mock_internal_config(monkeypatch, *, consent=True, twin_registry=True, vision=True):
    def config(url_name, token_name):
        if url_name == "CONSENT_API_URL":
            return ("https://consent.example.test", "c" * 40) if consent else None
        if url_name == "TWIN_REGISTRY_API_URL":
            return ("https://twins.example.test", "t" * 40) if twin_registry else None
        if url_name == "VISION_INTELLIGENCE_API_URL":
            return ("https://vision.example.test", "v" * 40) if vision else None
        return None
    monkeypatch.setattr(main, "_internal_config", config)


def test_health_is_liveness_only():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "alive", "service": "cirvanna-virtual-twin"}


def test_capabilities_do_not_claim_mesh_measurement_or_cal_is_available(monkeypatch):
    monkeypatch.setattr(main, "_vision_worker_ready", lambda: _false())
    response = client.get("/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["body_reconstruction"] is False
    assert data["full_surface_mesh"] is False
    assert data["calibrated_body_measurements"] is False
    assert data["click_it_product_reconstruction"] is False
    assert data["decision_governance_connected_to_rendering"] is False



def test_pose_only_provider_does_not_advertise_persistent_twin(monkeypatch):
    mock_internal_config(monkeypatch, consent=True, twin_registry=True, vision=True)

    async def ready():
        return True

    monkeypatch.setattr(main, "_vision_worker_ready", ready)
    data = client.get("/capabilities").json()
    assert data["pose_skeleton_inference"] is True
    assert data["twin_generation"] is False
    assert data["persistent_twin_generation"] is False
    assert data["persistent_twin_preview"] is False
    assert data["body_reconstruction"] is False
    assert data["full_surface_mesh"] is False


async def _false():
    return False


def test_readiness_fails_closed_without_dependencies(monkeypatch):
    monkeypatch.delenv("VIRTUAL_TWIN_API_TOKEN", raising=False)
    response = client.get("/ready")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["status"] == "not_ready"
    assert detail["model_adapter_configured"] is False
    assert detail["reason"] == "api_auth_not_configured"


def test_twin_endpoint_requires_authentication():
    response = client.post(
        "/twin",
        data={**identity_fields(), "height_cm": "180", "consent_image_processing": "true", "consent_body_measurements": "true"},
        files={"images": ("person.png", b"image", "image/png")},
    )
    assert response.status_code == 401


def test_twin_requires_explicit_consent(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", TOKEN)
    response = client.post(
        "/twin",
        headers=auth(),
        data={**identity_fields(), "height_cm": "180", "consent_image_processing": "false", "consent_body_measurements": "true"},
        files={"images": ("person.png", b"image", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EXPLICIT_TWIN_CONSENT_REQUIRED"


def test_twin_endpoint_does_not_claim_inference_when_worker_is_missing(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", TOKEN)
    response = client.post(
        "/twin",
        headers=auth(),
        data={**identity_fields(), "height_cm": "180", "consent_image_processing": "true", "consent_body_measurements": "true"},
        files={"images": ("person.png", b"image", "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "VISION_INFERENCE_NOT_CONFIGURED"


def test_twin_rejects_too_many_images(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", TOKEN)
    files = [("images", (f"image-{index}.jpg", b"x", "image/jpeg")) for index in range(7)]
    response = client.post(
        "/twin",
        headers=auth(),
        data={**identity_fields(), "height_cm": "180", "consent_image_processing": "true", "consent_body_measurements": "true"},
        files=files,
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "TOO_MANY_IMAGES"


def test_twin_rejects_oversized_image_before_calling_consent(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", TOKEN)
    monkeypatch.setattr(main, "MAX_IMAGE_BYTES", 3)
    response = client.post(
        "/twin",
        headers=auth(),
        data={**identity_fields(), "height_cm": "180", "consent_image_processing": "true", "consent_body_measurements": "true"},
        files={"images": ("large.jpg", b"four", "image/jpeg")},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "IMAGE_SIZE_LIMIT_EXCEEDED"


def test_twin_rejects_oversized_video(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", TOKEN)
    monkeypatch.setattr(main, "MAX_VIDEO_BYTES", 3)
    response = client.post(
        "/twin",
        headers=auth(),
        data={**identity_fields(), "height_cm": "180", "consent_image_processing": "true", "consent_body_measurements": "true"},
        files={"video": ("large.mp4", b"four", "video/mp4")},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "VIDEO_SIZE_LIMIT_EXCEEDED"


def test_twin_rejects_height_outside_contract(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", TOKEN)
    response = client.post(
        "/twin",
        headers=auth(),
        data={**identity_fields(), "height_cm": "261", "consent_image_processing": "true", "consent_body_measurements": "true"},
        files={"images": ("person.png", b"image", "image/png")},
    )
    assert response.status_code == 422
    assert any(error.get("loc", [None])[-1] == "height_cm" for error in response.json()["detail"])


def test_twin_success_returns_only_a_partial_ephemeral_pose(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", TOKEN)
    mock_internal_config(monkeypatch)

    async def verify(*_args, **_kwargs):
        return None

    async def run(*args, **kwargs):
        return {
            "status": "partial_twin_inference",
            "representation_type": "3d_pose_skeleton",
            "landmarks": [{"name": "nose"}],
            "surface_mesh_available": False,
            "fit_grade_measurements_available": False,
            "image_persisted": False,
        }

    monkeypatch.setattr(main, "_verify_consent", verify)
    monkeypatch.setattr(main, "_run_vision", run)
    response = client.post(
        "/twin",
        headers=auth(),
        data={**identity_fields(), "height_cm": "180", "consent_image_processing": "true", "consent_body_measurements": "true"},
        files={"images": ("person.png", b"image", "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial_twin_inference"
    assert body["record_persisted"] is False
    assert body["full_surface_mesh_available"] is False
    assert body["decision_status"] == "REVIEW_REQUIRED"
    assert response.headers["cache-control"] == "no-store, private"


def test_click_it_requires_explicit_consent(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", TOKEN)
    response = client.post(
        "/click-it",
        headers=auth(),
        data={**identity_fields(), "twin_id": "twin-123", "consent_image_processing": "false", "consent_click_it": "true"},
        files={"product_image": ("product.jpg", b"photo", "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EXPLICIT_CLICK_IT_CONSENT_REQUIRED"


def test_click_it_requires_authentication():
    response = client.post(
        "/click-it",
        data={**identity_fields(), "twin_id": "twin-123", "consent_image_processing": "true", "consent_click_it": "true"},
        files={"product_image": ("product.jpg", b"image", "image/jpeg")},
    )
    assert response.status_code == 401


def test_click_it_rejects_unsupported_media_type(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", TOKEN)
    response = client.post(
        "/click-it",
        headers=auth(),
        data={**identity_fields(), "twin_id": "twin-123", "consent_image_processing": "true", "consent_click_it": "true"},
        files={"product_image": ("product.bin", b"not-image", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "UNSUPPORTED_PRODUCT_IMAGE_TYPE"


def test_click_it_rejects_oversized_product_image(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", TOKEN)
    monkeypatch.setattr(main, "MAX_IMAGE_BYTES", 3)
    response = client.post(
        "/click-it",
        headers=auth(),
        data={**identity_fields(), "twin_id": "twin-123", "consent_image_processing": "true", "consent_click_it": "true"},
        files={"product_image": ("product.jpg", b"four", "image/jpeg")},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "PRODUCT_IMAGE_SIZE_LIMIT_EXCEEDED"


def test_click_it_stays_unavailable_without_worker(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", TOKEN)
    response = client.post(
        "/click-it",
        headers=auth(),
        data={**identity_fields(), "twin_id": "twin-123", "consent_image_processing": "true", "consent_click_it": "true"},
        files={"product_image": ("product.jpg", b"photo", "image/jpeg")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "VISION_INFERENCE_NOT_CONFIGURED"


def test_click_it_requires_verified_consent_before_worker(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", TOKEN)
    mock_internal_config(monkeypatch, consent=False)
    monkeypatch.setattr(main, "_run_vision", lambda *args, **kwargs: pytest.fail("must not run worker"))
    response = client.post(
        "/click-it",
        headers=auth(),
        data={**identity_fields(), "twin_id": "twin-123", "consent_image_processing": "true", "consent_click_it": "true"},
        files={"product_image": ("product.jpg", b"photo", "image/jpeg")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CONSENT_PROVIDER_NOT_CONFIGURED"


def test_click_it_success_returns_candidates_but_never_claims_display_authorization(monkeypatch):
    import pytest
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", TOKEN)
    mock_internal_config(monkeypatch)

    async def verify(*_args, **_kwargs):
        return None

    async def authorize(*_args, **_kwargs):
        return None

    async def run(*_args, **_kwargs):
        return {
            "status": "complete",
            "results": [{"variant_id": "offer-1", "product_name": "blue linen shirt", "match_score": 0.43}],
            "image_persisted": False,
            "scores_are_probabilities": False,
        }

    monkeypatch.setattr(main, "_verify_consent", verify)
    monkeypatch.setattr(main, "_authorize_twin", authorize)
    monkeypatch.setattr(main, "_run_vision", run)
    response = client.post(
        "/click-it",
        headers=auth(),
        data={**identity_fields(), "twin_id": "twin-123", "consent_image_processing": "true", "consent_click_it": "true"},
        files={"product_image": ("product.jpg", b"photo", "image/jpeg")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["candidates"][0]["variant_id"] == "offer-1"
    assert "results" not in body
    assert body["display_authorized"] is False
    assert body["decision_status"] == "PENDING_CAL"
    assert body["image_persisted"] is False
