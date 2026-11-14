"""Purpose-bound consent checks for DSI internal use cases.

The privacy service must verify receipt authenticity and subject binding before
a trusted internal caller constructs this contract. This module is not a token verifier.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .contracts import ConsentPurpose, PurposeConsent


class ConsentNotAuthorized(ValueError):
    """Raised when a DSI action lacks valid, current, purpose-bound consent."""


def require_purpose_consent(
    receipt: PurposeConsent,
    purpose: ConsentPurpose,
    *,
    now: datetime | None = None,
) -> None:
    """Fail closed unless trusted, active consent grants the exact requested purpose."""
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not receipt.verified_by_privacy_service:
        raise ConsentNotAuthorized("consent receipt has not been verified by the privacy service")
    if not receipt.active or receipt.revoked:
        raise ConsentNotAuthorized("consent is inactive or revoked")
    if receipt.purpose != purpose:
        raise ConsentNotAuthorized("consent does not grant the requested purpose")
    if current_time < receipt.issued_at or current_time >= receipt.expires_at:
        raise ConsentNotAuthorized("consent is not currently valid")
