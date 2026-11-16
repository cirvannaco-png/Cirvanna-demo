"""Trusted internal client for the dedicated DSI Vision endpoints."""
from __future__ import annotations

import os
from urllib.parse import urlsplit

import httpx

from .errors import DSIProviderUnavailable


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


async def _post_json(path: str, payload: dict) -> dict:
    base, token = _config()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=2.0),
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
    except httpx.TimeoutException as exc:
        raise DSIProviderUnavailable("dsi_vision_timeout") from exc
    except httpx.HTTPError as exc:
        raise DSIProviderUnavailable("dsi_vision_unavailable") from exc
    if response.status_code != 200:
        raise DSIProviderUnavailable("dsi_vision_capture_verification_unavailable")
    if "no-store" not in response.headers.get("cache-control", "").casefold():
        raise DSIProviderUnavailable("dsi_vision_cache_policy_invalid")
    try:
        result = response.json()
    except ValueError as exc:
        raise DSIProviderUnavailable("dsi_vision_invalid_response") from exc
    if not isinstance(result, dict):
        raise DSIProviderUnavailable("dsi_vision_invalid_response")
    return result


async def create_dsi_capture_challenge(
    *,
    subject_id: str,
    consent_id: str,
    consent_version: str,
    resource_id: str,
    purpose: str,
) -> dict:
    if purpose not in {
        "cosmetic_skin_analysis",
        "facial_geometry_analysis",
        "body_tone_analysis",
        "appearance_correction",
    }:
        raise DSIProviderUnavailable("dsi_capture_purpose_invalid")
    payload = await _post_json(
        "/v1/dsi/capture-challenges",
        {
            "subject_id": subject_id,
            "consent_id": consent_id,
            "consent_version": consent_version,
            "resource_id": resource_id,
            "purpose": purpose,
        },
    )
    if not (
        payload.get("status") == "challenge_issued"
        and isinstance(payload.get("challenge_id"), str)
        and isinstance(payload.get("nonce_b64url"), str)
        and payload.get("nonce_bytes") == 32
        and payload.get("subject_id") == subject_id
        and payload.get("resource_id") == resource_id
        and payload.get("purpose") == purpose
        and payload.get("verification_state") == "pending_server_verification"
    ):
        raise DSIProviderUnavailable("dsi_vision_capture_challenge_contract_invalid")
    return payload


async def verify_dsi_capture_envelope(
    *,
    subject_id: str,
    consent_id: str,
    consent_version: str,
    resource_id: str,
    purpose: str,
    challenge_id: str,
    nonce_b64url: str,
    manifest_canonical_json: str,
    manifest_signature_base64url: str,
    attestation_certificate_chain: list[str],
    play_integrity_token: str,
    content: bytes,
    content_type: str,
    filename: str,
) -> dict:
    import json

    if purpose not in {
        "cosmetic_skin_analysis",
        "facial_geometry_analysis",
        "body_tone_analysis",
        "appearance_correction",
    }:
        raise DSIProviderUnavailable("dsi_capture_purpose_invalid")
    if not isinstance(attestation_certificate_chain, list) or not (
        2 <= len(attestation_certificate_chain) <= 8
    ):
        raise DSIProviderUnavailable("dsi_vision_attestation_chain_invalid")

    payload = await _post_image(
        "/v1/dsi/capture-verifications",
        content=content,
        content_type=content_type,
        filename=filename,
        form_data={
            "subject_id": subject_id,
            "consent_id": consent_id,
            "consent_version": consent_version,
            "resource_id": resource_id,
            "purpose": purpose,
            "challenge_id": challenge_id,
            "nonce_b64url": nonce_b64url,
            "manifest_canonical_json": manifest_canonical_json,
            "manifest_signature_base64url": manifest_signature_base64url,
            "attestation_certificate_chain_base64url": json.dumps(
                attestation_certificate_chain,
                separators=(",", ":"),
            ),
            "play_integrity_token": play_integrity_token,
        },
    )
    receipt = payload.get("receipt")
    verification = payload.get("verification")
    if not (
        payload.get("status") == "capture_verified"
        and isinstance(receipt, dict)
        and isinstance(receipt.get("receipt_id"), str)
        and receipt.get("verification_status") == "verified_by_trusted_vision_service"
        and receipt.get("subject_id") == subject_id
        and receipt.get("resource_id") == resource_id
        and receipt.get("purpose") == purpose
        and isinstance(receipt.get("manifest_sha256"), str)
        and isinstance(receipt.get("image_sha256"), str)
        and isinstance(receipt.get("device_pipeline_fingerprint_sha256"), str)
        and isinstance(verification, dict)
        and verification.get("android_key_attestation") == "verified"
        and verification.get("play_integrity") == "verified"
        and payload.get("absolute_colour_measurement_approved") is False
    ):
        raise DSIProviderUnavailable("dsi_vision_capture_receipt_contract_invalid")
    return payload


async def verify_dsi_capture_receipt(
    *,
    receipt_id: str,
    subject_id: str,
    resource_id: str,
    purpose: str,
    manifest_sha256: str,
    image_sha256: str,
    device_pipeline_fingerprint_sha256: str,
) -> dict:
    payload = await _post_json(
        "/v1/dsi/capture-receipts/verify",
        {
            "receipt_id": receipt_id,
            "subject_id": subject_id,
            "resource_id": resource_id,
            "purpose": purpose,
            "manifest_sha256": manifest_sha256,
            "image_sha256": image_sha256,
            "device_pipeline_fingerprint_sha256": device_pipeline_fingerprint_sha256,
        },
    )
    receipt = payload.get("receipt")
    if not (
        payload.get("verified") is True
        and isinstance(receipt, dict)
        and receipt.get("receipt_id") == receipt_id
        and receipt.get("subject_id") == subject_id
        and receipt.get("resource_id") == resource_id
        and receipt.get("purpose") == purpose
        and receipt.get("manifest_sha256") == manifest_sha256
        and receipt.get("image_sha256") == image_sha256
        and receipt.get("device_pipeline_fingerprint_sha256") == device_pipeline_fingerprint_sha256
        and receipt.get("verification_status") == "verified_by_trusted_vision_service"
    ):
        raise DSIProviderUnavailable("dsi_vision_capture_receipt_contract_invalid")
    return receipt
