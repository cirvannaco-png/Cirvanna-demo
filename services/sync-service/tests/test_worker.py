from __future__ import annotations

import httpx

from app.worker import CommerceWardrobeWorker, Settings


def settings():
    return Settings(
        commerce_url="https://commerce.internal",
        commerce_token="c" * 40,
        wardrobe_url="https://wardrobe.internal",
        wardrobe_token="w" * 40,
        worker_id="sync-test",
        batch_size=10,
    )


def paid_event():
    event_id = "123e4567-e89b-42d3-a456-426614174000"
    return {
        "event_id": event_id,
        "event_type": "commerce.order.paid",
        "schema_version": 1,
        "payload": {
            "event_id": event_id,
            "event_type": "commerce.order.paid",
            "schema_version": 1,
            "ownership_authority": "verified_payment",
            "buyer_user_id": "buyer-1",
            "order_id": "123e4567-e89b-42d3-a456-426614174001",
            "currency": "KES",
            "paid_at": "2026-11-07T09:00:00+00:00",
            "items": [{
                "order_item_id": "123e4567-e89b-42d3-a456-426614174002",
                "catalog_product_id": "product-1",
                "product_name": "Linen shirt",
                "quantity": 2,
                "unit_price_minor": 250000,
                "currency": "KES",
            }],
        },
    }


