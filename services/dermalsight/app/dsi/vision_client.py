"""Trusted internal client for the dedicated DSI Vision endpoints."""
from __future__ import annotations

import os
from urllib.parse import urlsplit

import httpx

from .errors import DSICaptureRejected, DSIProviderUnavailable


def _config() -> tuple[str, str]:
    base = os.getenv("DSI_VISION_API_URL", "").strip().rstrip("/")
    token = os.getenv("DSI_VISION_API_TOKEN", "").strip()
    if not base or len(token.encode("utf-8")) < 32:
        raise DSIProviderUnavailable("dsi_vision_provider_not_configured")
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
        raise DSIProviderUnavailable("dsi_vision_provider_url_invalid")
    return base, token


async def _post_image(
    path: str,
    *,
    content: bytes,
    content_type: str,
    filename: str,
    form_data: dict[str, str] | None = None,
) -> dict:
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
                data=form_data,
            )
    except httpx.TimeoutException as exc:
        raise DSIProviderUnavailable("dsi_vision_timeout") from exc
    except httpx.HTTPError as exc:
        raise DSIProviderUnavailable("dsi_vision_unavailable") from exc
    if response.status_code != 200:
        raise DSIProviderUnavailable("dsi_vision_inference_unavailable")
    if "no-store" not in response.headers.get("cache-control", "").casefold():
        raise DSIProviderUnavailable("dsi_vision_cache_policy_invalid")
    try:
        payload = response.json()
    except ValueError as exc:
        raise DSIProviderUnavailable("dsi_vision_invalid_response") from exc
    if not isinstance(payload, dict):
        raise DSIProviderUnavailable("dsi_vision_invalid_response")
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
        raise DSIProviderUnavailable("dsi_vision_face_contract_invalid")
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
        raise DSIProviderUnavailable("dsi_vision_segmentation_contract_invalid")
    return payload



async def fetch_colorchecker_tone_preview(
    *,
    content: bytes,
    content_type: str,
    filename: str,
    profile_id: str,
    patch_grid_corners: str,
    chart_edition_confirmed_after_2014: bool,
    chart_age_months: int | None,
    chart_condition: str,
    requested_region: str,
) -> dict:
    if requested_region not in {"face_skin", "body_skin"}:
        raise DSIProviderUnavailable("dsi_vision_color_region_invalid")
    if chart_edition_confirmed_after_2014 is not True:
        raise DSIProviderUnavailable("dsi_vision_color_chart_edition_not_confirmed")
    fields = {
        "profile_id": profile_id,
        "patch_grid_corners": patch_grid_corners,
        "chart_edition_confirmed_after_2014": "true",
        "chart_condition": chart_condition,
        "requested_region": requested_region,
    }
    if chart_age_months is not None:
        fields["chart_age_months"] = str(chart_age_months)
    payload = await _post_image(
        "/v1/dsi/colorchecker-tone-preview",
        content=content,
        content_type=content_type,
        filename=filename,
        form_data=fields,
    )
    model = payload.get("skin_segmentation_model")
    profile = payload.get("profile")
    stats = payload.get("chart_fit_leave_one_out_delta_e_2000")
    regions = payload.get("skin_regions")
    expected_region = regions.get(requested_region) if isinstance(regions, dict) else None
    if not (
        payload.get("status") == "colorchecker_fit_candidate_unvalidated"
        and payload.get("calibration_state") == "experimental_unvalidated"
        and payload.get("requested_region") == requested_region
        and isinstance(profile, dict)
        and profile.get("profile_id") == profile_id
        and isinstance(profile.get("profile_sha256"), str)
        and len(profile["profile_sha256"]) == 64
        and isinstance(stats, dict)
        and all(key in stats for key in ("mean", "median", "p95", "maximum"))
        and isinstance(payload.get("chart_patch_count_used"), int)
        and 18 <= payload["chart_patch_count_used"] <= 24
        and isinstance(payload.get("neutral_patches_used"), int)
        and payload["neutral_patches_used"] >= 4
        and isinstance(payload.get("patches_excluded_from_fit"), list)
        and isinstance(payload.get("patch_leave_one_out_delta_e_2000"), list)
        and len(payload["patch_leave_one_out_delta_e_2000"]) == payload["chart_patch_count_used"]
        and isinstance(expected_region, dict)
        and isinstance(model, dict)
        and isinstance(model.get("version"), str)
        and isinstance(model.get("sha256"), str)
        and len(model["sha256"]) == 64
        and payload.get("absolute_colour_measurement_approved") is False
        and payload.get("independent_model_validation_passed") is False
        and payload.get("image_persisted") is False
        and payload.get("profile_persisted") is False
        and payload.get("global_training_performed") is False
        and payload.get("discovery_restricted") is False
    ):
        raise DSIProviderUnavailable("dsi_vision_color_calibration_contract_invalid")
    return payload



