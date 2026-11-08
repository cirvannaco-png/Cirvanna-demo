"""Fail-closed face anonymization for Click It.

This module performs face *detection* only. It contains no identity, recognition,
verification, embedding, or face-search functionality. The detector asset must be
provisioned out of band and pinned by SHA-256 before Click It can process images.
"""
from __future__ import annotations

import hashlib
import hmac
import os
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
_DETECTOR = None


def detector_configuration() -> tuple[bool, str]:
    model_path = os.getenv("CLICK_IT_FACE_DETECTOR_MODEL_PATH", "").strip()
    expected = os.getenv("CLICK_IT_FACE_DETECTOR_MODEL_SHA256", "").strip().lower()
    if not model_path or len(expected) != SHA256_LENGTH or any(c not in "0123456789abcdef" for c in expected):
        return False, "pinned_face_detector_asset_required"
    path = Path(model_path)
    if not path.is_file():
        return False, "face_detector_asset_missing"
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


def _face_detector():
    global _DETECTOR
    configured, reason = detector_configuration()
    if not configured:
        raise HTTPException(503, detail={"code": "CLICK_IT_PRIVACY_DETECTOR_NOT_READY", "reason": reason})
    if _DETECTOR is None:
        try:
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision

            options = vision.FaceDetectorOptions(
                base_options=python.BaseOptions(model_asset_path=os.environ["CLICK_IT_FACE_DETECTOR_MODEL_PATH"]),
                running_mode=vision.RunningMode.IMAGE,
                min_detection_confidence=FACE_DETECTOR_CANDIDATE_THRESHOLD,
            )
            _DETECTOR = vision.FaceDetector.create_from_options(options)
        except Exception as exc:
            raise HTTPException(503, detail={"code": "CLICK_IT_PRIVACY_DETECTOR_LOAD_FAILED"}) from exc
    return _DETECTOR


def mask_face_regions(image: Image.Image, boxes: Iterable[tuple[int, int, int, int]]) -> tuple[Image.Image, int]:
    """Blur every supplied face box with padding; reject malformed detector output."""
    output = image.convert("RGB").copy()
    regions = list(boxes)
    try:
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

        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
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
