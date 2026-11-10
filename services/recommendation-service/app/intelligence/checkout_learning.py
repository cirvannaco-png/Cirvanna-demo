"""Consent-gated checkout observations for TAL.

This module creates a minimal handoff contract only. It does not persist events,
change a user's explicit preferences, authorize CAL, or participate in payment.
"""
from __future__ import annotations

from typing import Any


_EVENT_FIELDS: dict[str, set[str]] = {
    "checkout.offer_selected": {"variant_id", "merchant_id", "currency", "unit_price_minor"},
    "checkout.fulfillment_selected": {"fulfillment_mode", "merchant_id"},
    "checkout.payment_method_selected": {"payment_method_family"},
    "checkout.item_removed": {"variant_id", "merchant_id", "explicit_reason"},
    "checkout.item_replaced": {"removed_variant_id", "selected_variant_id", "explicit_reason"},
    "commerce.order.paid": {"order_id", "currency", "total_minor", "ownership_authority"},
}
_ALLOWED_REMOVAL_REASONS = {"price", "delivery", "size", "style", "availability", "changed_mind", "other"}


def build_checkout_observation(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a consented, low-inference checkout event for TAL.

    The caller must supply a consent receipt already verified against the
    authenticated subject and the personalization purpose. Payment completion
    is accepted only from the trusted Commerce paid-order outbox contract.
    """
    if payload.get("consent_verified") is not True:
        raise ValueError("verified personalization consent is required")
    for field in ("consent_receipt_id", "event_id", "subject_id", "checkout_id", "event_type", "occurred_at"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise ValueError(f"{field} is required")

    event_type = payload["event_type"]
    if event_type not in _EVENT_FIELDS:
        raise ValueError("unsupported checkout observation event")
    if event_type == "commerce.order.paid" and payload.get("ownership_authority") != "verified_payment":
        raise ValueError("purchase observations require verified Commerce payment authority")

    allowed = _EVENT_FIELDS[event_type]
    details = {key: payload[key] for key in allowed if key in payload}
    required_by_event = {
        "checkout.offer_selected": {"variant_id", "merchant_id", "currency", "unit_price_minor"},
        "checkout.fulfillment_selected": {"fulfillment_mode"},
        "checkout.payment_method_selected": {"payment_method_family"},
        "checkout.item_removed": {"variant_id"},
        "checkout.item_replaced": {"removed_variant_id", "selected_variant_id"},
        "commerce.order.paid": {"order_id", "currency", "total_minor", "ownership_authority"},
    }
    if not required_by_event[event_type].issubset(details):
        raise ValueError("checkout observation is missing required event details")

    if "currency" in details and (not isinstance(details["currency"], str) or len(details["currency"]) != 3):
        raise ValueError("currency must be an ISO-4217 code")
    for key in ("unit_price_minor", "total_minor"):
        if key in details and (not isinstance(details[key], int) or details[key] < 0):
            raise ValueError(f"{key} must be a non-negative integer in minor units")
    if event_type == "checkout.payment_method_selected" and details["payment_method_family"] not in {
        "card", "wallet", "bank_transfer", "cash_on_delivery", "other"
    }:
        raise ValueError("unsupported payment method family")
    if event_type in {"checkout.item_removed", "checkout.item_replaced"}:
        reason = details.get("explicit_reason")
        if reason is not None and reason not in _ALLOWED_REMOVAL_REASONS:
            raise ValueError("unsupported explicit removal reason")

    return {
        "schema_version": "1.0",
        "event_id": payload["event_id"],
        "event_type": "tal.checkout_observation",
        "subject_id": payload["subject_id"],
        "checkout_id": payload["checkout_id"],
        "occurred_at": payload["occurred_at"],
        "source_event_type": event_type,
        "evidence_type": "explicit_checkout_choice" if event_type != "commerce.order.paid" else "verified_transaction",
        "signal_strength": "weak",
        "signal_semantics": (
            "transaction_choice_is_not_a_declared_preference"
            if event_type == "commerce.order.paid"
            else "observed_choice_not_a_declared_preference"
        ),
        "details": details,
        "consent": {"purpose": "personalization", "receipt_id": payload["consent_receipt_id"], "verified": True},
        "may_create_hard_npl_veto": False,
        "may_change_explicit_preference": False,
        "owner": "TAL",
        "persistence": "handoff_required",
    }
