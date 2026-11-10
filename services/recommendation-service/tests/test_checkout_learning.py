import pytest

from app.intelligence.checkout_learning import build_checkout_observation


def base(**overrides):
    payload = {
        "consent_verified": True,
        "consent_receipt_id": "consent-receipt-123",
        "event_id": "event-123",
        "subject_id": "subject-123",
        "checkout_id": "checkout-123",
        "event_type": "checkout.offer_selected",
        "occurred_at": "2026-11-10T12:00:00Z",
        "variant_id": "variant-123",
        "merchant_id": "merchant-123",
        "currency": "KES",
        "unit_price_minor": 125000,
        "email": "should-not-be-forwarded@example.test",
        "shipping_address": "private address",
    }
    payload.update(overrides)
    return payload


def test_offer_choice_is_weak_observation_and_excludes_pii():
    event = build_checkout_observation(base())
    assert event["event_type"] == "tal.checkout_observation"
    assert event["signal_strength"] == "weak"
    assert event["may_change_explicit_preference"] is False
    assert event["may_create_hard_npl_veto"] is False
    assert event["details"] == {
        "variant_id": "variant-123",
        "merchant_id": "merchant-123",
        "currency": "KES",
        "unit_price_minor": 125000,
    }
    assert "email" not in event["details"]
    assert "shipping_address" not in event["details"]


def test_checkout_observation_requires_verified_purpose_consent():
    with pytest.raises(ValueError, match="verified personalization consent"):
        build_checkout_observation(base(consent_verified=False))


@pytest.mark.parametrize("event_type", ["checkout.abandoned", "checkout.payment_failed", "checkout.cancelled"])
def test_abandonment_and_failure_are_not_preference_signals(event_type):
    with pytest.raises(ValueError, match="unsupported checkout observation"):
        build_checkout_observation(base(event_type=event_type))


def test_item_removal_without_reason_does_not_infer_dislike():
    event = build_checkout_observation(base(event_type="checkout.item_removed"))
    assert event["details"]["variant_id"] == "variant-123"
    assert "explicit_reason" not in event["details"]
    assert "dislike" not in event["signal_semantics"]


def test_payment_method_observation_stores_family_not_account_details():
    event = build_checkout_observation(base(
        event_type="checkout.payment_method_selected",
        payment_method_family="bank_transfer",
        bank_account_number="do-not-store",
        bank_name="private bank",
    ))
    assert event["details"] == {"payment_method_family": "bank_transfer"}


def test_paid_order_requires_verified_payment_authority():
    with pytest.raises(ValueError, match="verified Commerce payment authority"):
        build_checkout_observation(base(
            event_type="commerce.order.paid",
            order_id="order-123",
            currency="KES",
            total_minor=125000,
            ownership_authority="user_asserted",
        ))


def test_verified_paid_order_is_still_only_a_weak_transaction_signal():
    event = build_checkout_observation(base(
        event_type="commerce.order.paid",
        order_id="order-123",
        currency="KES",
        total_minor=125000,
        ownership_authority="verified_payment",
    ))
    assert event["signal_strength"] == "weak"
    assert event["evidence_type"] == "verified_transaction"
    assert event["may_change_explicit_preference"] is False


def test_invalid_currency_and_amount_are_rejected():
    with pytest.raises(ValueError, match="ISO-4217"):
        build_checkout_observation(base(currency="K"))
    with pytest.raises(ValueError, match="non-negative integer"):
        build_checkout_observation(base(unit_price_minor=-1))
