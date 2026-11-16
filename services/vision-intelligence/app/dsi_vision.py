"""Private DSI visual inference endpoints.

Dedicated worker authentication and task-specific pinned model assets isolate DSI
from generic CLIP/Commerce readiness. Endpoints are stateless and no-store.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import re
import json
import os
from typing import Annotated, Any, Literal

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image
from pydantic import ValidationError

from app.image_io import decode_image, evaluate_image_quality
from app.color_calibration import (
    ColorCalibrationError,
    PROFILE_ID as COLORCHECKER_PROFILE_ID,
    PROFILE_VERSION as COLORCHECKER_PROFILE_VERSION,
    build_skin_colour_preview,
)
from app import dsi_models
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


@router.post("/capture-challenges", dependencies=[Depends(require_dsi_worker)])
async def create_capture_challenge(payload: IdentityCaptureChallengeRequest) -> JSONResponse:
    """Issue the one-time capture nonce only through Identity's live consent check."""
    try:
        challenge = await issue_identity_capture_challenge(payload)
    except CaptureVerificationError as exc:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_CHALLENGE_NOT_AUTHORIZED"}) from exc
    except CaptureVerificationUnavailable as exc:
        raise HTTPException(503, detail={"code": "DSI_CAPTURE_CHALLENGE_PROVIDER_UNAVAILABLE"}) from exc
    return _no_store({"status": "issued", "challenge": challenge})


@router.post("/capture-verifications", dependencies=[Depends(require_dsi_worker)])
async def verify_capture_envelope(
    envelope_json: Annotated[str, Form(min_length=2, max_length=512 * 1024)],
    challenge_nonce_base64url: Annotated[str, Form(min_length=43, max_length=43)],
    image: Annotated[UploadFile, File()],
) -> JSONResponse:
    """Verify native capture proofs and persist the receipt only after both Google checks pass."""
    try:
        envelope = AndroidAttestationEnvelope.model_validate_checked(json.loads(envelope_json))
    except (ValidationError, ValueError, TypeError) as exc:
        await image.close()
        raise HTTPException(422, detail={"code": "DSI_CAPTURE_ENVELOPE_INVALID"}) from exc

    try:
        image_bytes, decoded = await _read_image(image)
        try:
            result = await verify_and_persist_capture(
                envelope,
                challenge_nonce_base64url=challenge_nonce_base64url,
                image_bytes=image_bytes,
            )
        finally:
            decoded.close()
    except CaptureVerificationError as exc:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_PROOF_REJECTED"}) from exc
    except CaptureVerificationUnavailable as exc:
        raise HTTPException(503, detail={"code": "DSI_CAPTURE_VERIFIER_UNAVAILABLE"}) from exc
    return _no_store(result)


def _replay_upload(image_bytes: bytes, content_type: str, filename: str) -> UploadFile:
    from starlette.datastructures import Headers

    return UploadFile(
        filename=filename,
        file=io.BytesIO(image_bytes),
        headers=Headers({"content-type": content_type}),
    )


