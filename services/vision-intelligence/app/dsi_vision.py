"""Private DSI visual inference endpoints.

Dedicated worker authentication and task-specific pinned model assets isolate DSI
from generic CLIP/Commerce readiness. Endpoints are stateless and no-store.
"""
from __future__ import annotations

import base64
import hmac
import io
import json
import os
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlsplit
from typing import Annotated, Any, Literal

import httpx

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from app.image_io import decode_image, evaluate_image_quality
from app.color_calibration import (
    ColorCalibrationError,
    PROFILE_ID as COLORCHECKER_PROFILE_ID,
    PROFILE_VERSION as COLORCHECKER_PROFILE_VERSION,
    build_skin_colour_preview,
)
from app import dsi_models
from app.dsi_capture_verification import (
    CaptureVerificationError,
    verify_android_capture_envelope,
)
from app.dsi_device_baselines import (
    DeviceBaselineError,
    DeviceCaptureReport,
    baseline_result,
    load_device_baseline_registry,
)

router = APIRouter(prefix="/v1/dsi", tags=["dsi"])
bearer = HTTPBearer(auto_error=False)
MAX_DSI_IMAGE_BYTES = 5 * 1024 * 1024
MAX_DSI_IMAGE_PIXELS = 16_000_000


def require_dsi_worker(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("DSI_VISION_WORKER_TOKEN", "")
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "DSI_VISION_AUTH_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            401,
            detail={"code": "UNAUTHORIZED"},
            headers={"WWW-Authenticate": "Bearer"},
        )


def _no_store(payload: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )


async def _read_image(image: UploadFile) -> tuple[bytes, Any]:
    content_type = image.content_type or ""
    try:
        data = await image.read(MAX_DSI_IMAGE_BYTES + 1)
    finally:
        await image.close()
    if len(data) > MAX_DSI_IMAGE_BYTES:
        raise HTTPException(
            413,
            detail={"code": "IMAGE_SIZE_LIMIT_EXCEEDED", "maximum_bytes": MAX_DSI_IMAGE_BYTES},
        )
    decoded = decode_image(
        data,
        content_type,
        max_bytes=MAX_DSI_IMAGE_BYTES,
        max_pixels=MAX_DSI_IMAGE_PIXELS,
    )
    quality = evaluate_image_quality(decoded)
    if not quality["passed"]:
        decoded.close()
        raise HTTPException(422, detail={"code": "IMAGE_QUALITY_REJECTED", "quality": quality})
    return data, decoded


def _mp_image(image: Image.Image):
    import mediapipe as mp

    rgb = np.asarray(image, dtype=np.uint8)
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)


@router.get("/ready", dependencies=[Depends(require_dsi_worker)])
def dsi_ready() -> JSONResponse:
    face = dsi_models.face_landmarker_status()
    segmenter = dsi_models.skin_segmenter_status()
    face_loaded = False
    segmenter_loaded = False
    face_load_error = None
    segmenter_load_error = None
    if face["configured"] is True:
        try:
            dsi_models.get_face_landmarker()
            face_loaded = True
        except Exception:
            face_load_error = "face_landmarker_load_failed"
    if segmenter["configured"] is True:
        try:
            dsi_models.get_skin_segmenter()
            segmenter_loaded = True
        except Exception:
            segmenter_load_error = "skin_segmenter_load_or_label_map_failed"
    ready = face_loaded and segmenter_loaded
    return _no_store({
        "service": "cirvanna-vision-intelligence",
        "dsi_ready": ready,
        "face_landmarker": {
            "configured": face["configured"],
            "loaded": face_loaded,
            "reason": face_load_error or face["reason"],
            "model_version": face.get("version"),
            "model_sha256": face.get("sha256"),
        },
        "skin_segmenter": {
            "configured": segmenter["configured"],
            "loaded": segmenter_loaded,
            "reason": segmenter_load_error or segmenter["reason"],
            "model_version": segmenter.get("version"),
            "model_sha256": segmenter.get("sha256"),
        },
        "image_persistence": False,
        "face_recognition": False,
        "identity_matching": False,
        "face_embeddings": False,
        "age_estimation": False,
        "video_processing": False,
    }, status_code=200 if ready else 503)


