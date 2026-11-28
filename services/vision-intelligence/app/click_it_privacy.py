"""Fail-closed face anonymization for Click It.

This module performs face *detection* only. It contains no identity, recognition,
verification, embedding, or face-search functionality. The detector asset must be
provisioned out of band and pinned by SHA-256 before Click It can process images.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import threading
from pathlib import Path
from typing import Iterable

import numpy as np
from fastapi import HTTPException
from PIL import Image, ImageFilter

FACE_DETECTION_CONFIDENCE = 0.70
FACE_DETECTOR_CANDIDATE_THRESHOLD = 0.10
FACE_BLUR_RADIUS = 18
FACE_PADDING_FRACTION = 0.22
SHA256_LENGTH = 64
MAX_FACE_DETECTOR_BYTES = 64 * 1024 * 1024
_DETECTOR = None
_DETECTOR_KEY: tuple[str, str] | None = None
_DETECTOR_LOCK = threading.Lock()


def detector_configuration() -> tuple[bool, str]:
    model_path = os.getenv("CLICK_IT_FACE_DETECTOR_MODEL_PATH", "").strip()
    expected = os.getenv("CLICK_IT_FACE_DETECTOR_MODEL_SHA256", "").strip().lower()
    if not model_path or len(expected) != SHA256_LENGTH or any(c not in "0123456789abcdef" for c in expected):
        return False, "pinned_face_detector_asset_required"
    path = Path(model_path)
    if not path.is_file():
        return False, "face_detector_asset_missing"
    try:
        if path.stat().st_size > MAX_FACE_DETECTOR_BYTES:
            return False, "face_detector_asset_too_large"
    except OSError:
        return False, "face_detector_asset_unreadable"
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return False, "face_detector_asset_unreadable"
    if not hmac.compare_digest(digest.hexdigest(), expected):
        return False, "face_detector_asset_sha256_mismatch"
    return True, "configured"


def _create_face_detector(model_asset: bytes):
    """Construct the detector from the exact bytes whose digest was verified."""
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    options = vision.FaceDetectorOptions(
        base_options=python.BaseOptions(model_asset_buffer=model_asset),
        running_mode=vision.RunningMode.IMAGE,
        min_detection_confidence=FACE_DETECTOR_CANDIDATE_THRESHOLD,
    )
    return vision.FaceDetector.create_from_options(options)


def _face_detector():
    global _DETECTOR, _DETECTOR_KEY
    configured, reason = detector_configuration()
    if not configured:
        raise HTTPException(503, detail={"code": "CLICK_IT_PRIVACY_DETECTOR_NOT_READY", "reason": reason})

    model_path = Path(os.environ["CLICK_IT_FACE_DETECTOR_MODEL_PATH"].strip())
    expected = os.environ["CLICK_IT_FACE_DETECTOR_MODEL_SHA256"].strip().lower()
    try:
        resolved_path = model_path.resolve(strict=True)
        with resolved_path.open("rb") as stream:
            model_asset = stream.read(MAX_FACE_DETECTOR_BYTES + 1)
        if len(model_asset) > MAX_FACE_DETECTOR_BYTES:
            raise HTTPException(503, detail={"code": "CLICK_IT_PRIVACY_DETECTOR_NOT_READY", "reason": "face_detector_asset_too_large"})
    except (OSError, RuntimeError) as exc:
        raise HTTPException(503, detail={"code": "CLICK_IT_PRIVACY_DETECTOR_NOT_READY", "reason": "face_detector_asset_unreadable"}) from exc

    # Hash the bytes passed to MediaPipe, not merely the file path checked earlier.
    # This closes the file-replacement window between readiness validation and model loading.
    actual = hashlib.sha256(model_asset).hexdigest()
    if not hmac.compare_digest(actual, expected):
        raise HTTPException(503, detail={"code": "CLICK_IT_PRIVACY_DETECTOR_NOT_READY", "reason": "face_detector_asset_sha256_mismatch"})

    detector_key = (str(resolved_path), expected)
    with _DETECTOR_LOCK:
        if _DETECTOR is not None and _DETECTOR_KEY == detector_key:
            return _DETECTOR

        previous = _DETECTOR
        _DETECTOR = None
        _DETECTOR_KEY = None
        if previous is not None:
            close = getattr(previous, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:
                    raise HTTPException(503, detail={"code": "CLICK_IT_PRIVACY_DETECTOR_RELOAD_FAILED"}) from exc

        try:
            detector = _create_face_detector(model_asset)
        except Exception as exc:
            raise HTTPException(503, detail={"code": "CLICK_IT_PRIVACY_DETECTOR_LOAD_FAILED"}) from exc

        _DETECTOR = detector
        _DETECTOR_KEY = detector_key
        return detector


def mask_face_regions(image: Image.Image, boxes: Iterable[tuple[int, int, int, int]]) -> tuple[Image.Image, int]:
    """Blur every supplied face box with padding; reject malformed detector output."""
    converted = image.convert("RGB")
    try:
        output = converted.copy()
    finally:
        converted.close()
    try:
        regions = list(boxes)
        for box in regions:
            if not isinstance(box, (tuple, list)) or len(box) != 4:
                raise HTTPException(503, detail={"code": "CLICK_IT_PRIVACY_INVALID_DETECTION"})
            x, y, width, height = box
            if any(not isinstance(value, (int, np.integer)) for value in box) or width <= 0 or height <= 0:
                raise HTTPException(503, detail={"code": "CLICK_IT_PRIVACY_INVALID_DETECTION"})
            pad_x = max(4, int(width * FACE_PADDING_FRACTION))
            pad_y = max(4, int(height * FACE_PADDING_FRACTION))
            left = max(0, x - pad_x)
            top = max(0, y - pad_y)
            right = min(output.width, x + width + pad_x)
            bottom = min(output.height, y + height + pad_y)
            if right <= left or bottom <= top:
                raise HTTPException(503, detail={"code": "CLICK_IT_PRIVACY_INVALID_DETECTION"})
            crop = output.crop((left, top, right, bottom))
            try:
                blurred = crop.filter(ImageFilter.GaussianBlur(radius=FACE_BLUR_RADIUS))
                try:
                    output.paste(blurred, (left, top))
                finally:
                    blurred.close()
            finally:
                crop.close()
        return output, len(regions)
    except Exception:
        output.close()
        raise

def anonymize_click_it_image(image: Image.Image) -> tuple[Image.Image, int]:
    """Detect and blur all faces before any Click It embedding or downstream call."""
    try:
        detector = _face_detector()
        import mediapipe as mp

        converted = image.convert("RGB")
        try:
            rgb = np.asarray(converted, dtype=np.uint8)
            result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        finally:
            converted.close()
        detections = getattr(result, "detections", None)
        if detections is None:
            raise HTTPException(503, detail={"code": "CLICK_IT_PRIVACY_DETECTION_UNCERTAIN"})
        boxes: list[tuple[int, int, int, int]] = []
        for detection in detections:
            categories = getattr(detection, "categories", None) or []
            scores = [float(getattr(category, "score", 0.0)) for category in categories]
            confidence = max(scores, default=0.0)
            bounding_box = getattr(detection, "bounding_box", None)
            if confidence < FACE_DETECTION_CONFIDENCE or bounding_box is None:
                raise HTTPException(503, detail={"code": "CLICK_IT_PRIVACY_DETECTION_UNCERTAIN"})
            boxes.append((
                int(bounding_box.origin_x), int(bounding_box.origin_y),
                int(bounding_box.width), int(bounding_box.height),
            ))
        return mask_face_regions(image, boxes)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "CLICK_IT_PRIVACY_DETECTION_FAILED"}) from exc