async def issue_dsi_capture_challenge(*, payload: dict[str, str]) -> dict:
    """Request a one-time challenge from Vision; Identity remains the consent authority."""
    base, token = _config()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=2.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(
                base + "/v1/dsi/capture-challenges",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise DSIProviderUnavailable("dsi_capture_challenge_timeout") from exc
    except httpx.HTTPError as exc:
        raise DSIProviderUnavailable("dsi_capture_challenge_unavailable") from exc
    if response.status_code in {401, 403, 404, 409, 422}:
        raise DSICaptureRejected("dsi_capture_challenge_rejected")
    if response.status_code != 200:
        raise DSIProviderUnavailable("dsi_capture_challenge_unavailable")
    if "no-store" not in response.headers.get("cache-control", "").casefold():
        raise DSIProviderUnavailable("dsi_capture_challenge_cache_policy_invalid")
    try:
        result = response.json()
    except ValueError as exc:
        raise DSIProviderUnavailable("dsi_capture_challenge_invalid_response") from exc
    challenge = result.get("challenge") if isinstance(result, dict) else None
    if (
        not isinstance(result, dict)
        or result.get("status") != "issued"
        or not isinstance(challenge, dict)
        or not isinstance(challenge.get("challengeId"), str)
        or not isinstance(challenge.get("nonceBase64Url"), str)
        or len(challenge["nonceBase64Url"]) != 43
        or not isinstance(challenge.get("expiresAtEpochMs"), int)
        or challenge["expiresAtEpochMs"] <= 0
    ):
        raise DSIProviderUnavailable("dsi_capture_challenge_contract_invalid")
    return challenge


async def verify_dsi_native_capture(
    *,
    envelope_json: str,
    challenge_nonce_base64url: str,
    content: bytes,
    content_type: str,
    filename: str,
) -> dict:
    """Forward exact multipart bytes to Vision and validate the server-created receipt."""
    base, token = _config()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(40.0, connect=2.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(
                base + "/v1/dsi/capture-verifications",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                data={
                    "envelope_json": envelope_json,
                    "challenge_nonce_base64url": challenge_nonce_base64url,
                },
                files={"image": (filename, content, content_type)},
            )
    except httpx.TimeoutException as exc:
        raise DSIProviderUnavailable("dsi_capture_verification_timeout") from exc
    except httpx.HTTPError as exc:
        raise DSIProviderUnavailable("dsi_capture_verification_unavailable") from exc
    if response.status_code in {401, 403, 404, 409, 410, 422}:
        raise DSICaptureRejected("dsi_capture_proof_rejected")
    if response.status_code != 200:
        raise DSIProviderUnavailable("dsi_capture_verification_unavailable")
    if "no-store" not in response.headers.get("cache-control", "").casefold():
        raise DSIProviderUnavailable("dsi_capture_verification_cache_policy_invalid")
    try:
        result = response.json()
    except ValueError as exc:
        raise DSIProviderUnavailable("dsi_capture_verification_invalid_response") from exc
    receipt = result.get("receipt") if isinstance(result, dict) else None
    if (
        not isinstance(result, dict)
        or result.get("status") != "verified"
        or not isinstance(receipt, dict)
        or not isinstance(receipt.get("receipt_id"), str)
        or result.get("absolute_colour_measurement_approved") is not False
        or result.get("profile_persistence_authorized") is not False
    ):
        raise DSIProviderUnavailable("dsi_capture_verification_contract_invalid")
    return result