@router.post("/face-landmarks", dependencies=[Depends(require_dsi_worker)])
async def face_landmarks(image: Annotated[UploadFile, File()]) -> JSONResponse:
    """Return single-face 478-point geometry landmarks; no identity features."""
    _data, decoded = await _read_image(image)
    try:
        try:
            landmarker = dsi_models.get_face_landmarker()
            result = landmarker.detect(_mp_image(decoded))
        except Exception as exc:
            raise HTTPException(503, detail={"code": "DSI_FACE_LANDMARKER_UNAVAILABLE"}) from exc
        faces = getattr(result, "face_landmarks", None) or []
        if len(faces) == 0:
            raise HTTPException(422, detail={"code": "DSI_FACE_NOT_DETECTED"})
        if len(faces) != 1:
            raise HTTPException(422, detail={"code": "DSI_SINGLE_FACE_REQUIRED"})
        points = faces[0]
        if len(points) != dsi_models.FACE_LANDMARK_COUNT:
            raise HTTPException(502, detail={"code": "DSI_FACE_LANDMARK_CONTRACT_MISMATCH"})
        landmarks: list[dict[str, float]] = []
        for point in points:
            x = float(getattr(point, "x", float("nan")))
            y = float(getattr(point, "y", float("nan")))
            z = float(getattr(point, "z", float("nan")))
            if not np.isfinite([x, y, z]).all() or not (-0.05 <= x <= 1.05) or not (-0.05 <= y <= 1.05):
                raise HTTPException(502, detail={"code": "DSI_INVALID_FACE_LANDMARK"})
            landmarks.append({"x": round(x, 7), "y": round(y, 7), "z": round(z, 7)})
        meta = dsi_models.face_landmarker_status()
        return _no_store({
            "status": "landmarks_detected_unvalidated_geometry",
            "width": decoded.width,
            "height": decoded.height,
            "landmark_count": len(landmarks),
            "landmarks": landmarks,
            "model": {
                "family": "MediaPipe Face Landmarker",
                "version": meta["version"],
                "sha256": meta["sha256"],
            },
            "input_quality": evaluate_image_quality(decoded),
            "face_blendshapes_computed": False,
            "facial_transformation_matrices_computed": False,
            "face_embeddings_computed": False,
            "face_recognition_performed": False,
            "identity_matching_performed": False,
            "age_estimation_performed": False,
            "image_persisted": False,
            "disclaimer": (
                "Landmarks are geometric model output, not identity, clinical, "
                "demographic or validated beauty measurements. Validate ratios "
                "against an independently labelled dataset before product claims."
            ),
        })
    finally:
        decoded.close()


def _png_base64(mask: np.ndarray) -> str:
    output = io.BytesIO()
    Image.fromarray(mask.astype(np.uint8), mode="L").save(output, format="PNG", optimize=False)
    return base64.b64encode(output.getvalue()).decode("ascii")


