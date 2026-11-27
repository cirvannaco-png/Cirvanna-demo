from __future__ import annotations

import threading

from app import main


def test_catalog_and_offer_reads_execute_concurrently_and_join_only_active_products(monkeypatch):
    monkeypatch.setenv("CATALOG_SERVICE_URL", "https://catalog.internal")
    monkeypatch.setenv("CATALOG_API_TOKEN", "catalog-token-with-at-least-32-bytes-long")
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.internal")
    monkeypatch.setenv("COMMERCE_MARKETPLACE_READ_TOKEN", "commerce-read-token-with-at-least-32-bytes")

    barrier = threading.Barrier(2)
    lock = threading.Lock()
    active = 0
    maximum_active = 0
    calls = {}

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            assert kwargs.get("trust_env") is False
            assert kwargs.get("follow_redirects") is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, *, params, headers):
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
                calls[url] = {"params": params, "headers": headers}
            try:
                barrier.wait(timeout=2)
                if url.endswith("/products"):
                    return FakeResponse({"items": [
                        {"product_id": "p-active", "status": "active"},
                        {"product_id": "p-draft", "status": "draft"},
                    ]})
                return FakeResponse({"items": [
                    {"catalog_product_id": "p-active", "offer_id": "o-active"},
                    {"catalog_product_id": "p-draft", "offer_id": "o-draft"},
                    {"catalog_product_id": "p-unknown", "offer_id": "o-unknown"},
                ]})
            finally:
                with lock:
                    active -= 1

    monkeypatch.setattr(main.httpx, "Client", FakeClient)
    request = main.DiscoveryRequest(
        user_id="verified-subject",
        query="cotton shirt",
        category="tops",
        currency="KES",
        market_country_code="KE",
        display_currency="KES",
        limit=10,
    )

    products, offers = main._discover_catalog_and_offers(request)

    assert maximum_active == 2
    assert [item["product_id"] for item in products] == ["p-active"]
    assert [item["offer_id"] for item in offers] == ["o-active"]
    assert calls["https://catalog.internal/products"]["params"] == {
        "limit": 10, "offset": 0, "q": "cotton shirt", "category": "tops"
    }
    assert calls["https://commerce.internal/marketplace/offers"]["params"]["market_country_code"] == "KE"
    assert calls["https://commerce.internal/marketplace/offers"]["headers"]["X-Commerce-Marketplace-Read-Token"].startswith("commerce-read-token")