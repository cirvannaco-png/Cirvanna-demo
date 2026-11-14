"""Purpose-specific, resource-bound consent verification for DSI.

The caller must be an authenticated internal service. This module delegates
receipt validation to the canonical Identity Learning service; it does not
create, extend, infer, or persist consent.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from .contracts import ConsentPurpose
from .errors import ConsentNotAuthorized, DSIProviderUnavailable


PURPOSE_SCOPES: dict[ConsentPurpose, tuple[str, ...]] = {
    ConsentPurpose.COSMETIC_SKIN_ANALYSIS: ("image_processing", "skin_analysis"),
    ConsentPurpose.FACIAL_GEOMETRY_ANALYSIS: ("image_processing", "facial_geometry_analysis"),
    ConsentPurpose.BODY_TONE_ANALYSIS: ("image_processing", "body_tone_analysis", "body_measurements"),
    ConsentPurpose.APPEARANCE_CORRECTION: ("image_processing", "appearance_correction"),
    ConsentPurpose.GLOBAL_MODEL_TRAINING: ("global_model_training",),
}


def _provider_config() -> tuple[str, str]:
    import os

    raw = os.getenv("IDENTITY_LEARNING_API_URL", "").strip().rstrip("/")
    token = os.getenv("IDENTITY_LEARNING_API_TOKEN", "").strip()
    if not raw or len(token.encode("utf-8")) < 32:
        raise DSIProviderUnavailable("identity_learning_provider_not_configured")
    parsed = urlsplit(raw)
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
        raise DSIProviderUnavailable("identity_learning_provider_url_invalid")
    return raw, token


def _aware_expiry(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ConsentNotAuthorized("consent_expiry_missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConsentNotAuthorized("consent_expiry_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConsentNotAuthorized("consent_expiry_not_timezone_aware")
    return parsed.astimezone(timezone.utc)


async def verify_dsi_consent(
    *,
    subject_id: str,
    consent_id: str,
    consent_version: str,
    resource_id: str,
    purpose: ConsentPurpose,
    now: datetime | None = None,
) -> dict[str, object]:
    """Verify exact subject, purpose scopes, version, resource, revocation and expiry."""
    for name, value in (
        ("subject_id", subject_id),
        ("consent_id", consent_id),
        ("consent_version", consent_version),
        ("resource_id", resource_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ConsentNotAuthorized(f"{name}_required")
    if purpose not in PURPOSE_SCOPES:
        raise ConsentNotAuthorized("unsupported_dsi_consent_purpose")

    base, token = _provider_config()
    payload = {
        "subject_id": subject_id,
        "consent_id": consent_id,
        "consent_version": consent_version,
        "resource_id": resource_id,
        "required_scopes": list(PURPOSE_SCOPES[purpose]),
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(4.0, connect=1.5),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(
                base + "/internal/v1/consents/verify",
                headers={
                    "Authorization": "Bearer " + token,
                    "Accept": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise DSIProviderUnavailable("identity_learning_verification_timeout") from exc
    except httpx.HTTPError as exc:
        raise DSIProviderUnavailable("identity_learning_verifier_unavailable") from exc

    if response.status_code in {401, 403, 404}:
        raise ConsentNotAuthorized("dsi_purpose_consent_not_verified")
    if response.status_code != 200:
        raise DSIProviderUnavailable("identity_learning_verifier_unavailable")
    try:
        receipt = response.json()
    except ValueError as exc:
        raise DSIProviderUnavailable("identity_learning_verifier_invalid_response") from exc

    required = set(PURPOSE_SCOPES[purpose])
    granted = receipt.get("granted_scopes") if isinstance(receipt, dict) else None
    receipt_ids = receipt.get("receipt_ids") if isinstance(receipt, dict) else None
    if not (
        isinstance(receipt, dict)
        and receipt.get("verified") is True
        and receipt.get("active") is True
        and receipt.get("subject_id") == subject_id
        and receipt.get("consent_id") == consent_id
        and receipt.get("resource_id") == resource_id
        and receipt.get("consent_version") == consent_version
        and isinstance(granted, list)
        and required.issubset(set(granted))
        and isinstance(receipt_ids, list)
        and len(receipt_ids) >= len(required)
        and all(isinstance(item, str) and item.strip() for item in receipt_ids)
    ):
        raise ConsentNotAuthorized("dsi_purpose_consent_not_verified")

    expiry = _aware_expiry(receipt.get("expires_at"))
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if expiry <= current.astimezone(timezone.utc):
        raise ConsentNotAuthorized("dsi_purpose_consent_expired")

    return {
        "subject_id": subject_id,
        "consent_id": consent_id,
        "resource_id": resource_id,
        "consent_version": consent_version,
        "purpose": purpose.value,
        "required_scopes": list(PURPOSE_SCOPES[purpose]),
        "receipt_ids": receipt_ids,
        "expires_at": expiry.isoformat(),
        "verified": True,
    }