@router.post("/skin-segmentation", dependencies=[Depends(require_dsi_worker)])
async def skin_segmentation(image: Annotated[UploadFile, File()]) -> JSONResponse:
    """Return in-memory, pixel-aligned skin-region masks for authorized DSI callers."""
    _data, decoded = await _read_image(image)
    try:
        try:
            segmenter = dsi_models.get_skin_segmenter()
            result = segmenter.segment(_mp_image(decoded))
        except Exception as exc:
            raise HTTPException(503, detail={"code": "DSI_SKIN_SEGMENTER_UNAVAILABLE"}) from exc

        labels = getattr(segmenter, "labels", None)
        if callable(labels):
            labels = labels()
        if not isinstance(labels, (list, tuple)) or tuple(str(item).strip().casefold() for item in labels) != dsi_models.EXPECTED_SEGMENTATION_LABELS:
            raise HTTPException(503, detail={"code": "DSI_SEGMENTATION_LABEL_MAP_MISMATCH"})

        category_mask = getattr(result, "category_mask", None)
        if category_mask is None:
            raise HTTPException(502, detail={"code": "DSI_CATEGORY_MASK_MISSING"})
        categories = np.asarray(category_mask.numpy_view())
        if categories.ndim != 2 or categories.shape != (decoded.height, decoded.width):
            raise HTTPException(502, detail={"code": "DSI_CATEGORY_MASK_SHAPE_INVALID"})
        if not np.issubdtype(categories.dtype, np.integer):
            raise HTTPException(502, detail={"code": "DSI_CATEGORY_MASK_TYPE_INVALID"})
        if categories.size == 0 or int(categories.max()) >= len(labels) or int(categories.min()) < 0:
            raise HTTPException(502, detail={"code": "DSI_CATEGORY_MASK_LABEL_INVALID"})

        confidence_masks = getattr(result, "confidence_masks", None) or []
        if len(confidence_masks) != len(labels):
            raise HTTPException(502, detail={"code": "DSI_CONFIDENCE_MASK_COUNT_INVALID"})
        confidence_arrays: list[np.ndarray] = []
        for mask in confidence_masks:
            values = np.asarray(mask.numpy_view(), dtype=np.float32)
            if values.shape != categories.shape or not np.isfinite(values).all():
                raise HTTPException(502, detail={"code": "DSI_CONFIDENCE_MASK_INVALID"})
            if float(values.min()) < 0.0 or float(values.max()) > 1.0:
                raise HTTPException(502, detail={"code": "DSI_CONFIDENCE_MASK_RANGE_INVALID"})
            confidence_arrays.append(values)

        face_mask = categories == 3
        body_mask = categories == 2
        meta = dsi_models.skin_segmenter_status()
        total = int(categories.size)
        return _no_store({
            "status": "segmentation_detected_unvalidated_skin_masks",
            "width": decoded.width,
            "height": decoded.height,
            "labels": list(labels),
            "region_coverage": {
                "face_skin_fraction": round(float(face_mask.sum()) / total, 7),
                "body_skin_fraction": round(float(body_mask.sum()) / total, 7),
                "hair_fraction": round(float(np.count_nonzero(categories == 1)) / total, 7),
                "clothing_fraction": round(float(np.count_nonzero(categories == 4)) / total, 7),
            },
            "face_skin_mask_png_base64": _png_base64(face_mask * 255),
            "body_skin_mask_png_base64": _png_base64(body_mask * 255),
            "mean_model_confidence_noncalibrated": {
                "face_skin": round(float(confidence_arrays[3][face_mask].mean()), 7) if face_mask.any() else None,
                "body_skin": round(float(confidence_arrays[2][body_mask].mean()), 7) if body_mask.any() else None,
            },
            "model": {
                "family": "MediaPipe Image Segmenter",
                "version": meta["version"],
                "sha256": meta["sha256"],
            },
            "input_quality": evaluate_image_quality(decoded),
            "skin_tone_value_computed": False,
            "absolute_color_calibration_performed": False,
            "image_persisted": False,
            "disclaimer": (
                "Segmentation identifies model-predicted face/body skin regions; it does not "
                "measure exact skin colour, diagnose conditions, determine identity, or validate "
                "regional body tone. Model confidence is not a calibrated probability."
            ),
        })
    finally:
        decoded.close()


