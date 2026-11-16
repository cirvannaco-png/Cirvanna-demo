"""Purpose-authorized, stateless DSI preview endpoints."""
from __future__ import annotations

from typing import Annotated, Literal

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from .consent import verify_dsi_consent
from .errors import ConsentNotAuthorized, DSICaptureRejected, DSIProviderUnavailable
from .contracts import ConsentPurpose
from .features import summarize_face_geometry
from .media import read_and_decode_payload
from .security import require_dsi_api_token
from .vision_client import (
    fetch_colorchecker_tone_preview,
    fetch_face_landmarks,
    fetch_skin_segmentation,
    issue_dsi_capture_challenge,
    verify_dsi_native_capture,
)

router = APIRouter(prefix="/api/v1/dsi", tags=["dsi-analysis"])
MAX_DSI_IMAGE_BYTES = 5 * 1024 * 1024
MAX_DSI_IMAGE_PIXELS = 16_000_000
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MIME_TO_FORMAT = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


def _private_response(payload: dict, status_code: int = 200) -> JSONResponse:
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


async def _read_payload(image: UploadFile) -> tuple[bytes, np.ndarray]:
    return await read_and_decode_payload(
        image,
        max_bytes=MAX_DSI_IMAGE_BYTES,
        max_pixels=MAX_DSI_IMAGE_PIXELS,
        allowed_mime_types=ALLOWED_MIME_TYPES,
        mime_to_format=MIME_TO_FORMAT,
    )


async def _verify_purpose(
    *,
    subject_id: str,
    consent_id: str,
    consent_version: str,
    resource_id: str,
    purpose: ConsentPurpose,
    image: UploadFile | None = None,
) -> dict[str, object]:
    try:
        return await verify_dsi_consent(
            subject_id=subject_id,
            consent_id=consent_id,
            consent_version=consent_version,
            resource_id=resource_id,
            purpose=purpose,
        )
    except ConsentNotAuthorized as exc:
        if image is not None:
            await image.close()
        raise HTTPException(403, detail={"code": "DSI_PURPOSE_CONSENT_NOT_VERIFIED"}) from exc
    except DSIProviderUnavailable as exc:
        if image is not None:
            await image.close()
        raise HTTPException(503, detail={"code": "DSI_CONSENT_PROVIDER_UNAVAILABLE"}) from exc


@router.post("/face-geometry-preview", dependencies=[Depends(require_dsi_api_token)])
async def face_geometry_preview(
    subject_id: Annotated[str, Form(min_length=1, max_length=128)],
    consent_id: Annotated[str, Form(min_length=8, max_length=128)],
    consent_version: Annotated[str, Form(min_length=1, max_length=80)],
    resource_id: Annotated[str, Form(min_length=3, max_length=160)],
    image: Annotated[UploadFile, File()],
) -> JSONResponse:
    """Return optional geometric ratios only after exact facial-analysis consent."""
    await _verify_purpose(
        subject_id=subject_id,
        consent_id=consent_id,
        consent_version=consent_version,
        resource_id=resource_id,
        purpose=ConsentPurpose.FACIAL_GEOMETRY_ANALYSIS,
        image=image,
    )
    content_type = image.content_type or ""
    filename = image.filename or "dsi-capture"
    content, decoded = await _read_payload(image)
    try:
        payload = await fetch_face_landmarks(
            content=content,
            content_type=content_type,
            filename=filename,
        )
        geometry = summarize_face_geometry(payload)
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "DSI_GEOMETRY_CONTRACT_INVALID"}) from exc
    except DSIProviderUnavailable as exc:
        raise HTTPException(503, detail={"code": "DSI_VISION_PROVIDER_UNAVAILABLE"}) from exc
    finally:
        del decoded
    return _private_response({
        "status": "completed",
        "purpose": ConsentPurpose.FACIAL_GEOMETRY_ANALYSIS.value,
        "geometry": geometry,
        "image_persisted": False,
        "profile_persisted": False,
        "discovery_restricted": False,
        "user_autonomy": "recommendations_are_optional_and_user_choices_remain_authoritative",
        "disclaimer": (
            "This optional preview does not identify the person, classify face shape, "
            "measure beauty, or determine what styles the user may explore."
        ),
    })


