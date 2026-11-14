"""Pinned, lazy-loaded DSI models for facial landmarks and skin segmentation.

Model weights are provisioned out-of-band. This module never downloads weights,
stores user media, computes face embeddings, or performs identity analysis.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from typing import Any

FACE_LANDMARK_COUNT = 478
EXPECTED_SEGMENTATION_LABELS = (
    "background",
    "hair",
    "body-skin",
    "face-skin",
    "clothes",
    "others",
)
_FACE_LANDMARKER: Any | None = None
_SKIN_SEGMENTER: Any | None = None


def _artifact_status(path_env: str, sha_env: str, version_env: str) -> dict[str, object]:
    path = os.getenv(path_env, "").strip()
    expected = os.getenv(sha_env, "").strip().lower()
    version = os.getenv(version_env, "").strip()
    if not path or len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        return {"configured": False, "reason": "model_path_sha256_and_version_required"}
    if not version or len(version) > 128:
        return {"configured": False, "reason": "model_version_required"}
    asset = Path(path)
    if not asset.is_file():
        return {"configured": False, "reason": "model_asset_missing"}
    digest = hashlib.sha256()
    try:
        with asset.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return {"configured": False, "reason": "model_asset_unreadable"}
    actual = digest.hexdigest()
    if not hmac.compare_digest(actual, expected):
        return {"configured": False, "reason": "model_asset_sha256_mismatch"}
    return {
        "configured": True,
        "reason": None,
        "path": str(asset),
        "sha256": actual,
        "version": version,
    }


def face_landmarker_status() -> dict[str, object]:
    return _artifact_status(
        "DSI_FACE_LANDMARKER_MODEL_PATH",
        "DSI_FACE_LANDMARKER_MODEL_SHA256",
        "DSI_FACE_LANDMARKER_MODEL_VERSION",
    )


def skin_segmenter_status() -> dict[str, object]:
    return _artifact_status(
        "DSI_SKIN_SEGMENTER_MODEL_PATH",
        "DSI_SKIN_SEGMENTER_MODEL_SHA256",
        "DSI_SKIN_SEGMENTER_MODEL_VERSION",
    )


def get_face_landmarker():
    global _FACE_LANDMARKER
    status = face_landmarker_status()
    if not status["configured"]:
        raise RuntimeError(str(status["reason"]))
    if _FACE_LANDMARKER is None:
        import mediapipe as mp

        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(status["path"])),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_faces=2,
            min_face_detection_confidence=0.60,
            min_face_presence_confidence=0.60,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        _FACE_LANDMARKER = mp.tasks.vision.FaceLandmarker.create_from_options(options)
    return _FACE_LANDMARKER


def get_skin_segmenter():
    global _SKIN_SEGMENTER
    status = skin_segmenter_status()
    if not status["configured"]:
        raise RuntimeError(str(status["reason"]))
    if _SKIN_SEGMENTER is None:
        import mediapipe as mp

        options = mp.tasks.vision.ImageSegmenterOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(status["path"])),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            display_names_locale="en",
            output_category_mask=True,
            output_confidence_masks=True,
        )
        segmenter = mp.tasks.vision.ImageSegmenter.create_from_options(options)
        labels = getattr(segmenter, "labels", None)
        if callable(labels):
            labels = labels()
        normalized = tuple(str(item).strip().casefold() for item in labels) if isinstance(labels, (list, tuple)) else ()
        if normalized != EXPECTED_SEGMENTATION_LABELS:
            close = getattr(segmenter, "close", None)
            if callable(close):
                close()
            raise RuntimeError("skin_segmenter_label_map_mismatch")
        _SKIN_SEGMENTER = segmenter
    return _SKIN_SEGMENTER


def reset_loaded_models_for_tests() -> None:
    """Close test/runtime instances when supported; never called from request code."""
    global _FACE_LANDMARKER, _SKIN_SEGMENTER
    for model in (_FACE_LANDMARKER, _SKIN_SEGMENTER):
        close = getattr(model, "close", None)
        if callable(close):
            close()
    _FACE_LANDMARKER = None
    _SKIN_SEGMENTER = None