@router.post("/colorchecker-tone-preview", dependencies=[Depends(require_dsi_worker)])
async def colorchecker_tone_preview(
    image: Annotated[UploadFile, File()],
    profile_id: Annotated[str, Form(min_length=1, max_length=128)],
    patch_grid_corners: Annotated[str, Form(min_length=20, max_length=1000)],
    chart_edition_confirmed_after_2014: Annotated[bool, Form()],
    chart_age_months: Annotated[int | None, Form(ge=0)] = None,
    chart_condition: Annotated[str, Form(pattern="^(good|worn|unknown)$")] = "unknown",
    requested_region: Annotated[Literal["face_skin", "body_skin", "both"], Form()] = "both",
) -> JSONResponse:
    """Return an experimental same-frame ColorChecker skin-colour preview.

    The four corner points identify the outer bounds of the 6-by-4 patch grid,
    ordered top-left, top-right, bottom-right, bottom-left, in source-image pixels.
    """
    if profile_id != COLORCHECKER_PROFILE_ID:
        await image.close()
        raise HTTPException(422, detail={"code": "DSI_COLOR_REFERENCE_PROFILE_UNSUPPORTED"})
    if chart_edition_confirmed_after_2014 is not True:
        await image.close()
        raise HTTPException(422, detail={"code": "DSI_COLOR_REFERENCE_EDITION_NOT_CONFIRMED"})
    try:
        corners = json.loads(patch_grid_corners)
    except (TypeError, ValueError) as exc:
        await image.close()
        raise HTTPException(422, detail={"code": "DSI_PATCH_GRID_CORNERS_INVALID"}) from exc

    _data, decoded = await _read_image(image)
    try:
        try:
            segmenter = dsi_models.get_skin_segmenter()
            result = segmenter.segment(_mp_image(decoded))
        except Exception as exc:
            raise HTTPException(503, detail={"code": "DSI_SKIN_SEGMENTER_UNAVAILABLE"}) from exc

        labels = getattr(segmenter, "labels", None)
        if callable(labels):
            labels = labels()
        normalized_labels = (
            tuple(str(item).strip().casefold() for item in labels)
            if isinstance(labels, (list, tuple)) else ()
        )
        if normalized_labels != dsi_models.EXPECTED_SEGMENTATION_LABELS:
            raise HTTPException(503, detail={"code": "DSI_SEGMENTATION_LABEL_MAP_MISMATCH"})

        category_mask = getattr(result, "category_mask", None)
        if category_mask is None:
            raise HTTPException(502, detail={"code": "DSI_CATEGORY_MASK_MISSING"})
        categories = np.asarray(category_mask.numpy_view())
        if categories.ndim != 2 or categories.shape != (decoded.height, decoded.width):
            raise HTTPException(502, detail={"code": "DSI_CATEGORY_MASK_SHAPE_INVALID"})
        if not np.issubdtype(categories.dtype, np.integer):
            raise HTTPException(502, detail={"code": "DSI_CATEGORY_MASK_TYPE_INVALID"})
        if categories.size == 0 or int(categories.max()) >= len(normalized_labels) or int(categories.min()) < 0:
            raise HTTPException(502, detail={"code": "DSI_CATEGORY_MASK_LABEL_INVALID"})

        preview = build_skin_colour_preview(
            decoded,
            categories,
            patch_grid_corners=corners,
            chart_age_months_declared=chart_age_months,
            chart_condition_declared=chart_condition,
            requested_region=requested_region,
        )
        segmenter_meta = dsi_models.skin_segmenter_status()
        preview["skin_segmentation_model"] = {
            "family": "MediaPipe Image Segmenter",
            "version": segmenter_meta["version"],
            "sha256": segmenter_meta["sha256"],
        }
        preview["input_quality"] = evaluate_image_quality(decoded)
        preview["input_rgb_interpretation"] = "embedded ICC profiles normalized to sRGB; absent profile assumed sRGB"
        return _no_store(preview)
    except ColorCalibrationError as exc:
        raise HTTPException(
            422,
            detail={"code": "DSI_COLOR_CALIBRATION_INPUT_INVALID", "reason": str(exc)},
        ) from exc
    finally:
        decoded.close()



@router.post("/device-baseline", dependencies=[Depends(require_dsi_worker)])
async def device_baseline(report: DeviceCaptureReport) -> JSONResponse:
    """Resolve an exact device pipeline profile without trusting client declarations.

    No image is accepted. Until a trusted capture-attestation verifier is wired
    in, this public internal route always returns a relative-only effective tier.
    """
    try:
        registry, configured = load_device_baseline_registry()
    except DeviceBaselineError as exc:
        raise HTTPException(
            503,
            detail={"code": "DSI_DEVICE_BASELINE_REGISTRY_UNAVAILABLE"},
        ) from exc

    result = baseline_result(
        report,
        registry,
        registry_configured=configured,
        capture_attestation_verified=False,
    )
    return _no_store(result)