@router.post("/skin-region-preview", dependencies=[Depends(require_dsi_api_token)])
async def skin_region_preview(
    subject_id: Annotated[str, Form(min_length=1, max_length=128)],
    consent_id: Annotated[str, Form(min_length=8, max_length=128)],
    consent_version: Annotated[str, Form(min_length=1, max_length=80)],
    resource_id: Annotated[str, Form(min_length=3, max_length=160)],
    purpose: Annotated[Literal["cosmetic_skin_analysis", "body_tone_analysis"], Form()],
    image: Annotated[UploadFile, File()],
) -> JSONResponse:
    """Return visible region masks/coverage; never label segmentation as skin tone."""
    purpose_enum = (
        ConsentPurpose.COSMETIC_SKIN_ANALYSIS
        if purpose == ConsentPurpose.COSMETIC_SKIN_ANALYSIS.value
        else ConsentPurpose.BODY_TONE_ANALYSIS
    )
    await _verify_purpose(
        subject_id=subject_id,
        consent_id=consent_id,
        consent_version=consent_version,
        resource_id=resource_id,
        purpose=purpose_enum,
        image=image,
    )
    content_type = image.content_type or ""
    filename = image.filename or "dsi-capture"
    content, _decoded = await _read_payload(image)
    try:
        payload = await fetch_skin_segmentation(
            content=content,
            content_type=content_type,
            filename=filename,
        )
    except DSIProviderUnavailable as exc:
        raise HTTPException(503, detail={"code": "DSI_VISION_PROVIDER_UNAVAILABLE"}) from exc
    return _private_response({
        "status": "completed",
        "purpose": purpose_enum.value,
        "segmentation_status": payload["status"],
        "input_quality": payload.get("input_quality"),
        "region_coverage": payload["region_coverage"],
        "model": payload["model"],
        "skin_tone_value_computed": False,
        "absolute_color_calibration_performed": False,
        "image_persisted": False,
        "profile_persisted": False,
        "discovery_restricted": False,
        "user_autonomy": "recommendations_are_optional_and_user_choices_remain_authoritative",
        "disclaimer": (
            "This preview estimates visible face/body skin regions only. It does not "
            "measure exact skin tone, compare all body regions, diagnose skin conditions, "
            "or limit the user's appearance choices."
        ),
    })



@router.post("/color-calibration-preview", dependencies=[Depends(require_dsi_api_token)])
async def color_calibration_preview(
    subject_id: Annotated[str, Form(min_length=1, max_length=128)],
    consent_id: Annotated[str, Form(min_length=8, max_length=128)],
    consent_version: Annotated[str, Form(min_length=1, max_length=80)],
    resource_id: Annotated[str, Form(min_length=3, max_length=160)],
    purpose: Annotated[Literal["cosmetic_skin_analysis", "body_tone_analysis"], Form()],
    profile_id: Annotated[str, Form(min_length=1, max_length=128)],
    patch_grid_corners: Annotated[str, Form(min_length=20, max_length=1000)],
    chart_edition_confirmed_after_2014: Annotated[bool, Form()],
    chart_age_months: Annotated[int | None, Form(ge=0)] = None,
    chart_condition: Annotated[Literal["good", "worn", "unknown"], Form()] = "unknown",
    image: Annotated[UploadFile, File()] = ...,
) -> JSONResponse:
    """Return an experimental chart-calibrated preview after exact regional consent."""
    purpose_enum = (
        ConsentPurpose.COSMETIC_SKIN_ANALYSIS
        if purpose == ConsentPurpose.COSMETIC_SKIN_ANALYSIS.value
        else ConsentPurpose.BODY_TONE_ANALYSIS
    )
    if chart_edition_confirmed_after_2014 is not True:
        await image.close()
        raise HTTPException(
            422,
            detail={"code": "DSI_COLOR_REFERENCE_EDITION_NOT_CONFIRMED"},
        )
    await _verify_purpose(
        subject_id=subject_id,
        consent_id=consent_id,
        consent_version=consent_version,
        resource_id=resource_id,
        purpose=purpose_enum,
        image=image,
    )
    content_type = image.content_type or ""
    filename = image.filename or "dsi-color-capture"
    content, decoded = await _read_payload(image)
    requested_region = (
        "face_skin"
        if purpose_enum == ConsentPurpose.COSMETIC_SKIN_ANALYSIS
        else "body_skin"
    )
    try:
        preview = await fetch_colorchecker_tone_preview(
            content=content,
            content_type=content_type,
            filename=filename,
            profile_id=profile_id,
            patch_grid_corners=patch_grid_corners,
            chart_edition_confirmed_after_2014=chart_edition_confirmed_after_2014,
            chart_age_months=chart_age_months,
            chart_condition=chart_condition,
            requested_region=requested_region,
        )
    except DSIProviderUnavailable as exc:
        raise HTTPException(
            503,
            detail={"code": "DSI_COLOR_CALIBRATION_UNAVAILABLE"},
        ) from exc
    finally:
        del decoded

    return _private_response({
        "status": "completed_experimental_preview",
        "purpose": purpose_enum.value,
        "requested_region": requested_region,
        "color_preview": preview,
        "absolute_color_measurement_approved": False,
        "independent_model_validation_passed": False,
        "image_persisted": False,
        "profile_persisted": False,
        "global_training_performed": False,
        "discovery_restricted": False,
        "user_autonomy": "recommendations_are_optional_and_user_choices_remain_authoritative",
        "disclaimer": (
            "This is an experimental ColorChecker-assisted colour preview, not an exact or "
            "validated skin-tone measurement. Do not use it for product shade decisions or "
            "persistent personalization until independent camera, lighting, chart and "
            "population validation is complete."
        ),
    })


