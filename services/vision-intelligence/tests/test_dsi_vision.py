from __future__ import annotations

import hashlib
import io
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app import main, dsi_models, dsi_vision

DSI_TOKEN = "dsi-vision-worker-token-at-least-thirty-two-bytes"


@pytest.fixture
def dsi_client(monkeypatch):
    monkeypatch.setenv("DSI_VISION_WORKER_TOKEN", DSI_TOKEN)
    # These endpoint tests use fake model providers; keep native MediaPipe image
    # construction in the separately provisioned-model smoke test.
    monkeypatch.setattr(dsi_vision, "_mp_image", lambda image: image)
    with TestClient(main.app) as client:
        yield client


def dsi_auth():
    return {"Authorization": f"Bearer {DSI_TOKEN}"}


def dsi_image_bytes():
    image = Image.new("RGB", (240, 320), (120, 120, 120))
    draw = ImageDraw.Draw(image)
    for y in range(0, 320, 14):
        draw.line((0, y, 239, y), fill=(30, 80, 140), width=3)
    for x in range(0, 240, 14):
        draw.line((x, 0, x, 319), fill=(180, 40, 70), width=3)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_dsi_worker_auth_is_independent_and_required(dsi_client, monkeypatch):
    monkeypatch.delenv("DSI_VISION_WORKER_TOKEN", raising=False)
    response = dsi_client.post(
        "/v1/dsi/face-landmarks",
        files={"image": ("face.png", dsi_image_bytes(), "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DSI_VISION_AUTH_NOT_CONFIGURED"


def test_dsi_face_endpoint_rejects_unauthenticated_call(dsi_client):
    response = dsi_client.post(
        "/v1/dsi/face-landmarks",
        files={"image": ("face.png", dsi_image_bytes(), "image/png")},
    )
    assert response.status_code == 401


def test_dsi_face_endpoint_returns_478_landmarks_without_identity_features(dsi_client, monkeypatch):
    points = [SimpleNamespace(x=0.4, y=0.45, z=-0.01) for _ in range(478)]

    class FakeLandmarker:
        def detect(self, _image):
            return SimpleNamespace(face_landmarks=[points])

    monkeypatch.setattr(dsi_models, "get_face_landmarker", lambda: FakeLandmarker())
    monkeypatch.setattr(
        dsi_models,
        "face_landmarker_status",
        lambda: {"configured": True, "version": "test-v1", "sha256": "a" * 64, "reason": None},
    )
    response = dsi_client.post(
        "/v1/dsi/face-landmarks",
        headers=dsi_auth(),
        files={"image": ("face.png", dsi_image_bytes(), "image/png")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["landmark_count"] == 478
    assert len(payload["landmarks"]) == 478
    assert payload["face_embeddings_computed"] is False
    assert payload["face_recognition_performed"] is False
    assert payload["age_estimation_performed"] is False
    assert payload["image_persisted"] is False
    assert response.headers["cache-control"] == "no-store, private"


@pytest.mark.parametrize(
    ("faces", "expected"),
    [
        ([], "DSI_FACE_NOT_DETECTED"),
        ([[SimpleNamespace(x=0.4, y=0.5, z=0.0)] * 478, [SimpleNamespace(x=0.5, y=0.5, z=0.0)] * 478], "DSI_SINGLE_FACE_REQUIRED"),
    ],
)
def test_dsi_face_endpoint_rejects_missing_or_multiple_faces(dsi_client, monkeypatch, faces, expected):
    class FakeLandmarker:
        def detect(self, _image):
            return SimpleNamespace(face_landmarks=faces)

    monkeypatch.setattr(dsi_models, "get_face_landmarker", lambda: FakeLandmarker())
    response = dsi_client.post(
        "/v1/dsi/face-landmarks",
        headers=dsi_auth(),
        files={"image": ("face.png", dsi_image_bytes(), "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == expected


def test_dsi_face_endpoint_fails_on_invalid_landmark_coordinates(dsi_client, monkeypatch):
    points = [SimpleNamespace(x=0.4, y=0.45, z=0.0) for _ in range(478)]
    points[0] = SimpleNamespace(x=float("nan"), y=0.45, z=0.0)

    class FakeLandmarker:
        def detect(self, _image):
            return SimpleNamespace(face_landmarks=[points])

    monkeypatch.setattr(dsi_models, "get_face_landmarker", lambda: FakeLandmarker())
    response = dsi_client.post(
        "/v1/dsi/face-landmarks",
        headers=dsi_auth(),
        files={"image": ("face.png", dsi_image_bytes(), "image/png")},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "DSI_INVALID_FACE_LANDMARK"


def test_dsi_skin_segmentation_returns_only_region_masks_and_unvalidated_status(dsi_client, monkeypatch):
    categories = np.zeros((320, 240), dtype=np.uint8)
    categories[40:120, 70:160] = 3
    categories[130:240, 60:180] = 2
    masks = [np.full((320, 240), 0.5, dtype=np.float32) for _ in range(6)]
    fake_images = [SimpleNamespace(numpy_view=lambda values=values: values) for values in masks]
    category_image = SimpleNamespace(numpy_view=lambda: categories)

    class FakeSegmenter:
        labels = ["background", "hair", "body-skin", "face-skin", "clothes", "others"]

        def segment(self, _image):
            return SimpleNamespace(category_mask=category_image, confidence_masks=fake_images)

    monkeypatch.setattr(dsi_models, "get_skin_segmenter", lambda: FakeSegmenter())
    monkeypatch.setattr(
        dsi_models,
        "skin_segmenter_status",
        lambda: {"configured": True, "version": "segmenter-test-v1", "sha256": "b" * 64, "reason": None},
    )
    response = dsi_client.post(
        "/v1/dsi/skin-segmentation",
        headers=dsi_auth(),
        files={"image": ("face.png", dsi_image_bytes(), "image/png")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "segmentation_detected_unvalidated_skin_masks"
    assert payload["skin_tone_value_computed"] is False
    assert payload["absolute_color_calibration_performed"] is False
    assert payload["image_persisted"] is False
    assert payload["region_coverage"]["face_skin_fraction"] > 0
    assert payload["region_coverage"]["body_skin_fraction"] > 0
    assert payload["mean_model_confidence_noncalibrated"]["face_skin"] == 0.5
    assert "results" not in payload
    assert response.headers["cache-control"] == "no-store, private"


def test_dsi_segmentation_fails_closed_on_unknown_label_order(dsi_client, monkeypatch):
    categories = np.zeros((320, 240), dtype=np.uint8)
    masks = [np.ones((320, 240), dtype=np.float32) for _ in range(6)]
    fake_images = [SimpleNamespace(numpy_view=lambda values=values: values) for values in masks]
    category_image = SimpleNamespace(numpy_view=lambda: categories)

    class FakeSegmenter:
        labels = ["background", "face-skin", "hair", "body-skin", "clothes", "others"]

        def segment(self, _image):
            return SimpleNamespace(category_mask=category_image, confidence_masks=fake_images)

    monkeypatch.setattr(dsi_models, "get_skin_segmenter", lambda: FakeSegmenter())
    response = dsi_client.post(
        "/v1/dsi/skin-segmentation",
        headers=dsi_auth(),
        files={"image": ("face.png", dsi_image_bytes(), "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DSI_SEGMENTATION_LABEL_MAP_MISMATCH"


def test_dsi_skin_segmentation_rejects_invalid_mask_shape(dsi_client, monkeypatch):
    categories = np.zeros((12, 12), dtype=np.uint8)
    masks = [np.ones((12, 12), dtype=np.float32) for _ in range(6)]
    fake_images = [SimpleNamespace(numpy_view=lambda values=values: values) for values in masks]
    category_image = SimpleNamespace(numpy_view=lambda: categories)

    class FakeSegmenter:
        labels = ["background", "hair", "body-skin", "face-skin", "clothes", "others"]

        def segment(self, _image):
            return SimpleNamespace(category_mask=category_image, confidence_masks=fake_images)

    monkeypatch.setattr(dsi_models, "get_skin_segmenter", lambda: FakeSegmenter())
    response = dsi_client.post(
        "/v1/dsi/skin-segmentation",
        headers=dsi_auth(),
        files={"image": ("face.png", dsi_image_bytes(), "image/png")},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "DSI_CATEGORY_MASK_SHAPE_INVALID"


def test_dsi_readiness_is_independent_of_marketplace_and_requires_two_pinned_models(dsi_client, monkeypatch):
    monkeypatch.setattr(dsi_models, "face_landmarker_status", lambda: {"configured": True, "version": "f-v1", "sha256": "a" * 64, "reason": None})
    monkeypatch.setattr(dsi_models, "get_face_landmarker", lambda: object())
    monkeypatch.setattr(dsi_models, "skin_segmenter_status", lambda: {"configured": False, "reason": "model_asset_missing"})
    response = dsi_client.get("/v1/dsi/ready", headers=dsi_auth())
    assert response.status_code == 503
    payload = response.json()
    assert payload["dsi_ready"] is False
    assert payload["face_landmarker"]["configured"] is True
    assert payload["face_landmarker"]["loaded"] is True
    assert payload["skin_segmenter"]["configured"] is False
    assert payload["skin_segmenter"]["loaded"] is False



def test_dsi_model_assets_require_a_matching_sha256_and_version(tmp_path, monkeypatch):
    asset = tmp_path / "face_landmarker.task"
    asset.write_bytes(b"model-asset-fixture")
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    monkeypatch.setenv("DSI_FACE_LANDMARKER_MODEL_PATH", str(asset))
    monkeypatch.setenv("DSI_FACE_LANDMARKER_MODEL_SHA256", digest)
    monkeypatch.setenv("DSI_FACE_LANDMARKER_MODEL_VERSION", "face-test-v1")
    valid = dsi_models.face_landmarker_status()
    assert valid["configured"] is True
    assert valid["sha256"] == digest
    assert valid["version"] == "face-test-v1"

    monkeypatch.setenv("DSI_FACE_LANDMARKER_MODEL_SHA256", "0" * 64)
    invalid = dsi_models.face_landmarker_status()
    assert invalid["configured"] is False
    assert invalid["reason"] == "model_asset_sha256_mismatch"


def test_dsi_model_assets_are_not_ready_without_all_pins(monkeypatch):
    for name in (
        "DSI_SKIN_SEGMENTER_MODEL_PATH",
        "DSI_SKIN_SEGMENTER_MODEL_SHA256",
        "DSI_SKIN_SEGMENTER_MODEL_VERSION",
    ):
        monkeypatch.delenv(name, raising=False)
    status = dsi_models.skin_segmenter_status()
    assert status["configured"] is False
    assert status["reason"] == "model_path_sha256_and_version_required"


def test_dsi_ready_requires_successful_model_loads_and_label_map(dsi_client, monkeypatch):
    monkeypatch.setattr(
        dsi_models,
        "face_landmarker_status",
        lambda: {"configured": True, "version": "face-v1", "sha256": "a" * 64, "reason": None},
    )
    monkeypatch.setattr(
        dsi_models,
        "skin_segmenter_status",
        lambda: {"configured": True, "version": "skin-v1", "sha256": "b" * 64, "reason": None},
    )
    monkeypatch.setattr(dsi_models, "get_face_landmarker", lambda: object())
    monkeypatch.setattr(dsi_models, "get_skin_segmenter", lambda: object())
    response = dsi_client.get("/v1/dsi/ready", headers=dsi_auth())
    assert response.status_code == 200
    assert response.json()["dsi_ready"] is True
    assert response.json()["face_landmarker"]["loaded"] is True
    assert response.json()["skin_segmenter"]["loaded"] is True



def test_dsi_colorchecker_preview_requires_supported_reference_and_returns_unvalidated_lab_stats(dsi_client, monkeypatch):
    from app.color_calibration import PROFILE_ID
    categories = np.zeros((320, 240), dtype=np.uint8)
    categories[40:140, 70:160] = 3
    categories[150:290, 40:210] = 2
    category_image = SimpleNamespace(numpy_view=lambda: categories)

    class FakeSegmenter:
        labels = ["background", "hair", "body-skin", "face-skin", "clothes", "others"]

        def segment(self, _image):
            return SimpleNamespace(category_mask=category_image)

    monkeypatch.setattr(dsi_models, "get_skin_segmenter", lambda: FakeSegmenter())
    response = dsi_client.post(
        "/v1/dsi/colorchecker-tone-preview",
        headers=dsi_auth(),
        data={
            "profile_id": PROFILE_ID,
            "patch_grid_corners": "[[20,40],[100,40],[100,120],[20,120]]",
            "chart_edition_confirmed_after_2014": "true",
            "chart_age_months": "12",
            "chart_condition": "good",
            "requested_region": "face_skin",
        },
        files={"image": ("capture.png", dsi_image_bytes(), "image/png")},
    )
    # This is a routing/provider test, not a chart-fit test; the deliberately
    # wrong pixel rectangle must be rejected by the real calibration geometry.
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "DSI_COLOR_CALIBRATION_INPUT_INVALID"


def test_dsi_colorchecker_preview_rejects_unsupported_reference_before_model_use(dsi_client, monkeypatch):
    def forbidden():
        pytest.fail("unsupported chart profile must be rejected before model loading")

    monkeypatch.setattr(dsi_models, "get_skin_segmenter", forbidden)
    response = dsi_client.post(
        "/v1/dsi/colorchecker-tone-preview",
        headers=dsi_auth(),
        data={
            "profile_id": "unknown-chart-edition",
            "patch_grid_corners": "[[20,40],[100,40],[100,120],[20,120]]",
            "chart_edition_confirmed_after_2014": "true",
            "chart_age_months": "12",
            "chart_condition": "good",
            "requested_region": "face_skin",
        },
        files={"image": ("capture.png", dsi_image_bytes(), "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "DSI_COLOR_REFERENCE_PROFILE_UNSUPPORTED"



def test_dsi_colorchecker_route_requires_correct_chart_edition_confirmation(dsi_client, monkeypatch):
    from app.color_calibration import PROFILE_ID

    def forbidden():
        pytest.fail("the worker must reject an unconfirmed chart edition before model loading")

    monkeypatch.setattr(dsi_models, "get_skin_segmenter", forbidden)
    response = dsi_client.post(
        "/v1/dsi/colorchecker-tone-preview",
        headers=dsi_auth(),
        data={
            "profile_id": PROFILE_ID,
            "patch_grid_corners": "[[20,40],[100,40],[100,120],[20,120]]",
            "chart_edition_confirmed_after_2014": "false",
        },
        files={"image": ("capture.png", dsi_image_bytes(), "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "DSI_COLOR_REFERENCE_EDITION_NOT_CONFIRMED"


def _signed_capture_envelope_for_route(image_bytes: bytes) -> tuple[dict, str]:
    import base64
    import json

    nonce = base64.urlsafe_b64encode(b"z" * 32).rstrip(b"=").decode("ascii")
    manifest = {
        "schema_version": "dsi-capture-manifest-v1",
        "capture_ref": "cap_abcdefghijkl",
        "challenge_id": "dsi_challenge_0123456789abcdef",
        "challenge_nonce_sha256": hashlib.sha256(b"z" * 32).hexdigest(),
        "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "image_byte_count": len(image_bytes),
        "device_pipeline_fingerprint_sha256": "a" * 64,
        "absolute_colour_measurement_approved": False,
        "server_verification_required": True,
    }
    # This fixture only exercises the HTTP contract; the cryptographic verifier is
    # separately exercised through its CLI build and unit tests.
    from app.dsi_capture_verification import _canonical_json
    canonical = _canonical_json(manifest)
    manifest_digest = hashlib.sha256(canonical.encode()).hexdigest()
    request_hash = base64.urlsafe_b64encode(
        hashlib.sha256(canonical.encode()).digest()
    ).rstrip(b"=").decode("ascii")
    envelope = {
        "schemaVersion": "dsi-android-attestation-v1",
        "captureRef": manifest["capture_ref"],
        "challengeId": manifest["challenge_id"],
        "manifestSha256": manifest_digest,
        "imageSha256": manifest["image_sha256"],
        "devicePipelineFingerprintSha256": manifest["device_pipeline_fingerprint_sha256"],
        "manifestCanonicalJson": canonical,
        "signatureAlgorithm": "SHA256withECDSA",
        "signatureBase64Url": "A" * 86,
        "attestationCertificateChainBase64Url": ["QUJD", "REVG", "R0hJ"],
        "playIntegrityToken": "p" * 80,
        "playIntegrityRequestHash": request_hash,
        "androidKeySecurityLevel": "software",
        "verificationState": "pending_server_verification",
        "absoluteColourMeasurementApproved": False,
    }
    return envelope, nonce


def test_capture_challenge_is_issued_through_identity(dsi_client, monkeypatch):
    import asyncio

    calls = []

    async def issue(payload):
        calls.append(payload)
        return {
            "status": "issued",
            "challenge_id": "dsi_challenge_0123456789abcdef",
            "nonce_b64url": "A" * 43,
        }

    monkeypatch.setattr(dsi_vision, "issue_identity_capture_challenge", issue)
    response = dsi_client.post(
        "/v1/dsi/capture-challenges",
        headers=dsi_auth(),
        json={
            "subject_id": "subject-1",
            "consent_id": "consent-12345678",
            "consent_version": "v1",
            "resource_id": "resource-1",
            "purpose": "cosmetic_skin_analysis",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "issued"
    assert calls[0].subject_id == "subject-1"
    assert calls[0].purpose == "cosmetic_skin_analysis"


def test_capture_verification_parses_pending_client_envelope_and_returns_server_result(dsi_client, monkeypatch):
    import asyncio

    image_bytes = dsi_image_bytes()
    envelope, nonce = _signed_capture_envelope_for_route(image_bytes)
    calls = []

    async def verify(candidate, *, challenge_nonce_base64url, image_bytes):
        calls.append((candidate, challenge_nonce_base64url, image_bytes))
        return {
            "status": "verified",
            "receipt": {"receipt_id": "dsi_receipt_1234567890"},
            "absolute_colour_measurement_approved": False,
        }

    monkeypatch.setattr(dsi_vision, "verify_and_persist_capture", verify)
    response = dsi_client.post(
        "/v1/dsi/capture-verifications",
        headers=dsi_auth(),
        data={"envelope_json": __import__("json").dumps(envelope), "challenge_nonce_base64url": nonce},
        files={"image": ("capture.png", image_bytes, "image/png")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["receipt"]["receipt_id"] == "dsi_receipt_1234567890"
    assert calls[0][0].android_key_security_level_hint == "software"
    assert calls[0][1] == nonce
    assert calls[0][2] == image_bytes


def test_capture_verification_rejects_client_claimed_verified_state_before_provider_call(dsi_client, monkeypatch):
    import json

    image_bytes = dsi_image_bytes()
    envelope, nonce = _signed_capture_envelope_for_route(image_bytes)
    envelope["verificationState"] = "verified"
    monkeypatch.setattr(
        dsi_vision,
        "verify_and_persist_capture",
        lambda *_args, **_kwargs: pytest.fail("untrusted client state must be rejected before verification"),
    )
    response = dsi_client.post(
        "/v1/dsi/capture-verifications",
        headers=dsi_auth(),
        data={"envelope_json": json.dumps(envelope), "challenge_nonce_base64url": nonce},
        files={"image": ("capture.png", image_bytes, "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "DSI_CAPTURE_ENVELOPE_INVALID"


def test_trusted_capture_gate_rejects_modified_image_before_identity_check(dsi_client, monkeypatch):
    image_bytes = dsi_image_bytes()

    class Decoded:
        def close(self):
            pass

    async def fake_read(image):
        data = await image.read()
        await image.close()
        return data, Decoded()

    monkeypatch.setattr(dsi_vision, "_read_image", fake_read)
    monkeypatch.setattr(
        dsi_vision,
        "verify_identity_capture_receipt",
        lambda **_kwargs: pytest.fail("Identity must not be called with a mismatched image"),
    )
    response = dsi_client.post(
        "/v1/dsi/capture/skin-segmentation",
        headers=dsi_auth(),
        data={
            "receipt_id": "dsi_receipt_1234567890",
            "subject_id": "subject-1",
            "resource_id": "resource-1",
            "purpose": "cosmetic_skin_analysis",
            "manifest_sha256": "b" * 64,
            "image_sha256": "c" * 64,
            "device_pipeline_fingerprint_sha256": "a" * 64,
        },
        files={"image": ("capture.png", image_bytes, "image/png")},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "DSI_CAPTURE_IMAGE_DIGEST_MISMATCH"


def test_trusted_capture_gate_revalidates_live_identity_receipt_before_inference(dsi_client, monkeypatch):
    image_bytes = dsi_image_bytes()

    class Decoded:
        def close(self):
            pass

    async def fake_read(image):
        data = await image.read()
        await image.close()
        return data, Decoded()

    identity_calls = []
    async def verify_identity(**kwargs):
        identity_calls.append(kwargs)
        return {"verified": True, "receipt": {"receipt_id": "dsi_receipt_1234567890"}}

    async def fake_segmentation(upload):
        payload = await upload.read()
        await upload.close()
        assert payload == image_bytes
        return dsi_vision._no_store({"status": "segmentation_detected_unvalidated_skin_masks"})

    monkeypatch.setattr(dsi_vision, "_read_image", fake_read)
    monkeypatch.setattr(dsi_vision, "verify_identity_capture_receipt", verify_identity)
    monkeypatch.setattr(dsi_vision, "skin_segmentation", fake_segmentation)
    response = dsi_client.post(
        "/v1/dsi/capture/skin-segmentation",
        headers=dsi_auth(),
        data={
            "receipt_id": "dsi_receipt_1234567890",
            "subject_id": "subject-1",
            "resource_id": "resource-1",
            "purpose": "cosmetic_skin_analysis",
            "manifest_sha256": "b" * 64,
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "device_pipeline_fingerprint_sha256": "a" * 64,
        },
        files={"image": ("capture.png", image_bytes, "image/png")},
    )
    assert response.status_code == 200, response.text
    assert identity_calls[0]["subject_id"] == "subject-1"
    assert identity_calls[0]["image_sha256"] == hashlib.sha256(image_bytes).hexdigest()
    assert response.json()["status"] == "segmentation_detected_unvalidated_skin_masks"
