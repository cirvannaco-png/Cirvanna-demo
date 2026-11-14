"""Private DSI visual inference endpoints.

Dedicated worker authentication and task-specific pinned model assets isolate DSI
from generic CLIP/Commerce readiness. Endpoints are stateless and no-store.
"""
from __future__ import annotations

import base64
import hmac
import io
import os
from typing import Annotated, Any

import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image

from app.image_io import decode_image, evaluate_image_quality
from app import dsi_models

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