async def _verify_receipt_before_inference(
    *,
    receipt_id: str,
    subject_id: str,
    resource_id: str,
    purpose: Literal[
        "cosmetic_skin_analysis",
        "facial_geometry_analysis",
        "body_tone_analysis",
        "appearance_correction",
    ],
    manifest_sha256: str,
    image_sha256: str,
    device_pipeline_fingerprint_sha256: str,
    image: UploadFile,
    allowed_purposes: set[str],
) -> tuple[bytes, str]:
    if purpose not in allowed_purposes:
        await image.close()
        raise HTTPException(422, detail={"code": "DSI_CAPTURE_PURPOSE_NOT_ALLOWED"})
    content_type = image.content_type or ""
    image_bytes, decoded = await _read_image(image)
    decoded.close()
    actual_image_sha256 = hashlib.sha256(image_bytes).hexdigest()
    if not hmac.compare_digest(actual_image_sha256, image_sha256):
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_IMAGE_DIGEST_MISMATCH"})
    if not re.fullmatch(r"^[a-f0-9]{64}$", manifest_sha256) or not re.fullmatch(
        r"^[a-f0-9]{64}$", device_pipeline_fingerprint_sha256
    ):
        raise HTTPException(422, detail={"code": "DSI_CAPTURE_RECEIPT_DIGEST_INVALID"})
    try:
        await verify_identity_capture_receipt(
            receipt_id=receipt_id,
            subject_id=subject_id,
            resource_id=resource_id,
            purpose=purpose,
            manifest_sha256=manifest_sha256,
            image_sha256=actual_image_sha256,
            device_pipeline_fingerprint_sha256=device_pipeline_fingerprint_sha256,
        )
    except CaptureVerificationError as exc:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_RECEIPT_REJECTED"}) from exc
    except CaptureVerificationUnavailable as exc:
        raise HTTPException(503, detail={"code": "DSI_CAPTURE_RECEIPT_PROVIDER_UNAVAILABLE"}) from exc
    return image_bytes, content_type


@router.post("/capture/skin-segmentation", dependencies=[Depends(require_dsi_worker)])
async def verified_capture_skin_segmentation(
    receipt_id: Annotated[str, Form(min_length=12, max_length=80)],
    subject_id: Annotated[str, Form(min_length=1, max_length=128)],
    resource_id: Annotated[str, Form(min_length=3, max_length=160)],
    purpose: Annotated[Literal["cosmetic_skin_analysis", "body_tone_analysis"], Form()],
    manifest_sha256: Annotated[str, Form(min_length=64, max_length=64)],
    image_sha256: Annotated[str, Form(min_length=64, max_length=64)],
    device_pipeline_fingerprint_sha256: Annotated[str, Form(min_length=64, max_length=64)],
    image: Annotated[UploadFile, File()],
) -> JSONResponse:
    """Run DSI segmentation only against bytes covered by a live Identity receipt."""
    image_bytes, content_type = await _verify_receipt_before_inference(
        receipt_id=receipt_id,
        subject_id=subject_id,
        resource_id=resource_id,
        purpose=purpose,
        manifest_sha256=manifest_sha256,
        image_sha256=image_sha256,
        device_pipeline_fingerprint_sha256=device_pipeline_fingerprint_sha256,
        image=image,
        allowed_purposes={"cosmetic_skin_analysis", "body_tone_analysis"},
    )
    return await skin_segmentation(
        _replay_upload(image_bytes, content_type, "verified-dsi-capture")
    )


@router.post("/capture/face-landmarks", dependencies=[Depends(require_dsi_worker)])
async def verified_capture_face_landmarks(
    receipt_id: Annotated[str, Form(min_length=12, max_length=80)],
    subject_id: Annotated[str, Form(min_length=1, max_length=128)],
    resource_id: Annotated[str, Form(min_length=3, max_length=160)],
    purpose: Annotated[Literal["facial_geometry_analysis"], Form()],
    manifest_sha256: Annotated[str, Form(min_length=64, max_length=64)],
    image_sha256: Annotated[str, Form(min_length=64, max_length=64)],
    device_pipeline_fingerprint_sha256: Annotated[str, Form(min_length=64, max_length=64)],
    image: Annotated[UploadFile, File()],
) -> JSONResponse:
    """Run geometry preview only against bytes covered by a live Identity receipt."""
    image_bytes, content_type = await _verify_receipt_before_inference(
        receipt_id=receipt_id,
        subject_id=subject_id,
        resource_id=resource_id,
        purpose=purpose,
        manifest_sha256=manifest_sha256,
        image_sha256=image_sha256,
        device_pipeline_fingerprint_sha256=device_pipeline_fingerprint_sha256,
        image=image,
        allowed_purposes={"facial_geometry_analysis"},
    )
    return await face_landmarks(
        _replay_upload(image_bytes, content_type, "verified-dsi-capture")
    )
