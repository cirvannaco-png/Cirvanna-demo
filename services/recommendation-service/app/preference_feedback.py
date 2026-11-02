"""Explicit feedback routing contract for USI/TAL and NPL.

The module creates auditable event proposals only. Durable, idempotent persistence
must be supplied by the canonical preference/TAL service before the UI claims
that a preference has been remembered.
"""
from __future__ import annotations

from typing import Any

ALLOWED_DIMENSIONS = {
    "clothing_colour",
    "makeup_colour",
    "fragrance_family",
    "fragrance_note",
    "earrings",
    "necklace",
    "glasses",
    "accessory",
    "aesthetic",
}


def build_preference_feedback_event(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("learning_consent") is not True:
        raise ValueError("explicit preference-learning consent is required")

    action = payload.get("action")
    dimension = payload.get("dimension")
    if dimension not in ALLOWED_DIMENSIONS:
        raise ValueError("unsupported feedback dimension")

    base = {
        "event_id": payload["event_id"],
        "request_id": payload["request_id"],
        "user_id": payload["user_id"],
        "recommendation_id": payload["recommendation_id"],
        "dimension": dimension,
    }

    if action == "approved":
        events = [{
            **base,
            "event_kind": "positive_preference_evidence",
            "target_value": payload["value"],
            "owner": "USI/TAL",
        }]
        explanation = (
            "The user explicitly approved this suggestion. It may be proposed as positive "
            "preference evidence for the canonical USI/TAL workflow."
        )
    elif action == "rejected":
        events = [{
            **base,
            "event_kind": "negative_recommendation_evidence",
            "target_value": payload["value"],
            "owner": "NPL",
        }]
        explanation = (
            "The user explicitly rejected this suggestion. Route the event to NPL as negative "
            "evidence; this event alone does not create a permanent hard exclusion."
        )
    elif action == "modified":
        modified_value = payload.get("modified_value")
        if not isinstance(modified_value, str) or not modified_value.strip():
            raise ValueError("modified_value is required when action is modified")
        events = [
            {
                **base,
                "event_kind": "negative_recommendation_evidence",
                "target_value": payload["value"],
                "owner": "NPL",
            },
            {
                **base,
                "event_id": f"{payload['event_id']}:modified",
                "event_kind": "positive_preference_evidence",
                "target_value": modified_value.strip(),
                "owner": "USI/TAL",
            },
        ]
        explanation = (
            "The original suggestion is rejected and the user's edited alternative is positive "
            "preference evidence. Both events retain a common source event for audit."
        )
    elif action == "not_relevant":
        events = []
        explanation = "The user marked the suggestion not relevant; no preference signal is proposed."
    else:
        raise ValueError("action must be approved, rejected, modified or not_relevant")

    return {
        "schema_version": "1.0",
        "contract_version": "1.0.0",
        "status": "event_proposal_only",
        "events": events,
        "idempotency_key": payload["event_id"],
        "persistence": "not_connected",
        "explanation": explanation,
        "required_next_step": (
            "Persist idempotently through the trusted USI/TAL/NPL adapter, then expose the updated "
            "preference version to the authenticated profile owner."
        ),
        "guardrails": [
            "Events are scoped to the supplied user and must be identity-bound by trusted ingress.",
            "User approval or rejection is not stored by this API.",
            "A rejection is evidence, not an automatic user-declared hard veto.",
            "Explicit user constraints must never be silently weakened by learned feedback.",
            "The user must be able to inspect, correct and delete learned preference state.",
        ],
    }
