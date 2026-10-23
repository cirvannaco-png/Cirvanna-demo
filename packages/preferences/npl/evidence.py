"""Canonical signed evidence envelope for negative-preference policy.

The payload binds NPL preferences to the evaluated request, user, candidate,
and candidate attributes. Signing keys belong only to trusted service secrets.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

EVIDENCE_CONTRACT_VERSION = "1.0.0"

def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)

def preference_payload(value: Any) -> dict[str, Any]:
    """Render either a domain object or validated input model as a canonical map."""
    def enum_text(item: Any) -> Any:
        return item.value if hasattr(item, "value") else item
    event_ids = _get(value, "rejection_event_ids", ())
    return {
        "preference_id": str(_get(value, "preference_id", "")).strip(),
        "user_id": str(_get(value, "user_id", "")).strip(),
        "target_type": enum_text(_get(value, "target_type", "")),
        "target_value": str(_get(value, "target_value", "")).strip(),
        "source": enum_text(_get(value, "source", "")),
        "rejection_event_ids": sorted(str(event).strip() for event in event_ids),
        "rejection_threshold": int(_get(value, "rejection_threshold", 3)),
        "active": bool(_get(value, "active", True)),
        "correction_event_id": _get(value, "correction_event_id"),
    }

def canonical_npl_evidence_payload(
    request_id: str,
    user_id: str,
    candidate_id: str,
    candidate_attributes: tuple[str, ...] | list[str],
    preferences: tuple[Any, ...] | list[Any],
) -> bytes:
    """Stable JSON serialization for provider HMAC and independent verification."""
    for label, value in (("request_id", request_id), ("user_id", user_id), ("candidate_id", candidate_id)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must not be empty")
    if not isinstance(candidate_attributes, (tuple, list)):
        raise ValueError("candidate_attributes must be a tuple or list")
    if any(not isinstance(value, str) or not value.strip() for value in candidate_attributes):
        raise ValueError("candidate_attributes must contain non-empty strings")
    if not isinstance(preferences, (tuple, list)):
        raise ValueError("preferences must be a tuple or list")
    normalized_preferences = [preference_payload(item) for item in preferences]
    if any(not item["preference_id"] or not item["user_id"] or not item["target_value"] for item in normalized_preferences):
        raise ValueError("preferences must contain required identifiers and target values")
    if any(item["user_id"] != user_id.strip() for item in normalized_preferences):
        raise ValueError("all signed preferences must belong to the evaluated user")
    normalized_preferences.sort(key=lambda item: (item["user_id"], item["preference_id"]))
    document = {
        "contract_version": EVIDENCE_CONTRACT_VERSION,
        "request_id": request_id.strip(),
        "user_id": user_id.strip(),
        "candidate_id": candidate_id.strip(),
        "candidate_attributes": sorted({item.strip().casefold() for item in candidate_attributes}),
        "negative_preferences": normalized_preferences,
    }
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
