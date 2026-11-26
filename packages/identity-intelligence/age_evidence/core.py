"""Purpose-bound, threshold-only age evidence contracts.

This package never stores DOB, document images, selfies, face templates or raw
age values. A trusted adapter must establish provider provenance before signing.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any

CONTRACT_VERSION = "age-threshold-attestation-v1"
MAX_ATTESTATION_TTL_SECONDS = 900


class AgeEvidenceError(ValueError):
    pass


def canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def sign_threshold_attestation(payload: dict[str, Any], secret: str) -> str:
    if len(secret.encode("utf-8")) < 32:
        raise AgeEvidenceError("age evidence signing key must contain at least 32 bytes")
    validate_threshold_attestation(payload)
    return hmac.new(secret.encode("utf-8"), canonical_payload(payload), hashlib.sha256).hexdigest()


def verify_threshold_attestation(
    payload: dict[str, Any],
    signature: str,
    secret: str,
    *,
    subject_id: str,
    request_id: str,
    purpose: str,
    policy_id: str,
    policy_version: str,
    threshold: int,
    now: datetime | None = None,
) -> bool:
    if len(secret.encode("utf-8")) < 32:
        raise AgeEvidenceError("age evidence signing key must contain at least 32 bytes")
    validate_threshold_attestation(payload)
    expected = hmac.new(secret.encode("utf-8"), canonical_payload(payload), hashlib.sha256).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(expected, signature):
        return False
    for name, value in {
        "subject_id": subject_id,
        "request_id": request_id,
        "purpose": purpose,
        "policy_id": policy_id,
        "policy_version": policy_version,
    }.items():
        if not isinstance(value, str) or not value.strip():
            raise AgeEvidenceError(f"expected {name} binding must be a non-empty string")
    if not isinstance(threshold, int) or isinstance(threshold, bool) or not 0 <= threshold <= 125:
        raise AgeEvidenceError("expected threshold binding must be an integer from 0 to 125")
    expected_bindings = {
        "subject_id": subject_id,
        "request_id": request_id,
        "purpose": purpose,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "threshold": threshold,
    }
    if any(payload.get(key) != value for key, value in expected_bindings.items()):
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise AgeEvidenceError("verification clock must be timezone-aware")
    issued = _timestamp(payload["issued_at"])
    expires = _timestamp(payload["expires_at"])
    if issued > current or expires <= current or expires <= issued:
        return False
    if (expires - issued).total_seconds() > MAX_ATTESTATION_TTL_SECONDS:
        return False
    return True



def build_threshold_attestation(
    *,
    subject_id: str,
    request_id: str,
    purpose: str,
    policy_id: str,
    policy_version: str,
    threshold: int,
    threshold_met: bool,
    provider_session_id: str,
    provider_evidence_id: str,
    issued_at: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    """Build the minimized attestation only after an authenticated provider result."""
    if not isinstance(threshold_met, bool):
        raise AgeEvidenceError("a pending or unknown provider result cannot create an attestation")
    if issued_at.tzinfo is None or expires_at.tzinfo is None:
        raise AgeEvidenceError("attestation timestamps must be timezone-aware")
    payload = {
        "contract_version": CONTRACT_VERSION,
        "jti": str(uuid.uuid4()),
        "issuer": "cirvanna-age-evidence-service",
        "provider": "yoti",
        "subject_id": subject_id,
        "request_id": request_id,
        "purpose": purpose,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "threshold": threshold,
        "threshold_met": threshold_met,
        "provider_session_id": provider_session_id,
        "provider_evidence_id": provider_evidence_id,
        "issued_at": issued_at.astimezone(timezone.utc).isoformat(),
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
    }
    validate_threshold_attestation(payload)
    if expires_at <= issued_at:
        raise AgeEvidenceError("attestation expiry must follow issuance")
    if (expires_at - issued_at).total_seconds() > MAX_ATTESTATION_TTL_SECONDS:
        raise AgeEvidenceError("attestation lifetime exceeds the 15-minute maximum")
    return payload


def validate_threshold_attestation(payload: dict[str, Any]) -> None:
    required = {
        "contract_version", "jti", "issuer", "provider", "subject_id", "request_id", "purpose",
        "policy_id", "policy_version", "threshold", "threshold_met",
        "provider_session_id", "provider_evidence_id", "issued_at", "expires_at",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise AgeEvidenceError("age attestation fields do not match the closed contract")
    try:
        uuid.UUID(payload["jti"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise AgeEvidenceError("jti must be a UUID") from exc
    if payload["contract_version"] != CONTRACT_VERSION:
        raise AgeEvidenceError("unsupported age attestation contract version")
    for key in (
        "issuer", "subject_id", "request_id", "purpose", "policy_id",
        "policy_version", "provider_session_id", "provider_evidence_id",
    ):
        if not isinstance(payload[key], str) or not payload[key].strip():
            raise AgeEvidenceError(f"{key} must be a non-empty string")
    if payload["issuer"] != "cirvanna-age-evidence-service" or payload["provider"] != "yoti":
        raise AgeEvidenceError("unapproved age evidence issuer or provider")
    if not isinstance(payload["threshold"], int) or isinstance(payload["threshold"], bool):
        raise AgeEvidenceError("threshold must be an integer")
    if payload["threshold"] < 0 or payload["threshold"] > 125:
        raise AgeEvidenceError("threshold is outside supported bounds")
    if not isinstance(payload["threshold_met"], bool):
        raise AgeEvidenceError("threshold_met must be a boolean")
    # These exact fields intentionally exclude age, date of birth and biometric data.
    forbidden = {"age", "age_years", "date_of_birth", "dob", "selfie", "document", "face_embedding"}
    if forbidden.intersection(payload):
        raise AgeEvidenceError("raw identity or biometric data is forbidden in age attestations")


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise AgeEvidenceError("attestation timestamps must be ISO-8601 strings")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AgeEvidenceError("invalid attestation timestamp") from exc
    if parsed.tzinfo is None:
        raise AgeEvidenceError("attestation timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)
