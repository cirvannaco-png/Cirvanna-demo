from __future__ import annotations

import hashlib
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import app
from app import dsi_vision


TOKEN = "dsi-vision-worker-token-with-at-least-thirty-two-bytes"
SUBJECT = "user-dsi-vision-test-01"
RESOURCE = "dsi-vision-session-001"
RECEIPT = "dsi_receipt_test_capture_001"
MANIFEST = "1" * 64
PIPELINE = "2" * 64


def png_capture() -> bytes:
    image = Image.new("RGB", (240, 320), (115, 120, 125))
    draw = ImageDraw.Draw(image)
    for y in range(0, 320, 13):
        draw.line((0, y, 239, y), fill=(25, 65, 150), width=3)
    for x in range(0, 240, 13):
        draw.line((x, 0, x, 319), fill=(180, 35, 75), width=3)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DSI_VISION_WORKER_TOKEN", TOKEN)
    with TestClient(app) as test_client:
        yield test_client


def form(image: bytes, *, image_sha256: str | None = None, purpose="facial_geometry_analysis"):
    return {
        "subject_id": SUBJECT,
        "resource_id": RESOURCE,
        "purpose": purpose,
        "receipt_id": RECEIPT,
        "manifest_sha256": MANIFEST,
        "image_sha256": image_sha256 or hashlib.sha256(image).hexdigest(),
        "device_pipeline_fingerprint_sha256": PIPELINE,
    }


def test_face_landmarks_direct_worker_call_requires_capture_receipt_fields(client, monkeypatch):
    monkeypatch.setattr(
        dsi_vision.dsi_models,
        "get_face_landmarker",
        lambda: pytest.fail("Vision must not run face inference without a receipt"),
    )
    response = client.post(
        "/v1/dsi/face-landmarks",
        headers={"Authorization": f"Bearer {TOKEN}"},
        files={"image": ("capture.png", png_capture(), "image/png")},
    )
    assert response.status_code == 422


def test_face_landmarks_direct_worker_call_rejects_image_digest_substitution(client, monkeypatch):
    monkeypatch.setattr(
        dsi_vision.dsi_models,
        "get_face_landmarker",
        lambda: pytest.fail("Vision must reject altered image bytes before inference"),
    )
    image = png_capture()
    response = client.post(
        "/v1/dsi/face-landmarks",
        headers={"Authorization": f"Bearer {TOKEN}"},
        data=form(image, image_sha256="f" * 64),
        files={"image": ("capture.png", image, "image/png")},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "DSI_CAPTURE_IMAGE_RECEIPT_MISMATCH"


def test_face_landmarks_direct_worker_call_rejects_revoked_or_unknown_receipt(client, monkeypatch):
    async def receipt_not_active(_path, _payload):
        return {"verified": False, "receipt": None}

    monkeypatch.setattr(dsi_vision, "_identity_dsi_capture_post", receipt_not_active)
    monkeypatch.setattr(
        dsi_vision.dsi_models,
        "get_face_landmarker",
        lambda: pytest.fail("Vision must not run inference for an inactive receipt"),
    )
    image = png_capture()
    response = client.post(
        "/v1/dsi/face-landmarks",
        headers={"Authorization": f"Bearer {TOKEN}"},
        data=form(image),
        files={"image": ("capture.png", image, "image/png")},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "DSI_CAPTURE_RECEIPT_NOT_VERIFIED"


def test_skin_segmentation_direct_worker_call_rejects_receipt_scope_mismatch(client, monkeypatch):
    async def wrong_scope(_path, _payload):
        return {
            "verified": True,
            "receipt": {
                "receipt_id": RECEIPT,
                "subject_id": "different-subject",
                "resource_id": RESOURCE,
                "purpose": "body_tone_analysis",
                "manifest_sha256": MANIFEST,
                "image_sha256": hashlib.sha256(image).hexdigest(),
                "device_pipeline_fingerprint_sha256": PIPELINE,
                "verification_status": "verified_by_trusted_vision_service",
            },
        }

    image = png_capture()
    monkeypatch.setattr(dsi_vision, "_identity_dsi_capture_post", wrong_scope)
    monkeypatch.setattr(
        dsi_vision.dsi_models,
        "get_skin_segmenter",
        lambda: pytest.fail("Vision must not run segmentation for a different user"),
    )
    response = client.post(
        "/v1/dsi/skin-segmentation",
        headers={"Authorization": f"Bearer {TOKEN}"},
        data=form(image, purpose="body_tone_analysis"),
        files={"image": ("capture.png", image, "image/png")},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "DSI_CAPTURE_RECEIPT_SCOPE_MISMATCH"
