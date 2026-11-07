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
