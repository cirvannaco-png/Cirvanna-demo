"""Versioned, jurisdiction-aware Click It policy gate.

The policy registry, not this service, determines applicable laws, age thresholds,
lawful bases, guardian-consent requirements, transfer rules and retention limits.
No country-specific legal thresholds are embedded here.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _policy_config() -> tuple[str, str] | None:
    raw = os.getenv("PRIVACY_POLICY_API_URL", "").strip().rstrip("/")
    token = os.getenv("PRIVACY_POLICY_API_TOKEN", "").strip()
    if not raw or len(token.encode("utf-8")) < 32:
        return None
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not host or parsed.username is not None or parsed.password is not None
        or parsed.query or parsed.fragment
        or (parsed.scheme != "https" and not (parsed.scheme == "http" and local))
    ):
        return None
    return raw, token


async def authorize_click_it_policy(subject_id: str, photographed_people_status: str) -> dict[str, object]:
    """Resolve all applicable jurisdictions and require an explicit current PASS receipt."""
    if photographed_people_status not in {"no_people", "adults_only", "contains_minor"}:
        raise HTTPException(403, detail={"code": "CHILD_SAFETY_STATUS_UNCONFIRMED"})
    config = _policy_config()
    if config is None:
        raise HTTPException(503, detail={"code": "PRIVACY_POLICY_REGISTRY_NOT_CONFIGURED"})
    base, token = config
    payload = {
        "subject_id": subject_id,
        "service": "cirvanna-click-it",
        "purpose": "visual_product_discovery",
        "photographed_people_status": photographed_people_status,
        "requested_retention_seconds": 0,
        "requested_public_display": False,
        "prohibited_processing": [
            "facial_recognition",
            "face_identity_analysis",
            "face_embeddings",
            "identity_matching",
            "sensitive_trait_inference",
            "child_behavioural_profiling",
            "child_facial_identity_analysis",
        ],
        "jurisdiction_resolution": {
            "resolve_from_trusted_subject_profile": True,
            "include_controller_and_processor_establishments": True,
            "include_capture_and_processing_context": True,
            "include_storage_and_transfer_destinations": True,
            "do_not_trust_client_country_claims": True,
        },
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, connect=1.5),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                base + "/internal/v1/privacy/click-it/evaluate",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "PRIVACY_POLICY_EVALUATION_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "PRIVACY_POLICY_REGISTRY_UNAVAILABLE"}) from exc
    if response.status_code in {401, 403, 404, 409, 422}:
        raise HTTPException(403, detail={"code": "PRIVACY_POLICY_BLOCKED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "PRIVACY_POLICY_REGISTRY_UNAVAILABLE"})
    try:
        receipt = response.json()
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "PRIVACY_POLICY_INVALID_RECEIPT"}) from exc
    jurisdictions = receipt.get("applicable_jurisdictions") if isinstance(receipt, dict) else None
    version = receipt.get("policy_version") if isinstance(receipt, dict) else None
    digest = receipt.get("policy_sha256") if isinstance(receipt, dict) else None
    safety_flags = (
        "facial_recognition_allowed",
        "face_identity_analysis_allowed",
        "child_facial_identity_analysis_allowed",
        "child_behavioural_profiling_allowed",
        "public_unmasked_face_exposure_allowed",
        "image_retention_allowed",
    )
    valid = (
        isinstance(receipt, dict)
        and receipt.get("decision") == "PASS"
        and receipt.get("current") is True
        and receipt.get("jurisdiction_resolution_complete") is True
        and receipt.get("policy_conflicts_resolved") is True
        and receipt.get("lawful_basis_authorized") is True
        and receipt.get("cross_border_transfers_authorized") is True
        and isinstance(version, str) and bool(version.strip())
        and isinstance(digest, str) and bool(_SHA256.fullmatch(digest))
        and isinstance(jurisdictions, list) and bool(jurisdictions)
        and all(isinstance(item, str) and item.strip() for item in jurisdictions)
        and all(receipt.get(flag) is False for flag in safety_flags)
        and isinstance(receipt.get("guardian_consent_required"), bool)
        and receipt.get("public_sharing_allowed") is False
    )
    if not valid:
        raise HTTPException(403, detail={"code": "PRIVACY_POLICY_BLOCKED"})
    return {
        "policy_version": version,
        "policy_sha256": digest,
        "applicable_jurisdictions": jurisdictions,
        "guardian_consent_required": receipt["guardian_consent_required"],
        "public_sharing_allowed": False,
    }
