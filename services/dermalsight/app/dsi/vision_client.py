"""Trusted internal client for the dedicated DSI Vision endpoints."""
from __future__ import annotations

import os
from urllib.parse import urlsplit

import httpx

from .consent import ConsentProviderUnavailable


def _config() -> tuple[str, str]:
    base = os.getenv("DSI_VISION_API_URL", "").strip().rstrip("/")
    token = os.getenv("DSI_VISION_API_TOKEN", "").strip()
    if not base or len(token.encode("utf-8")) < 32:
        raise ConsentProviderUnavailable("dsi_vision_provider_not_configured")
    parsed = urlsplit(base)
    host = (parsed.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (parsed.scheme != "https" and not (parsed.scheme == "http" and local))
    ):
        raise ConsentProviderUnavailable("dsi_vision_provider_url_invalid")
    return base, token


async def _post_image(path: str, *, content: bytes, content_type: str, filename: str) -> dict:
    base, token = _config()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=2.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(
                base + path,
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                files={"image": (filename, content, content_type)},
            )
    except httpx.TimeoutException as exc:
        raise ConsentProviderUnavailable("dsi_vision_timeout") from exc
    except httpx.HTTPError as exc:
        raise ConsentProviderUnavailable("dsi_vision_unavailable") from exc
    if response.status_code != 200:
        raise ConsentProviderUnavailable("dsi_vision_inference_unavailable")
    if "no-store" not in response.headers.get("cache-control", "").casefold():
        raise ConsentProviderUnavailable("dsi_vision_cache_policy_invalid")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ConsentProviderUnavailable("dsi_vision_invalid_response") from exc
    if not isinstance(payload, dict):
        raise ConsentProviderUnavailable("dsi_vision_invalid_response")
    return payload


async def fetch_face_landmarks(*, content: bytes, content_type: str, filename: str) -> dict:
    payload = await _post_image(
        "/v1/dsi/face-landmarks",
        content=content,
        content_type=content_type,
        filename=filename,
    )
    model = payload.get("model")
    landmarks = payload.get("landmarks")
    if not (
        payload.get("status") == "landmarks_detected_unvalidated_geometry"
        and payload.get("landmark_count") == 478
        and isinstance(landmarks, list)
        and len(landmarks) == 478
        and isinstance(model, dict)
        and isinstance(model.get("version"), str)
        and isinstance(model.get("sha256"), str)
        and len(model["sha256"]) == 64
        and payload.get("image_persisted") is False
        and payload.get("face_recognition_performed") is False
        and payload.get("identity_matching_performed") is False
        and payload.get("age_estimation_performed") is False
    ):
        raise ConsentProviderUnavailable("dsi_vision_face_contract_invalid")
    return payload


async def fetch_skin_segmentation(*, content: bytes, content_type: str, filename: str) -> dict:
    payload = await _post_image(
        "/v1/dsi/skin-segmentation",
        content=content,
        content_type=content_type,
        filename=filename,
    )
    model = payload.get("model")
    coverage = payload.get("region_coverage")
    expected_labels = ["background", "hair", "body-skin", "face-skin", "clothes", "others"]
    if not (
        payload.get("status") == "segmentation_detected_unvalidated_skin_masks"
        and payload.get("labels") == expected_labels
        and isinstance(coverage, dict)
        and isinstance(model, dict)
        and isinstance(model.get("version"), str)
        and isinstance(model.get("sha256"), str)
        and len(model["sha256"]) == 64
        and payload.get("image_persisted") is False
        and payload.get("skin_tone_value_computed") is False
        and payload.get("absolute_color_calibration_performed") is False
    ):
        raise ConsentProviderUnavailable("dsi_vision_segmentation_contract_invalid")
    return payload
