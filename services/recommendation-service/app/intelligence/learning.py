"""Consent-aware feedback event contract for the canonical TAL learning workflow."""
from __future__ import annotations

from typing import Any


def build_learning_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a versioned observation; persistence belongs to the TAL/profile owner."""
    if not payload.get("consent_to_personalization"):
        raise ValueError("explicit personalization consent is required")
    action = payload.get("preference_action", "observe_only")
    outcome = payload["outcome"]
    if action == "save_preference" and not payload.get("preference_value"):
        raise ValueError("preference_value is required when saving a preference")
    if action not in {"observe_only", "save_preference"}:
        raise ValueError("unsupported preference_action")
    return {
        "schema_version": "1.0",
        "event_id": payload["feedback_id"],
        "subject_id": payload["user_id"],
        "recommendation_id": payload["recommendation_id"],
        "category": payload["category"],
        "outcome": outcome,
        "preference_action": action,
        "preference_value": payload.get("preference_value") if action == "save_preference" else None,
        "signal_semantics": "soft_preference_observation",
        "may_create_hard_npl_veto": False,
        "reason_code": payload.get("reason_code"),
        "consent": {"purpose": "personalization", "explicit": True},
        "owner": "CaTaCaCi/TAL",
        "persistence": "handoff_required",
        "explanation": (
            "Approval is a positive preference observation; rejection is a negative soft signal. "
            "Neither silently rewrites identity or creates a permanent exclusion."
        ),
    }
