from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import app
from app.dsi import api as dsi_api
from app.dsi.consent import PURPOSE_SCOPES, verify_dsi_consent
from app.dsi.contracts import ConsentPurpose
from app.dsi.errors import ConsentNotAuthorized, DSIProviderUnavailable

DSI_API_TOKEN = "dsi-internal-api-token-with-at-least-thirty-two-bytes"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DSI_INTERNAL_API_TOKEN", DSI_API_TOKEN)
    with TestClient(app) as test_client:
        yield test_client


def auth():
    return {"Authorization": f"Bearer {DSI_API_TOKEN}"}


def capture_bytes():
    image = Image.new("RGB", (240, 320), (115, 120, 125))
    draw = ImageDraw.Draw(image)
    for y in range(0, 320, 13):
        draw.line((0, y, 239, y), fill=(25, 65, 150), width=3)
    for x in range(0, 240, 13):
        draw.line((x, 0, x, 319), fill=(180, 35, 75), width=3)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def face_landmark_payload():
    points = [{"x": 0.5, "y": 0.5, "z": 0.0} for _ in range(478)]
    points[234] = {"x": 0.20, "y": 0.50, "z": 0.0}
    points[454] = {"x": 0.80, "y": 0.50, "z": 0.0}
    points[10] = {"x": 0.50, "y": 0.10, "z": 0.0}
    points[152] = {"x": 0.50, "y": 0.90, "z": 0.0}
    points[172] = {"x": 0.34, "y": 0.73, "z": 0.0}
    points[397] = {"x": 0.66, "y": 0.73, "z": 0.0}
    points[103] = {"x": 0.30, "y": 0.22, "z": 0.0}
    points[332] = {"x": 0.70, "y": 0.22, "z": 0.0}
    return {
        "status": "landmarks_detected_unvalidated_geometry",
        "width": 240,
        "height": 320,
        "landmark_count": 478,
        "landmarks": points,
        "model": {"version": "fixture-v1", "sha256": "a" * 64},
        "image_persisted": False,
        "face_recognition_performed": False,
        "identity_matching_performed": False,
        "age_estimation_performed": False,
    }


def consent_form():
    return {
        "subject_id": "user-dsi-001",
        "consent_id": "consent-bundle-dsi-001",
        "consent_version": "dsi-v1",
        "resource_id": "dsi-enrollment-session-001",
    }


