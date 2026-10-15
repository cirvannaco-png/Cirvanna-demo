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
        data={"height_cm": "180", "weight_kg": "75"},
    )
    assert response.status_code == 401


def test_twin_endpoint_does_not_claim_generation_when_adapter_missing(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    response = client.post(
        "/twin",
        headers={"Authorization": "Bearer test-only-token"},
        data={"height_cm": "180", "weight_kg": "75"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MODEL_ADAPTER_NOT_CONFIGURED"


def test_twin_endpoint_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "expected-token")
    response = client.post(
        "/twin",
        headers={"Authorization": "Bearer wrong-token"},
        data={"height_cm": "180"},
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
        data={"height_cm": "180"},
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
        data={"height_cm": "261"},
    )
    assert response.status_code == 422
    assert any(
        error.get("loc", [None])[-1] == "height_cm"
        for error in response.json()["detail"]
    )