_CAPTURE_PURPOSES = {
    "cosmetic_skin_analysis": ConsentPurpose.COSMETIC_SKIN_ANALYSIS,
    "facial_geometry_analysis": ConsentPurpose.FACIAL_GEOMETRY_ANALYSIS,
    "body_tone_analysis": ConsentPurpose.BODY_TONE_ANALYSIS,
    "appearance_correction": ConsentPurpose.APPEARANCE_CORRECTION,
}


@router.post("/capture-challenges", dependencies=[Depends(require_dsi_api_token)])
async def create_native_capture_challenge(
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
) -> JSONResponse:
    """Issue the one-time Android capture challenge after exact purpose consent."""
    purpose_enum = _CAPTURE_PURPOSES[purpose]
    await _verify_purpose(
        subject_id=subject_id,
        consent_id=consent_id,
        consent_version=consent_version,
        resource_id=resource_id,
        purpose=purpose_enum,
    )
    try:
        challenge = await issue_dsi_capture_challenge(
            payload={
                "subject_id": subject_id,
                "consent_id": consent_id,
                "consent_version": consent_version,
                "resource_id": resource_id,
                "purpose": purpose,
            }
        )
    except DSICaptureRejected as exc:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_CHALLENGE_REJECTED"}) from exc
    except DSIProviderUnavailable as exc:
        raise HTTPException(503, detail={"code": "DSI_CAPTURE_CHALLENGE_UNAVAILABLE"}) from exc
    return _private_response({
        "status": "issued",
        "challenge": challenge,
        "purpose": purpose,
        "subject_id": subject_id,
        "resource_id": resource_id,
        "absolute_colour_measurement_approved": False,
    })


@router.post("/capture-verifications", dependencies=[Depends(require_dsi_api_token)])
async def verify_native_capture(
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
    envelope_json: Annotated[str, Form(min_length=2, max_length=512 * 1024)],
    challenge_nonce_base64url: Annotated[str, Form(min_length=43, max_length=43)],
    image: Annotated[UploadFile, File()],
) -> JSONResponse:
    """Forward original image bytes and signed evidence to the private Vision verifier."""
    await _verify_purpose(
        subject_id=subject_id,
        consent_id=consent_id,
        consent_version=consent_version,
        resource_id=resource_id,
        purpose=_CAPTURE_PURPOSES[purpose],
        image=image,
    )
    content_type = image.content_type or ""
    filename = image.filename or "dsi-native-capture"
    content, decoded = await _read_payload(image)
    del decoded
    try:
        result = await verify_dsi_native_capture(
            envelope_json=envelope_json,
            challenge_nonce_base64url=challenge_nonce_base64url,
            content=content,
            content_type=content_type,
            filename=filename,
        )
    except DSICaptureRejected as exc:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_PROOF_REJECTED"}) from exc
    except DSIProviderUnavailable as exc:
        raise HTTPException(503, detail={"code": "DSI_CAPTURE_VERIFIER_UNAVAILABLE"}) from exc

    receipt = result["receipt"]
    return _private_response({
        "status": "verified",
        "receipt": receipt,
        "key_attestation": result.get("key_attestation"),
        "play_integrity": result.get("play_integrity"),
        "absolute_colour_measurement_approved": False,
        "measurement_uncertainty_validated": False,
        "profile_persistence_authorized": False,
        "note": (
            "Device provenance and app integrity were verified. This does not establish "
            "camera colour accuracy, genuine sensor pixels, calibrated measurements, or "
            "population-level model validity."
        ),
    })
