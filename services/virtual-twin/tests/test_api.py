from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_is_liveness_only():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "alive",
        "service": "cirvanna-virtual-twin",
    }


def test_capabilities_do_not_claim_unimplemented_features():
    response = client.get("/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["twin_generation"] is False
    assert data["body_reconstruction"] is False
    assert data["skin_analysis"] is False
    assert data["fit_prediction"] is False
    assert data["ar_rendering"] is False
    assert data["click_it_product_reconstruction"] is False
    assert data["decision_governance_connected_to_rendering"] is False


def test_readiness_fails_closed_without_model_adapter():
    response = client.get("/ready")
    assert response.status_code == 503


def test_readiness_explains_missing_model_adapter():
    response = client.get("/ready")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["status"] == "not_ready"
    assert detail["model_adapter_configured"] is False
    assert detail["reason"] == "validated_model_adapter_not_integrated"


def test_twin_endpoint_requires_authentication(monkeypatch):
    monkeypatch.delenv("VIRTUAL_TWIN_API_TOKEN", raising=False)
    response = client.post(
        "/twin",
        data={"height_cm": "180", "weight_kg": "75", "consent_image_processing": "true", "consent_body_measurements": "true"},
    )
    assert response.status_code == 401


def test_twin_endpoint_does_not_claim_generation_when_adapter_missing(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    response = client.post(
        "/twin",
        headers={"Authorization": "Bearer test-only-token"},
        data={"height_cm": "180", "weight_kg": "75", "consent_image_processing": "true", "consent_body_measurements": "true"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MODEL_ADAPTER_NOT_CONFIGURED"


def test_twin_endpoint_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "expected-token")
    response = client.post(
        "/twin",
        headers={"Authorization": "Bearer wrong-token"},
        data={"height_cm": "180", "consent_image_processing": "true", "consent_body_measurements": "true"},
    )
    assert response.status_code == 401


def test_twin_endpoint_rejects_too_many_images(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    files = [
        ("images", (f"image-{index}.jpg", b"x", "image/jpeg"))
        for index in range(7)
    ]
    response = client.post(
        "/twin",
        headers={"Authorization": "Bearer test-only-token"},
        data={"height_cm": "180", "consent_image_processing": "true", "consent_body_measurements": "true"},
        files=files,
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "TOO_MANY_IMAGES"


def test_twin_endpoint_rejects_oversized_image(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    monkeypatch.setattr("app.main.MAX_IMAGE_BYTES", 3)
    response = client.post(
        "/twin",
        headers={"Authorization": "Bearer test-only-token"},
        data={"height_cm": "180"},
        files={"images": ("large.jpg", b"four", "image/jpeg")},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "IMAGE_SIZE_LIMIT_EXCEEDED"


def test_twin_endpoint_rejects_oversized_video(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    monkeypatch.setattr("app.main.MAX_VIDEO_BYTES", 3)
    response = client.post(
        "/twin",
        headers={"Authorization": "Bearer test-only-token"},
        data={"height_cm": "180"},
        files={"video": ("large.mp4", b"four", "video/mp4")},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "VIDEO_SIZE_LIMIT_EXCEEDED"


def test_twin_endpoint_rejects_height_outside_contract(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    response = client.post(
        "/twin",
        headers={"Authorization": "Bearer test-only-token"},
        data={"height_cm": "261", "consent_image_processing": "true", "consent_body_measurements": "true"},
    )
    assert response.status_code == 422
    assert any(
        error.get("loc", [None])[-1] == "height_cm"
        for error in response.json()["detail"]
    )




def test_click_it_requires_explicit_consent(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    response = client.post(
        "/click-it",
        headers={"Authorization": "Bearer test-only-token"},
        data={"twin_id": "twin-1", "consent_image_processing": "false", "consent_click_it": "true"},
        files={"product_image": ("product.jpg", b"photo", "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EXPLICIT_CLICK_IT_CONSENT_REQUIRED"


def test_twin_requires_explicit_consent(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    response = client.post(
        "/twin",
        headers={"Authorization": "Bearer test-only-token"},
        data={"height_cm": "180", "consent_image_processing": "false", "consent_body_measurements": "true"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EXPLICIT_TWIN_CONSENT_REQUIRED"

def test_click_it_requires_authentication():
    response = client.post(
        "/click-it",
        data={"twin_id": "twin-1", "consent_image_processing": "true", "consent_click_it": "true"},
        files={"product_image": ("product.jpg", b"image", "image/jpeg")},
    )
    assert response.status_code == 401


def test_click_it_rejects_unsupported_media_type(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    response = client.post(
        "/click-it",
        headers={"Authorization": "Bearer test-only-token"},
        data={"twin_id": "twin-1", "consent_image_processing": "true", "consent_click_it": "true"},
        files={"product_image": ("product.bin", b"not-image", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "UNSUPPORTED_PRODUCT_IMAGE_TYPE"


def test_click_it_rejects_oversized_product_image(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    monkeypatch.setattr("app.main.MAX_IMAGE_BYTES", 3)
    response = client.post(
        "/click-it",
        headers={"Authorization": "Bearer test-only-token"},
        data={"twin_id": "twin-1"},
        files={"product_image": ("product.jpg", b"four", "image/jpeg")},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "PRODUCT_IMAGE_SIZE_LIMIT_EXCEEDED"


def test_click_it_does_not_claim_product_reconstruction_when_pipeline_is_missing(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    response = client.post(
        "/click-it",
        headers={"Authorization": "Bearer test-only-token"},
        data={"twin_id": "twin-1"},
        files={"product_image": ("product.jpg", b"photo", "image/jpeg")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CLICK_IT_PIPELINE_NOT_CONFIGURED"
    assert "image was not processed" in response.json()["detail"]["detail"]