DSI_CAPTURE_PURPOSES = {
    "cosmetic_skin_analysis": {"image_processing", "skin_analysis"},
    "facial_geometry_analysis": {"image_processing", "facial_geometry_analysis"},
    "body_tone_analysis": {"image_processing", "body_tone_analysis"},
    "appearance_correction": {"image_processing", "appearance_correction"},
}


class DSICaptureChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    subject_id: str = Field(min_length=1, max_length=128)
    consent_id: str = Field(min_length=8, max_length=128)
    consent_version: str = Field(min_length=1, max_length=80)
    resource_id: str = Field(min_length=3, max_length=160)
    purpose: Literal[
        "cosmetic_skin_analysis",
        "facial_geometry_analysis",
        "body_tone_analysis",
        "appearance_correction",
    ]


class DSICaptureReceiptVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    receipt_id: str = Field(min_length=12, max_length=80)
    subject_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=3, max_length=160)
    purpose: Literal[
        "cosmetic_skin_analysis",
        "facial_geometry_analysis",
        "body_tone_analysis",
        "appearance_correction",
    ]
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    device_pipeline_fingerprint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def _identity_dsi_capture_config() -> tuple[str, str]:
    base = os.getenv("IDENTITY_LEARNING_API_URL", "").strip().rstrip("/")
    token = os.getenv("IDENTITY_DSI_CAPTURE_SERVICE_TOKEN", "").strip()
    parsed = urlsplit(base)
    host = (parsed.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not base
        or len(token.encode("utf-8")) < 32
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (parsed.scheme != "https" and not (parsed.scheme == "http" and local))
    ):
        raise HTTPException(503, detail={"code": "IDENTITY_DSI_CAPTURE_PROVIDER_NOT_CONFIGURED"})
    return base, token


async def _identity_dsi_capture_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base, token = _identity_dsi_capture_config()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, connect=2.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(
                base + path,
                headers={
                    "Authorization": "Bearer " + token,
                    "Accept": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "IDENTITY_DSI_CAPTURE_PROVIDER_UNAVAILABLE"}) from exc

    if response.status_code in {401, 403, 404, 409, 410}:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_AUTHORIZATION_REJECTED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "IDENTITY_DSI_CAPTURE_PROVIDER_UNAVAILABLE"})
    if "no-store" not in response.headers.get("cache-control", "").casefold():
        raise HTTPException(503, detail={"code": "IDENTITY_DSI_CAPTURE_CACHE_POLICY_INVALID"})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "IDENTITY_DSI_CAPTURE_RESPONSE_INVALID"}) from exc
    if not isinstance(result, dict):
        raise HTTPException(503, detail={"code": "IDENTITY_DSI_CAPTURE_RESPONSE_INVALID"})
    return result


