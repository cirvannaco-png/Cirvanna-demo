from __future__ import annotations

import io

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

import app.main as dermalsight


client = TestClient(dermalsight.app)


class FakeAdapter:
    def predict(self, image: np.ndarray) -> dict:
        assert image.dtype == np.uint8
        assert image.ndim == 3 and image.shape[2] == 3
        return {
            "model_version": "test-model-1",
            "score_semantics": "uncalibrated_model_score_not_a_probability_or_diagnosis",
            "attributes": [{"name": "texture_variation", "score": 0.731058}],
        }


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (12, 10), color=(100, 120, 140)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_health_is_liveness_only():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "alive", "service": "cirvanna-dermalsight"}


def test_readiness_fails_closed_without_api_token(monkeypatch):
    monkeypatch.delenv("DERMALSIGHT_API_TOKEN", raising=False)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "api_token_not_configured"


def test_readiness_fails_closed_without_model(monkeypatch):
    monkeypatch.setenv("DERMALSIGHT_API_TOKEN", "test-only-token")
    monkeypatch.delenv("DERMALSIGHT_MODEL_PATH", raising=False)
    monkeypatch.delenv("DERMALSIGHT_MODEL_MANIFEST_PATH", raising=False)
    monkeypatch.setattr(dermalsight, "get_model_adapter", lambda: None)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "model_assets_not_configured"


def test_capabilities_do_not_claim_clinical_diagnosis(monkeypatch):
    monkeypatch.setattr(dermalsight, "get_model_adapter", lambda: None)
    response = client.get("/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["inference_enabled"] is False
    assert data["clinical_diagnosis"] is False
    assert data["image_persistence"] is False


def test_endpoint_requires_authentication(monkeypatch):
    monkeypatch.delenv("DERMALSIGHT_API_TOKEN", raising=False)
    response = client.post(
        "/api/v1/analyze",
        data={"consent": "true"},
        files={"image": ("x.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 401


def test_invalid_token_is_rejected(monkeypatch):
    monkeypatch.setenv("DERMALSIGHT_API_TOKEN", "expected-token")
    response = client.post(
        "/api/v1/analyze",
        headers={"Authorization": "Bearer wrong-token"},
        data={"consent": "true"},
        files={"image": ("x.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 401


def test_explicit_consent_is_required(monkeypatch):
    monkeypatch.setenv("DERMALSIGHT_API_TOKEN", "test-only-token")
    response = client.post(
        "/api/v1/analyze",
        headers={"Authorization": "Bearer test-only-token"},
        data={"consent": "false"},
        files={"image": ("x.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EXPLICIT_CONSENT_REQUIRED"


def test_no_model_means_no_heuristic_fallback(monkeypatch):
    monkeypatch.setenv("DERMALSIGHT_API_TOKEN", "test-only-token")
    monkeypatch.setattr(dermalsight, "get_model_adapter", lambda: None)
    response = client.post(
        "/api/v1/analyze",
        headers={"Authorization": "Bearer test-only-token"},
        data={"consent": "true"},
        files={"image": ("x.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MODEL_NOT_CONFIGURED"
    assert "heuristic fallback is disabled" in response.json()["detail"]["detail"]


def test_valid_image_uses_adapter_and_returns_non_diagnostic_scores(monkeypatch):
    monkeypatch.setenv("DERMALSIGHT_API_TOKEN", "test-only-token")
    monkeypatch.setattr(dermalsight, "get_model_adapter", lambda: FakeAdapter())
    response = client.post(
        "/api/v1/analyze",
        headers={"Authorization": "Bearer test-only-token"},
        data={"consent": "true"},
        files={"image": ("x.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "completed"
    assert data["model_version"] == "test-model-1"
    assert data["attributes"] == [{"name": "texture_variation", "score": 0.731058}]
    assert "not a medical diagnosis" in data["disclaimer"]
    assert response.headers["cache-control"] == "no-store"


def test_rejects_mime_mismatch(monkeypatch):
    monkeypatch.setenv("DERMALSIGHT_API_TOKEN", "test-only-token")
    monkeypatch.setattr(dermalsight, "get_model_adapter", lambda: FakeAdapter())
    response = client.post(
        "/api/v1/analyze",
        headers={"Authorization": "Bearer test-only-token"},
        data={"consent": "true"},
        files={"image": ("x.png", png_bytes(), "image/jpeg")},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "IMAGE_MIME_MISMATCH"


def test_rejects_invalid_image_bytes(monkeypatch):
    monkeypatch.setenv("DERMALSIGHT_API_TOKEN", "test-only-token")
    monkeypatch.setattr(dermalsight, "get_model_adapter", lambda: FakeAdapter())
    response = client.post(
        "/api/v1/analyze",
        headers={"Authorization": "Bearer test-only-token"},
        data={"consent": "true"},
        files={"image": ("x.png", b"not-an-image", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_IMAGE"


def test_rejects_oversized_upload(monkeypatch):
    monkeypatch.setenv("DERMALSIGHT_API_TOKEN", "test-only-token")
    monkeypatch.setattr(dermalsight, "get_model_adapter", lambda: FakeAdapter())
    monkeypatch.setattr(dermalsight, "MAX_IMAGE_BYTES", 10)
    response = client.post(
        "/api/v1/analyze",
        headers={"Authorization": "Bearer test-only-token"},
        data={"consent": "true"},
        files={"image": ("x.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "IMAGE_SIZE_LIMIT_EXCEEDED"