def test_worker_delivers_all_lines_before_acknowledging():
    calls = []
    def handler(request: httpx.Request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/internal/outbox/claim":
            return httpx.Response(200, json={"events": [paid_event()]})
        if request.url.path == "/v1/purchases/verified":
            body = __import__("json").loads(request.content)
            assert body["ownership_authority"] == "verified_payment"
            assert body["order_item_id"] == "123e4567-e89b-42d3-a456-426614174002"
            return httpx.Response(201, json={"status": "created"})
        if request.url.path.endswith("/ack"):
            return httpx.Response(200, json={"status": "delivered"})
        raise AssertionError(request.url.path)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = CommerceWardrobeWorker(settings(), client).process_batch()
    assert result == {"claimed": 1, "processed": 1, "retried": 0, "dead_lettered": 0}
    assert calls[-1][1].endswith("/ack")
    assert calls.index(("POST", "/v1/purchases/verified")) < calls.index(("POST", calls[-1][1]))


def refund_event():
    event_id = "223e4567-e89b-42d3-a456-426614174000"
    return {
        "event_id": event_id,
        "event_type": "commerce.order.refund.updated",
        "schema_version": 1,
        "payload": {
            "event_id": event_id,
            "provider_event_id": "evt_refund_0001",
            "event_type": "commerce.order.refund.updated",
            "schema_version": 1,
            "ownership_authority": "verified_stripe_charge_refund",
            "order_id": "123e4567-e89b-42d3-a456-426614174001",
            "buyer_user_id": "buyer-1",
            "payment_intent_id": "pi_test_0001",
            "charge_id": "ch_test_0001",
            "currency": "KES",
            "order_total_minor": 500000,
            "amount_refunded_minor": 250000,
            "refund_state": "partial_refund",
            "refunded_at": "2026-11-07T12:00:00+00:00",
            "physical_return_confirmed": False,
            "ownership_effect": "financial_status_only",
        },
    }


def test_worker_delivers_refund_snapshot_before_acknowledging():
    calls = []

    def handler(request: httpx.Request):
        calls.append(request.url.path)
        if request.url.path == "/internal/outbox/claim":
            return httpx.Response(200, json={"events": [refund_event()]})
        if request.url.path == "/v1/purchases/refund-status":
            body = __import__("json").loads(request.content)
            assert body["ownership_authority"] == "verified_stripe_charge_refund"
            assert body["order_id"] == "123e4567-e89b-42d3-a456-426614174001"
            assert body["physical_return_confirmed"] is False
            return httpx.Response(200, json={"status": "recorded", "wardrobe_items_unchanged": True})
        if request.url.path.endswith("/ack"):
            return httpx.Response(200, json={"status": "delivered"})
        raise AssertionError(request.url.path)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = CommerceWardrobeWorker(settings(), client).process_batch()
    assert result == {"claimed": 1, "processed": 1, "retried": 0, "dead_lettered": 0}
    assert calls.index("/v1/purchases/refund-status") < len(calls) - 1
    assert calls[-1].endswith("/ack")


def test_worker_rejects_refund_event_that_claims_physical_return():
    event = refund_event()
    event["payload"]["physical_return_confirmed"] = True
    calls = []

    def handler(request: httpx.Request):
        calls.append(request.url.path)
        if request.url.path == "/internal/outbox/claim":
            return httpx.Response(200, json={"events": [event]})
        if request.url.path.endswith("/fail"):
            return httpx.Response(200, json={"status": "retry_scheduled"})
        raise AssertionError("untrusted refund must not reach Wardrobe or ack")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = CommerceWardrobeWorker(settings(), client).process_batch()
    assert result == {"claimed": 1, "processed": 0, "retried": 1, "dead_lettered": 0}
    assert "/v1/purchases/refund-status" not in calls
    assert not any(path.endswith("/ack") for path in calls)


def test_worker_never_acks_an_unverified_event_and_sends_it_to_retry():
    event = paid_event()
    event["payload"]["ownership_authority"] = "user_asserted"
    calls = []
    def handler(request: httpx.Request):
        calls.append(request.url.path)
        if request.url.path == "/internal/outbox/claim":
            return httpx.Response(200, json={"events": [event]})
        if request.url.path.endswith("/fail"):
            return httpx.Response(200, json={"status": "retry_scheduled"})
        raise AssertionError("unverified event must not reach Wardrobe or ack")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = CommerceWardrobeWorker(settings(), client).process_batch()
    assert result == {"claimed": 1, "processed": 0, "retried": 1, "dead_lettered": 0}
    assert not any(path == "/v1/purchases/verified" or path.endswith("/ack") for path in calls)


def test_worker_retries_when_wardrobe_is_unavailable_without_acknowledging():
    calls = []
    def handler(request: httpx.Request):
        calls.append(request.url.path)
        if request.url.path == "/internal/outbox/claim":
            return httpx.Response(200, json={"events": [paid_event()]})
        if request.url.path == "/v1/purchases/verified":
            return httpx.Response(503)
        if request.url.path.endswith("/fail"):
            return httpx.Response(200, json={"status": "retry_scheduled"})
        raise AssertionError("worker must not ack failed Wardrobe delivery")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = CommerceWardrobeWorker(settings(), client).process_batch()
    assert result == {"claimed": 1, "processed": 0, "retried": 1, "dead_lettered": 0}
    assert not any(path.endswith("/ack") for path in calls)



def consented_paid_event():
    event = paid_event()
    payload = event["payload"]
    payload["personalization_consent_receipt_id"] = "tal-consent-receipt-0001"
    payload["total_minor"] = 500000
    payload["fulfillment_mode"] = "collection"
    payload["payment_method_family"] = "card"
    payload["items"][0]["merchant_id"] = "merchant-1"
    payload["items"][0]["merchant_variant_id"] = "variant-1"
    return event


def tal_settings():
    return Settings(
        commerce_url="https://commerce.internal",
        commerce_token="c" * 40,
        wardrobe_url="https://wardrobe.internal",
        wardrobe_token="w" * 40,
        worker_id="sync-test",
        identity_learning_url="https://identity.internal",
        identity_learning_token="i" * 40,
        batch_size=10,
    )


def test_worker_sends_minimized_paid_choice_to_tal_before_ack():
    calls = []

    def handler(request: httpx.Request):
        calls.append(request.url.path)
        if request.url.path == "/internal/outbox/claim":
            return httpx.Response(200, json={"events": [consented_paid_event()]})
        if request.url.path == "/v1/purchases/verified":
            return httpx.Response(201, json={"status": "created"})
        if request.url.path == "/v1/tal/events":
            body = __import__("json").loads(request.content)
            value = __import__("json").loads(body["value"])
            assert request.url.params["subject_id"] == "buyer-1"
            assert body["consent_receipt_id"] == "tal-consent-receipt-0001"
            assert body["feature_key"] == "checkout.purchase_choice"
            assert value["signal_strength"] == "weak"
            assert value["payment_method_family"] == "card"
            assert value["fulfillment_mode"] == "collection"
            assert value["may_change_explicit_preference"] is False
            assert "product_name" not in value["items"][0]
            assert "email" not in body["value"]
            return httpx.Response(201, json={"status": "created"})
        if request.url.path.endswith("/ack"):
            return httpx.Response(200, json={"status": "delivered"})
        raise AssertionError(request.url.path)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = CommerceWardrobeWorker(tal_settings(), client).process_batch()
    assert result == {"claimed": 1, "processed": 1, "retried": 0, "dead_lettered": 0}
    assert calls.index("/v1/purchases/verified") < calls.index("/v1/tal/events") < len(calls) - 1
    assert calls[-1].endswith("/ack")


def test_worker_skips_tal_write_when_consent_was_revoked_without_blocking_ownership():
    calls = []

    def handler(request: httpx.Request):
        calls.append(request.url.path)
        if request.url.path == "/internal/outbox/claim":
            return httpx.Response(200, json={"events": [consented_paid_event()]})
        if request.url.path == "/v1/purchases/verified":
            return httpx.Response(201, json={"status": "created"})
        if request.url.path == "/v1/tal/events":
            return httpx.Response(403, json={"detail": {"code": "ACTIVE_TAL_CONSENT_REQUIRED"}})
        if request.url.path.endswith("/ack"):
            return httpx.Response(200, json={"status": "delivered"})
        raise AssertionError(request.url.path)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = CommerceWardrobeWorker(tal_settings(), client).process_batch()
    assert result == {"claimed": 1, "processed": 1, "retried": 0, "dead_lettered": 0}
    assert "/v1/purchases/verified" in calls
    assert "/v1/tal/events" in calls
    assert calls[-1].endswith("/ack")