@router.post("/capture-challenges", dependencies=[Depends(require_dsi_worker)])
async def create_capture_challenge(payload: DSICaptureChallengeRequest) -> JSONResponse:
    """Issue a one-use, consent-bound challenge through Identity Learning."""
    identity = await _identity_dsi_capture_post(
        "/internal/v1/dsi/capture-challenges",
        payload.model_dump(mode="json"),
    )
    try:
        nonce_text = identity["nonce_b64url"]
        nonce = base64.urlsafe_b64decode(
            nonce_text + ("=" * ((4 - len(nonce_text) % 4) % 4))
        )
        expected_nonce_sha = hashlib.sha256(nonce).hexdigest()
        expiry = datetime.fromisoformat(identity["expires_at"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(503, detail={"code": "IDENTITY_DSI_CAPTURE_RESPONSE_INVALID"}) from exc
    if (
        identity.get("status") != "issued"
        or identity.get("subject_id") != payload.subject_id
        or identity.get("consent_id") != payload.consent_id
        or identity.get("consent_version") != payload.consent_version
        or identity.get("resource_id") != payload.resource_id
        or identity.get("purpose") != payload.purpose
        or len(nonce) != 32
        or identity.get("nonce_bytes") != 32
        or identity.get("nonce_sha256") != expected_nonce_sha
        or expiry.tzinfo is None
        or expiry <= datetime.now(timezone.utc)
        or not isinstance(identity.get("challenge_id"), str)
        or not isinstance(identity.get("consent_receipt_ids"), list)
        or len(identity["consent_receipt_ids"]) < 2
    ):
        raise HTTPException(503, detail={"code": "IDENTITY_DSI_CAPTURE_RESPONSE_INVALID"})
    return _no_store({
        "status": "challenge_issued",
        "challenge_id": identity["challenge_id"],
        "nonce_b64url": nonce_text,
        "nonce_bytes": 32,
        "expires_at": identity["expires_at"],
        "subject_id": payload.subject_id,
        "consent_id": payload.consent_id,
        "consent_version": payload.consent_version,
        "resource_id": payload.resource_id,
        "purpose": payload.purpose,
        "required_scopes": sorted(DSI_CAPTURE_PURPOSES[payload.purpose]),
        "verification_state": "pending_server_verification",
    })


@router.post("/capture-verifications", dependencies=[Depends(require_dsi_worker)])
async def verify_capture_envelope(
    subject_id: Annotated[str, Form(min_length=1, max_length=128)],
    consent_id: Annotated[str, Form(min_length=8, max_length=128)],
    consent_version: Annotated[str, Form(min_length=1, max_length=80)],
    resource_id: Annotated[str, Form(min_length=3, max_length=160)],
    purpose: Annotated[
        Literal[
            "cosmetic_skin_analysis",
            "facial_geometry_analysis",
            "body_tone_analysis",
            "appearance_correction",
        ],
        Form(),
    ],
    challenge_id: Annotated[str, Form(min_length=12, max_length=80)],
    nonce_b64url: Annotated[str, Form(min_length=43, max_length=64)],
    manifest_canonical_json: Annotated[str, Form(min_length=2, max_length=128 * 1024)],
    manifest_signature_base64url: Annotated[str, Form(min_length=80, max_length=512)],
    attestation_certificate_chain_base64url: Annotated[str, Form(min_length=40, max_length=256 * 1024)],
    play_integrity_token: Annotated[str, Form(min_length=100, max_length=16 * 1024)],
    image: Annotated[UploadFile, File()],
) -> JSONResponse:
    """Verify image, Android Key Attestation and Play Integrity before receipt creation.

    No client-provided verification booleans or device tier are accepted. Identity
    Learning is called only after both independent Google-backed verifiers succeed.
    """
    _data, decoded = await _read_image(image)
    try:
        try:
            chain = json.loads(attestation_certificate_chain_base64url)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, detail={"code": "DSI_ANDROID_ATTESTATION_CHAIN_INVALID"}) from exc
        if (
            not isinstance(chain, list)
            or not (2 <= len(chain) <= 8)
            or any(not isinstance(item, str) for item in chain)
        ):
            raise HTTPException(422, detail={"code": "DSI_ANDROID_ATTESTATION_CHAIN_INVALID"})

        try:
            verified = await verify_android_capture_envelope(
                challenge_id=challenge_id,
                nonce_b64url=nonce_b64url,
                manifest_text=manifest_canonical_json,
                manifest_signature_b64url=manifest_signature_base64url,
                attestation_certificate_chain_base64url=chain,
                play_integrity_token=play_integrity_token,
                image_bytes=_data,
            )
        except CaptureVerificationError as exc:
            raise HTTPException(
                exc.status_code,
                detail={"code": exc.code},
            ) from exc

        sdk_version = os.getenv("DSI_ANDROID_CAPTURE_SDK_VERSION", "").strip()
        if not sdk_version:
            raise HTTPException(503, detail={"code": "DSI_ANDROID_CAPTURE_SDK_VERSION_NOT_CONFIGURED"})

        nonce = base64.urlsafe_b64decode(
            nonce_b64url + ("=" * ((4 - len(nonce_b64url) % 4) % 4))
        )
        consume_payload = {
            "nonce_b64url": nonce_b64url,
            "manifest_sha256": verified.manifest_sha256,
            "image_sha256": verified.image_sha256,
            "device_pipeline_fingerprint_sha256": verified.device_pipeline_fingerprint_sha256,
            "key_attestation_challenge_sha256": hashlib.sha256(nonce).hexdigest(),
            # Identity persists the canonical hexadecimal digest, not the base64url
            # wire representation returned by Play Integrity.
            "play_integrity_request_hash": verified.play_integrity_request_hash,
            "package_name": verified.package_name,
            "package_certificate_sha256": verified.package_certificate_sha256,
            "app_version": verified.app_version,
            "sdk_version": sdk_version,
            "verifier_policy_version": os.getenv("DSI_CAPTURE_VERIFIER_POLICY_VERSION", "dsi-android-policy-v1"),
            "key_security_level": verified.key_security_level,
            "verified_boot_state": verified.verified_boot_state,
            "app_recognition_verdict": verified.app_recognition_verdict,
            "account_licensing_verdict": verified.account_licensing_verdict,
            "device_integrity_verdicts": list(verified.device_integrity_verdicts),
        }
        identity = await _identity_dsi_capture_post(
            f"/internal/v1/dsi/capture-challenges/{challenge_id}/consume",
            consume_payload,
        )
        receipt = identity.get("receipt")
        if (
            identity.get("status") != "verified_receipt_created"
            or not isinstance(receipt, dict)
            or receipt.get("manifest_sha256") != verified.manifest_sha256
            or receipt.get("image_sha256") != verified.image_sha256
            or receipt.get("device_pipeline_fingerprint_sha256") != verified.device_pipeline_fingerprint_sha256
            or receipt.get("verification_status") != "verified_by_trusted_vision_service"
        ):
            raise HTTPException(503, detail={"code": "IDENTITY_DSI_CAPTURE_RECEIPT_INVALID"})
        return _no_store({
            "status": "capture_verified",
            "receipt": receipt,
            "verification": {
                "android_key_attestation": "verified",
                "play_integrity": "verified",
                "verified_boot_state": verified.verified_boot_state,
                "device_locked": verified.device_locked,
                "key_security_level": verified.key_security_level,
                "app_recognition_verdict": verified.app_recognition_verdict,
                "account_licensing_verdict": verified.account_licensing_verdict,
                "device_integrity_verdicts": list(verified.device_integrity_verdicts),
            },
            # Capture verification is not scientific colour measurement approval.
            "absolute_colour_measurement_approved": False,
            "measurement_release_required": True,
        })
    finally:
        decoded.close()


@router.post("/capture-receipts/verify", dependencies=[Depends(require_dsi_worker)])
async def verify_capture_receipt(
    payload: DSICaptureReceiptVerificationRequest,
) -> JSONResponse:
    """Re-check exact capture digest scope and live consent before each use."""
    identity = await _identity_dsi_capture_post(
        "/internal/v1/dsi/capture-receipts/verify",
        payload.model_dump(mode="json"),
    )
    if identity.get("verified") is not True:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_RECEIPT_NOT_VERIFIED"})
    receipt = identity.get("receipt")
    if (
        not isinstance(receipt, dict)
        or receipt.get("receipt_id") != payload.receipt_id
        or receipt.get("subject_id") != payload.subject_id
        or receipt.get("resource_id") != payload.resource_id
        or receipt.get("purpose") != payload.purpose
        or receipt.get("manifest_sha256") != payload.manifest_sha256
        or receipt.get("image_sha256") != payload.image_sha256
        or receipt.get("device_pipeline_fingerprint_sha256") != payload.device_pipeline_fingerprint_sha256
        or receipt.get("verification_status") != "verified_by_trusted_vision_service"
    ):
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_RECEIPT_SCOPE_MISMATCH"})
    return _no_store({"verified": True, "receipt": receipt})