def test_dsi_routes_require_dedicated_internal_auth(client, monkeypatch):
    monkeypatch.delenv("DSI_INTERNAL_API_TOKEN", raising=False)
    response = client.post(
        "/api/v1/dsi/face-geometry-preview",
        data=consent_form(),
        files={"image": ("capture.png", capture_bytes(), "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DSI_API_AUTH_NOT_CONFIGURED"


def test_face_geometry_preview_checks_consent_and_returns_non_vetoing_unvalidated_metrics(client, monkeypatch):
    verified = {}

    async def allow_consent(**kwargs):
        verified.update(kwargs)
        return {"verified": True, "purpose": ConsentPurpose.FACIAL_GEOMETRY_ANALYSIS.value}

    async def fake_landmarks(**kwargs):
        assert kwargs["content_type"] == "image/png"
        assert kwargs["filename"] == "capture.png"
        return face_landmark_payload()

    monkeypatch.setattr(dsi_api, "verify_dsi_consent", allow_consent)
    monkeypatch.setattr(dsi_api, "fetch_face_landmarks", fake_landmarks)
    response = client.post(
        "/api/v1/dsi/face-geometry-preview",
        headers=auth(),
        data=consent_form(),
        files={"image": ("capture.png", capture_bytes(), "image/png")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert verified["purpose"] == ConsentPurpose.FACIAL_GEOMETRY_ANALYSIS
    assert verified["subject_id"] == "user-dsi-001"
    assert verified["resource_id"] == "dsi-enrollment-session-001"
    assert payload["geometry"]["status"] == "unvalidated_geometry_preview"
    assert payload["geometry"]["face_shape"] == "not_classified"
    assert payload["geometry"]["hairline_shape"] == "not_classified"
    assert payload["geometry"]["measurement_uncertainty"] == "not_calibrated_or_independently_validated"
    assert payload["image_persisted"] is False
    assert payload["profile_persisted"] is False
    assert payload["discovery_restricted"] is False
    assert response.headers["cache-control"] == "no-store, private"


def test_face_geometry_preview_does_not_call_vision_without_verified_consent(client, monkeypatch):
    async def deny_consent(**_kwargs):
        raise ConsentNotAuthorized("revoked")

    async def forbidden(**_kwargs):
        pytest.fail("Vision inference must not run without purpose consent")

    monkeypatch.setattr(dsi_api, "verify_dsi_consent", deny_consent)
    monkeypatch.setattr(dsi_api, "fetch_face_landmarks", forbidden)
    response = client.post(
        "/api/v1/dsi/face-geometry-preview",
        headers=auth(),
        data=consent_form(),
        files={"image": ("capture.png", capture_bytes(), "image/png")},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "DSI_PURPOSE_CONSENT_NOT_VERIFIED"


def test_skin_region_preview_requires_body_tone_purpose_and_never_claims_tone(client, monkeypatch):
    verified = {}

    async def allow_consent(**kwargs):
        verified.update(kwargs)
        return {"verified": True}

    async def fake_segmentation(**_kwargs):
        return {
            "status": "segmentation_detected_unvalidated_skin_masks",
            "region_coverage": {
                "face_skin_fraction": 0.15,
                "body_skin_fraction": 0.30,
                "hair_fraction": 0.08,
                "clothing_fraction": 0.35,
            },
            "model": {"version": "segmenter-v1", "sha256": "b" * 64},
            "skin_tone_value_computed": False,
            "absolute_color_calibration_performed": False,
            "image_persisted": False,
        }

    monkeypatch.setattr(dsi_api, "verify_dsi_consent", allow_consent)
    monkeypatch.setattr(dsi_api, "fetch_skin_segmentation", fake_segmentation)
    response = client.post(
        "/api/v1/dsi/skin-region-preview",
        headers=auth(),
        data={**consent_form(), "purpose": "body_tone_analysis"},
        files={"image": ("capture.png", capture_bytes(), "image/png")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert verified["purpose"] == ConsentPurpose.BODY_TONE_ANALYSIS
    assert payload["purpose"] == "body_tone_analysis"
    assert payload["skin_tone_value_computed"] is False
    assert payload["absolute_color_calibration_performed"] is False
    assert payload["discovery_restricted"] is False
    assert payload["profile_persisted"] is False


def test_skin_region_preview_provider_failure_is_optional_and_sanitized(client, monkeypatch):
    async def allow_consent(**_kwargs):
        return {"verified": True}

    async def unavailable(**_kwargs):
        raise DSIProviderUnavailable("private provider details")

    monkeypatch.setattr(dsi_api, "verify_dsi_consent", allow_consent)
    monkeypatch.setattr(dsi_api, "fetch_skin_segmentation", unavailable)
    response = client.post(
        "/api/v1/dsi/skin-region-preview",
        headers=auth(),
        data={**consent_form(), "purpose": "cosmetic_skin_analysis"},
        files={"image": ("capture.png", capture_bytes(), "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DSI_VISION_PROVIDER_UNAVAILABLE"
    assert "private provider details" not in response.text


def _consent_receipt(*, scopes=None, expires=None, subject="user-dsi-001", resource="dsi-session-001"):
    return {
        "verified": True,
        "active": True,
        "subject_id": subject,
        "consent_id": "bundle-dsi-test",
        "resource_id": resource,
        "consent_version": "dsi-v1",
        "granted_scopes": list(scopes or PURPOSE_SCOPES[ConsentPurpose.FACIAL_GEOMETRY_ANALYSIS]),
        "receipt_ids": ["receipt-one", "receipt-two"],
        "expires_at": expires or (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    }


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, payload):
        self.payload = payload
        self.last_request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, url, *, headers, json):
        self.last_request = {"url": url, "headers": headers, "json": json}
        return FakeResponse(self.payload)


def test_consent_client_calls_identity_learning_with_exact_purpose_scope_and_resource(monkeypatch):
    import app.dsi.consent as consent_module

    expiry = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    fake = FakeAsyncClient(_consent_receipt(expires=expiry))
    monkeypatch.setenv("IDENTITY_LEARNING_API_URL", "http://localhost:8092")
    monkeypatch.setenv("IDENTITY_LEARNING_API_TOKEN", "identity-learning-test-token-longer-than-32")
    monkeypatch.setattr(consent_module.httpx, "AsyncClient", lambda **_kwargs: fake)
    result = asyncio.run(verify_dsi_consent(
        subject_id="user-dsi-001",
        consent_id="bundle-dsi-test",
        consent_version="dsi-v1",
        resource_id="dsi-session-001",
        purpose=ConsentPurpose.FACIAL_GEOMETRY_ANALYSIS,
    ))
    assert fake.last_request["url"].endswith("/internal/v1/consents/verify")
    assert fake.last_request["json"]["required_scopes"] == ["image_processing", "facial_geometry_analysis"]
    assert fake.last_request["json"]["resource_id"] == "dsi-session-001"
    assert result["verified"] is True


@pytest.mark.parametrize(
    "receipt",
    [
        _consent_receipt(subject="different-user"),
        _consent_receipt(resource="different-resource"),
        _consent_receipt(scopes=["image_processing"]),
        {**_consent_receipt(), "expires_at": None},
        {**_consent_receipt(), "expires_at": "2020-01-01T00:00:00Z"},
        {**_consent_receipt(), "active": False},
        {**_consent_receipt(), "verified": False},
    ],
)
def test_consent_client_rejects_mismatched_inactive_or_expired_receipts(monkeypatch, receipt):
    import app.dsi.consent as consent_module

    fake = FakeAsyncClient(receipt)
    monkeypatch.setenv("IDENTITY_LEARNING_API_URL", "http://localhost:8092")
    monkeypatch.setenv("IDENTITY_LEARNING_API_TOKEN", "identity-learning-test-token-longer-than-32")
    monkeypatch.setattr(consent_module.httpx, "AsyncClient", lambda **_kwargs: fake)
    with pytest.raises(ConsentNotAuthorized):
        asyncio.run(verify_dsi_consent(
            subject_id="user-dsi-001",
            consent_id="bundle-dsi-test",
            consent_version="dsi-v1",
            resource_id="dsi-session-001",
            purpose=ConsentPurpose.FACIAL_GEOMETRY_ANALYSIS,
        ))


def test_consent_client_refuses_missing_or_weak_identity_provider_configuration(monkeypatch):
    monkeypatch.delenv("IDENTITY_LEARNING_API_URL", raising=False)
    monkeypatch.delenv("IDENTITY_LEARNING_API_TOKEN", raising=False)
    with pytest.raises(DSIProviderUnavailable):
        asyncio.run(verify_dsi_consent(
            subject_id="user-dsi-001",
            consent_id="bundle-dsi-test",
            consent_version="dsi-v1",
            resource_id="dsi-session-001",
            purpose=ConsentPurpose.FACIAL_GEOMETRY_ANALYSIS,
        ))
