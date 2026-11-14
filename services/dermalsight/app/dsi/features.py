"""Provisional geometry summaries from 478 MediaPipe facial landmarks.

These ratios are geometric previews only. They are not validated face-shape
classifications, biometric identity templates, or calibrated anthropometry.
"""
from __future__ import annotations

import math
from typing import Any


def _distance(a: dict[str, float], b: dict[str, float], width: int, height: int) -> float:
    ax, ay = a["x"] * width, a["y"] * height
    bx, by = b["x"] * width, b["y"] * height
    return math.hypot(ax - bx, ay - by)


def summarize_face_geometry(payload: dict[str, Any]) -> dict[str, object]:
    landmarks = payload.get("landmarks")
    width, height = payload.get("width"), payload.get("height")
    if not isinstance(landmarks, list) or len(landmarks) != 478:
        raise ValueError("478 facial landmarks required")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise ValueError("valid image dimensions required")
    for point in landmarks:
        if not isinstance(point, dict) or any(
            not isinstance(point.get(key), (int, float)) or not math.isfinite(float(point[key]))
            for key in ("x", "y", "z")
        ):
            raise ValueError("invalid facial landmark coordinate")

    # MediaPipe Face Mesh reference indices. These are geometric anchors, not
    # an externally validated face-shape taxonomy.
    cheek_width = _distance(landmarks[234], landmarks[454], width, height)
    face_height = _distance(landmarks[10], landmarks[152], width, height)
    jaw_width = _distance(landmarks[172], landmarks[397], width, height)
    forehead_width = _distance(landmarks[103], landmarks[332], width, height)
    if min(cheek_width, face_height) <= 1e-6:
        raise ValueError("degenerate facial geometry")
    return {
        "status": "unvalidated_geometry_preview",
        "face_shape": "not_classified",
        "hairline_shape": "not_classified",
        "ratios": {
            "face_width_to_height": round(cheek_width / face_height, 6),
            "jaw_width_to_cheek_width": round(jaw_width / cheek_width, 6),
            "forehead_width_to_cheek_width": round(forehead_width / cheek_width, 6),
        },
        "measurement_uncertainty": "not_calibrated_or_independently_validated",
        "landmark_count": 478,
        "model": payload["model"],
    }
