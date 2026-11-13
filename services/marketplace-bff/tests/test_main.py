import json

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import main


class FakeResponse:
    def __init__(self, payload, status_code=200, content=None, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {"content-type": "application/json"}
        self.content = content if content is not None else json.dumps(payload).encode()

    def json(self):
        return self._payload


@pytest.fixture
def client():
    with TestClient(main.app) as test_client:
        yield test_client


def configure_upstreams(monkeypatch):
    monkeypatch.setenv("CATALOG_API_URL", "https://catalog.example.test")
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")


def test_marketplace_pnelly_search_uses_wardrobe_cil_path_and_complementer_advisory(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="aiDiscoveryResults"' in response.text
    assert '"/api/wardrobe/recommendations"' in response.text
    assert '"/api/vision/complementer"' in response.text
    assert "CAL SHOW" in response.text
    assert "wardrobe-aware marketplace" in response.text
    # Click It stays explicitly unavailable while its publication lifecycle remains unverified.
    assert "Click It · Temporarily paused" in response.text
    assert "No photo is requested or sent from this page" in response.text


def test_page_bootstraps_same_origin_live_offers_not_demo_data(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'window.CIRVANNA_MARKETPLACE_CONFIG = Object.freeze({publicOffersBase:"/api/commerce"});' in response.text
    assert "bootstrap.publicOffersBase" in response.text
    assert "connect-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_marketplace_offers_use_authenticated_gateway_cal_show_only(client, monkeypatch):
    configure_upstreams(monkeypatch)
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({
            "request_id": "req-marketplace-1",
            "ranked_candidate_count": 2,
            "displayable_products": [{
                "product": {
                    "product_id": "product-1", "name": "Linen shirt", "brand": "Cirvanna",
                    "category": "Fashion", "description": "A linen shirt",
                    "attributes": {"material": "linen"},
                    "image_urls": ["https://cdn.example.test/unverified-product.jpg"],
                },
                "offer": {
                    "catalog_product_id": "product-1", "variant_id": "variant-1",
                    "merchant_id": "merchant-1", "merchant_name": "Merchant One",
                    "product_name": "Linen shirt", "category": "Fashion", "sku": "LINEN-M",
                    "options": {"size": "M"}, "price_minor": 2500, "currency": "KES",
                    "available_stock": 3, "image_urls": ["https://cdn.example.test/unverified-offer.jpg"],
                    "product": {"image_urls": ["https://cdn.example.test/nested.jpg"]},
                },
                "decision": {"verdict": "show", "may_display": True, "policy_version": "policy-1"},
            }],
            "withheld_candidate_ids": [{"product_id": "blocked-product-secret", "decision": "review"}],
            "display_authority": "CaTaCaCi/CAL",
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get(
        "/api/commerce/marketplace/offers?q=linen&category=Fashion&market_country_code=KE&display_currency=KES&destination_key=Nakuru%2FSubukia&fulfillment_mode=courier_delivery&radius_km=75&offset=20&limit=10",
        headers={"Authorization": "Bearer signed-session"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["display_authority"] == "CaTaCaCi/CAL"
    assert data["withheld_candidate_count"] == 1
    assert "withheld_candidate_ids" not in data
    assert "blocked-product-secret" not in response.text
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["variant_id"] == "variant-1"
    assert item["product_name"] == "Linen shirt"
    assert item["image_urls"] == []
    assert item["product"]["image_urls"] == []
    assert fake.calls[0][1] == "https://commerce.example.test/me"
    assert fake.calls[1][1] == "https://decision.example.test/v1/discover"
    assert fake.calls[1][2]["headers"]["X-End-User-Authorization"] == "Bearer signed-session"
    sent = fake.calls[1][2]["json"]
    assert sent["user_id"] == "signed-user-42"
    assert sent["query"] == "linen"
    assert sent["market_country_code"] == "KE"
    assert sent["display_currency"] == "KES"
    assert sent["destination_key"] == "Nakuru/Subukia"
    assert sent["fulfillment_mode"] == "courier_delivery"
    assert sent["radius_km"] == 75.0
    assert sent["offset"] == 20
    assert "Authorization" not in response.text


def test_account_proxy_requires_bearer_and_blocks_admin_routes(client, monkeypatch):
    configure_upstreams(monkeypatch)
    calls = []
    monkeypatch.setattr(main.httpx, "request", lambda *args, **kwargs: calls.append(args) or FakeResponse({}))
    assert client.get("/api/commerce/me").status_code == 401
    denied = client.get("/api/commerce/admin/inventory/audit", headers={"Authorization": "Bearer customer-token"})
    assert denied.status_code == 404
    assert calls == []


def test_cart_and_checkout_require_candidate_bound_cal_reauthorization(client, monkeypatch):
    configure_upstreams(monkeypatch)
    calls = []
    monkeypatch.setattr(main.httpx, "request", lambda *args, **kwargs: calls.append((args, kwargs)) or FakeResponse({}))
    headers = {"Authorization": "Bearer customer-token", "Content-Type": "application/json"}
    variant = "123e4567-e89b-12d3-a456-426614174000"
    requests = [
        client.get("/api/commerce/cart", headers=headers),
        client.post("/api/commerce/cart/items", headers=headers, json={"variant_id": variant, "quantity": 1}),
        client.patch(f"/api/commerce/cart/items/{variant}", headers=headers, json={"quantity": 2}),
        client.post("/api/commerce/checkout", headers=headers, json={"confirm": True}),
    ]
    assert [response.status_code for response in requests] == [503, 503, 503, 503]
    assert all(response.json()["detail"]["code"] == "CAL_CANDIDATE_PURCHASE_REAUTH_REQUIRED" for response in requests)
    assert calls == []

    # Removing an existing cart line is a safe cleanup operation and remains available.
    removed = client.delete(f"/api/commerce/cart/items/{variant}", headers=headers)
    assert removed.status_code == 200
    assert calls and calls[0][0][0] == "DELETE"


def test_account_proxy_does_not_forward_checkout_without_candidate_authorization(client, monkeypatch):
    configure_upstreams(monkeypatch)
    calls = []
    monkeypatch.setattr(main.httpx, "request", lambda *args, **kwargs: calls.append((args, kwargs)) or FakeResponse({}))
    response = client.post(
        "/api/commerce/checkout",
        headers={
            "Authorization": "Bearer user-session-token",
            "Content-Type": "application/json",
            "Idempotency-Key": "checkout-test-key",
        },
        json={"confirm": True},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CAL_CANDIDATE_PURCHASE_REAUTH_REQUIRED"
    assert calls == []


def test_readiness_fails_closed_until_both_upstreams_are_ready(client, monkeypatch):
    configure_upstreams(monkeypatch)
    monkeypatch.delenv("CATALOG_API_TOKEN", raising=False)
    monkeypatch.setattr(main.httpx, "get", lambda *args, **kwargs: FakeResponse({"ready": True}))
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    assert ready.json()["catalog_ready"] is True
    assert ready.json()["catalog_url_configured"] is True
    assert ready.json()["commerce_ready"] is True

    monkeypatch.setattr(main.httpx, "get", lambda *args, **kwargs: FakeResponse({"ready": False}, status_code=503))
    pending = client.get("/ready")
    assert pending.status_code == 503
    assert pending.json()["detail"]["ready"] is False


def test_marketplace_guest_browse_requires_verified_user_bearer(client, monkeypatch):
    configure_upstreams(monkeypatch)
    fake = FakeAsyncClient([])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/commerce/marketplace/offers")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "USER_BEARER_REQUIRED"
    assert fake.calls == []

class FakeAsyncClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)

    async def patch(self, url, **kwargs):
        self.calls.append(("PATCH", url, kwargs))
        return self.responses.pop(0)

    async def put(self, url, **kwargs):
        self.calls.append(("PUT", url, kwargs))
        return self.responses.pop(0)

    async def delete(self, url, **kwargs):
        self.calls.append(("DELETE", url, kwargs))
        return self.responses.pop(0)



def test_description_search_fails_closed_without_pnelly_or_legacy_credentials(client, monkeypatch):
    for name in ("PNELLY_API_URL", "PNELLY_API_TOKEN", "XARI_API_URL", "XARI_API_TOKEN", "TARI_API_URL", "TARI_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    response = client.post("/api/vision/marketplace-search", json={"query": "blue linen summer dress"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PNELLY_API_URL_NOT_CONFIGURED"


def test_description_search_forwards_to_legacy_xari_alias_but_suppresses_all_candidates_until_cal(client, monkeypatch):
    monkeypatch.setenv("XARI_API_URL", "https://xari.example.test")
    monkeypatch.setenv("XARI_API_TOKEN", "xari-internal-token-at-least-thirty-two-bytes")
    fake = FakeAsyncClient([FakeResponse({
        "status": "complete",
        "query": "green linen dress",
        "candidate_count": 2,
        "candidates": [{
            "variant_id": "offer-1",
            "product_name": "green dress",
            "merchant_name": "unapproved merchant",
            "price_minor": 1234,
            "image_urls": ["https://cdn.example.test/unverified.jpg"],
            "product": {"name": "private product", "image_urls": ["https://cdn.example.test/nested.jpg"]},
        }],
        # PNELLY is not the CAL owner. These deliberately false/forged claims
        # must never authorize disclosure through this retrieval-only route.
        "display_authorized": True,
        "decision_status": "SHOW",
        "scores_are_probabilities": False,
    })])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post("/api/vision/marketplace-search", json={"query": " green   linen dress ", "limit": 5})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["candidate_count"] == 2
    assert data["display_authorized"] is False
    assert data["decision_status"] == "PENDING_CAL"
    assert "candidates" not in data
    for private_value in ("offer-1", "green dress", "unapproved merchant", "1234", "private product", "cdn.example.test"):
        assert private_value not in response.text
    assert fake.calls[0][1] == "https://xari.example.test/v1/marketplace/search"
    assert fake.calls[0][2]["json"]["query"] == "green linen dress"
    assert "Authorization" not in response.text


def test_click_it_requires_signed_user_token_before_upstream_calls(client, monkeypatch):
    response = client.post(
        "/api/vision/click-it",
        data={
            "consent_id": "consent-record-1234",
            "consent_image_processing": "true",
            "consent_click_it": "true",
        },
        files={"product_image": ("dress.png", b"not-used", "image/png")},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "USER_BEARER_REQUIRED"


def test_click_it_fails_closed_before_reading_or_forwarding_the_uploaded_photo(client, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Click It must not call upstream services while masking is unreleased")

    monkeypatch.setattr(main.httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(main, "_upstream_base", forbidden)
    monkeypatch.setattr(main, "_internal_service", forbidden)

    response = client.post(
        "/api/vision/click-it",
        headers={"Authorization": "Bearer signed-user-token"},
        data={
            "consent_id": "consent-record-1234",
            "consent_image_processing": "true",
            "consent_click_it": "true",
        },
        files={"product_image": ("dress.png", b"unmasked-private-photo-bytes", "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CLICK_IT_PRIVACY_PIPELINE_NOT_RELEASED"
    assert response.headers["cache-control"] == "no-store"


def test_click_it_rejects_before_multipart_form_parser_is_invoked(client, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Click It must return 503 without parsing multipart photo bytes")

    monkeypatch.setattr(Request, "form", forbidden)
    monkeypatch.setattr(Request, "body", forbidden)
    monkeypatch.setattr(Request, "stream", forbidden)
    response = client.post(
        "/api/vision/click-it",
        headers={"Authorization": "Bearer signed-user-token"},
        data={"consent_image_processing": "true", "consent_click_it": "true"},
        files={"product_image": ("private.jpg", b"do-not-parse-this-photo", "image/jpeg")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CLICK_IT_PRIVACY_PIPELINE_NOT_RELEASED"
    assert response.headers["cache-control"] == "no-store"


def test_click_it_requires_authentication_without_parsing_multipart(client, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Unauthenticated Click It request must not parse multipart body")

    monkeypatch.setattr(Request, "form", forbidden)
    monkeypatch.setattr(Request, "body", forbidden)
    monkeypatch.setattr(Request, "stream", forbidden)
    response = client.post(
        "/api/vision/click-it",
        files={"product_image": ("private.jpg", b"do-not-parse-this-photo", "image/jpeg")},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "USER_BEARER_REQUIRED"


def test_click_it_fails_closed_for_every_upload_type_without_content_inspection(client, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Click It must stop before content inspection or upstream calls")

    monkeypatch.setattr(main.httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(main, "_upstream_base", forbidden)
    monkeypatch.setattr(main, "_internal_service", forbidden)

    response = client.post(
        "/api/vision/click-it",
        headers={"Authorization": "Bearer signed-user-token"},
        data={
            "consent_id": "consent-record-1234",
            "consent_image_processing": "true",
            "consent_click_it": "true",
        },
        files={"product_image": ("payload.bin", b"opaque-bytes", "application/octet-stream")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CLICK_IT_PRIVACY_PIPELINE_NOT_RELEASED"


def test_click_it_route_is_registered_exactly_once(client):
    routes = [
        route for route in main.app.routes
        if getattr(route, "path", None) == "/api/vision/click-it"
        and "POST" in (getattr(route, "methods", set()) or set())
    ]
    assert len(routes) == 1


def test_bff_has_no_duplicate_method_path_route_registrations(client):
    counts = {}
    for route in main.app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", set()) or set()
        for method in methods:
            key = (method, path)
            counts[key] = counts.get(key, 0) + 1
    duplicates = {key: count for key, count in counts.items() if count > 1}
    assert duplicates == {}


def test_marketplace_ui_does_not_solicit_click_it_photos_while_pipeline_is_blocked(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="aiQuery"' in response.text
    assert 'id="aiSearchBtn"' in response.text
    assert "Click It · Temporarily paused" in response.text
    assert "Photo search is temporarily unavailable" in response.text
    assert "face masking, consent enforcement, and asset-bound privacy attestation" in response.text
    assert "No photo is requested or sent from this page" in response.text
    assert "Use PNELLY description search in the meantime" in response.text
    assert 'id="clickItImage"' not in response.text
    assert 'id="clickItConsentId"' not in response.text
    assert 'id="clickItForm"' not in response.text
    assert 'fetch("/api/vision/marketplace-search"' in response.text
    assert 'fetch("/api/vision/click-it"' not in response.text
    assert "display_authorized===true" not in response.text
    assert "PENDING_CAL" in response.text

def test_description_search_keeps_xari_credentials_as_legacy_fallback(client, monkeypatch):
    monkeypatch.setenv("XARI_API_URL", "https://xari.example.test")
    monkeypatch.setenv("XARI_API_TOKEN", "xari-internal-token-at-least-thirty-two-bytes")
    monkeypatch.setenv("TARI_API_URL", "https://legacy-tari.example.test")
    monkeypatch.setenv("TARI_API_TOKEN", "legacy-tari-token-at-least-thirty-two-bytes")
    fake = FakeAsyncClient([FakeResponse({
        "status": "complete",
        "query": "linen shirt",
        "candidate_count": 1,
        "candidates": [{"variant_id": "offer-1", "product_name": "linen shirt"}],
        "display_authorized": False,
        "decision_status": "PENDING_CAL",
        "scores_are_probabilities": False,
    })])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post("/api/vision/marketplace-search", json={"query": "linen shirt"})
    assert response.status_code == 200, response.text
    assert fake.calls[0][1] == "https://xari.example.test/v1/marketplace/search"
    assert fake.calls[0][2]["headers"]["Authorization"] == "Bearer xari-internal-token-at-least-thirty-two-bytes"


def test_description_search_prefers_pnelly_credentials_over_xari_and_tari(client, monkeypatch):
    monkeypatch.setenv("PNELLY_API_URL", "https://pnelly.example.test")
    monkeypatch.setenv("PNELLY_API_TOKEN", "pnelly-internal-token-at-least-thirty-two-bytes")
    monkeypatch.setenv("XARI_API_URL", "https://xari.example.test")
    monkeypatch.setenv("XARI_API_TOKEN", "xari-internal-token-at-least-thirty-two-bytes")
    monkeypatch.setenv("TARI_API_URL", "https://legacy-tari.example.test")
    monkeypatch.setenv("TARI_API_TOKEN", "legacy-tari-token-at-least-thirty-two-bytes")
    fake = FakeAsyncClient([FakeResponse({
        "status": "complete",
        "query": "linen shirt",
        "candidate_count": 1,
        "candidates": [{"variant_id": "offer-1", "product_name": "linen shirt"}],
        "display_authorized": False,
        "decision_status": "PENDING_CAL",
        "scores_are_probabilities": False,
    })])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post("/api/vision/marketplace-search", json={"query": "linen shirt"})
    assert response.status_code == 200, response.text
    assert fake.calls[0][1] == "https://pnelly.example.test/v1/marketplace/search"
    assert fake.calls[0][2]["headers"]["Authorization"] == "Bearer pnelly-internal-token-at-least-thirty-two-bytes"


def test_pnelly_url_never_uses_xari_or_tari_token_as_a_cross_provider_fallback(client, monkeypatch):
    monkeypatch.setenv("PNELLY_API_URL", "https://pnelly.example.test")
    monkeypatch.delenv("PNELLY_API_TOKEN", raising=False)
    monkeypatch.setenv("XARI_API_URL", "https://xari.example.test")
    monkeypatch.setenv("XARI_API_TOKEN", "xari-internal-token-at-least-thirty-two-bytes")
    monkeypatch.setenv("TARI_API_TOKEN", "legacy-tari-token-at-least-thirty-two-bytes")
    response = client.post("/api/vision/marketplace-search", json={"query": "linen shirt"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PNELLY_API_TOKEN_NOT_CONFIGURED"


def test_description_search_uses_tari_only_as_the_final_legacy_fallback(client, monkeypatch):
    monkeypatch.delenv("PNELLY_API_URL", raising=False)
    monkeypatch.delenv("PNELLY_API_TOKEN", raising=False)
    monkeypatch.delenv("XARI_API_URL", raising=False)
    monkeypatch.delenv("XARI_API_TOKEN", raising=False)
    monkeypatch.setenv("TARI_API_URL", "https://legacy-tari.example.test")
    monkeypatch.setenv("TARI_API_TOKEN", "legacy-tari-token-at-least-thirty-two-bytes")
    fake = FakeAsyncClient([FakeResponse({
        "status": "complete",
        "query": "linen shirt",
        "candidate_count": 0,
        "candidates": [],
        "display_authorized": False,
        "decision_status": "PENDING_CAL",
        "scores_are_probabilities": False,
    })])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post("/api/vision/marketplace-search", json={"query": "linen shirt"})
    assert response.status_code == 200, response.text
    assert fake.calls[0][1] == "https://legacy-tari.example.test/v1/marketplace/search"
    assert fake.calls[0][2]["headers"]["Authorization"] == "Bearer legacy-tari-token-at-least-thirty-two-bytes"


def test_wardrobe_items_are_bound_to_verified_commerce_subject(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({
            "owner_user_id": "signed-user-42",
            "items": [{"owner_user_id": "signed-user-42", "item_id": "closet-1", "status": "active"}],
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/wardrobe/items", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["items"][0]["item_id"] == "closet-1"
    assert fake.calls[0][1] == "https://commerce.example.test/me"
    assert fake.calls[1][1] == "https://wardrobe.example.test/v1/items"
    assert fake.calls[1][2]["params"]["owner_user_id"] == "signed-user-42"
    assert fake.calls[1][2]["headers"]["Authorization"] == "Bearer wardrobe-internal-token-more-than-thirty-two-bytes"


def test_wardrobe_bff_rejects_cross_subject_upstream_data(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({
            "owner_user_id": "signed-user-42",
            "items": [{"owner_user_id": "another-user", "item_id": "foreign-item", "status": "active"}],
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/wardrobe/items", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "WARDROBE_SCOPE_OR_SCHEMA_MISMATCH"


def test_wardrobe_feedback_forwards_only_verified_subject_to_service(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"status": "recorded", "event_id": "feedback-event-123", "delivery_state": "delivered"}, status_code=201),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/feedback",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "item_id": "closet-1",
            "event_id": "feedback-event-123",
            "signal": "dislike",
            "consent_receipt_id": "receipt-style-123",
            "target_type": "attribute",
            "target_value": "blue",
        },
    )
    assert response.status_code == 200, response.text
    forwarded = fake.calls[1][2]["json"]
    assert forwarded["owner_user_id"] == "signed-user-42"
    assert forwarded["observed_at"].endswith("Z")
    assert "owner_user_id" not in response.request.content.decode(errors="ignore")
    assert fake.calls[1][2]["headers"]["Authorization"] == "Bearer wardrobe-internal-token-more-than-thirty-two-bytes"


def test_wardrobe_consent_receipt_is_created_server_side_and_subject_scoped(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"status": "recorded", "granted": True}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/consents",
        headers={"Authorization": "Bearer signed-session"},
        json={"scope": "style_learning", "granted": True},
    )
    assert response.status_code == 200
    assert response.json()["subject_id"] == "signed-user-42"
    assert len(response.json()["receipt_id"]) == 36
    assert fake.calls[1][1] == "https://identity.example.test/v1/tal/consents"
    assert fake.calls[1][2]["params"]["subject_id"] == "signed-user-42"
    assert fake.calls[1][2]["json"]["scope"] == "style_learning"


def test_wardrobe_recommendations_forward_verified_token_to_cal_decision_gateway(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({
            "request_id": "req-1",
            "ranked_candidate_count": 1,
            "displayable_products": [{
                "product": {"product_id": "product-1", "catalog_version": 3,
                            "image_urls": ["https://cdn.example.test/product.jpg"]},
                "offer": {"catalog_product_id": "product-1", "variant_id": "variant-1",
                          "image_urls": ["https://cdn.example.test/offer.jpg"],
                          "product": {"image_urls": ["https://cdn.example.test/nested-offer.jpg"]}},
                "decision": {"product_id": "product-1", "catalog_version": 3,
                             "verdict": "show", "may_display": True},
                "cil_serving_assessment": {"status": "eligible", "assessed_catalog_version": 3},
            }],
            "withheld_candidate_ids": [{"product_id": "blocked-product-secret", "decision": "review"}],
            "display_authority": "CaTaCaCi/CAL",
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/recommendations",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "query": "light layer for my blue shirt",
            "location": "Subukia",
            "occasion": "everyday",
            "climate": "warm",
            "currency": "KES",
        },
    )
    assert response.status_code == 200, response.text
    sent = fake.calls[1][2]
    assert fake.calls[1][1] == "https://decision.example.test/v1/discover"
    assert sent["headers"]["X-End-User-Authorization"] == "Bearer signed-session"
    assert sent["json"]["user_id"] == "signed-user-42"
    assert sent["json"]["use_wardrobe_context"] is True
    assert sent["json"]["context"]["location_source"] == "user_declared"
    assert sent["json"]["context"]["climate_source"] == "user_declared"
    result = response.json()["displayable_products"][0]
    assert result["product"]["image_urls"] == []
    assert result["offer"]["image_urls"] == []
    assert result["offer"]["product"]["image_urls"] == []
    assert response.json()["withheld_candidate_count"] == 1
    assert "withheld_candidate_ids" not in response.json()
    assert "blocked-product-secret" not in response.text
    assert "Authorization" not in response.text


def test_wardrobe_page_exposes_feedback_and_consent_controls(client):
    response = client.get("/wardrobe")
    assert response.status_code == 200
    assert "Enable style learning" in response.text
    assert "Dislike" in response.text
    assert "Avoid" in response.text
    assert "/api/wardrobe/recommendations" in response.text
    assert "/api/vision/complementer" in response.text
    assert "Refine with Complementer" in response.text
    assert "profile_storage" in response.text
    assert "Edit piece" in response.text
    assert "/api/wardrobe/items/" in response.text
    assert 'method: "PATCH"' in response.text


def test_wardrobe_consent_listing_is_subject_scoped(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse([{
            "receipt_id": "receipt-style-123",
            "scope": "style_learning",
            "granted": True,
            "revoked_at": None,
        }]),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/wardrobe/consents", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 200
    assert response.json()["subject_id"] == "signed-user-42"
    assert response.json()["items"][0]["receipt_id"] == "receipt-style-123"
    assert fake.calls[1][1] == "https://identity.example.test/v1/tal/consents/signed-user-42"


def test_wardrobe_consent_revocation_is_subject_scoped(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"status": "revoked", "receipt_id": "receipt-style-123"}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/consents/receipt-style-123/revoke",
        headers={"Authorization": "Bearer signed-session"},
    )
    assert response.status_code == 200
    assert fake.calls[1][1] == "https://identity.example.test/v1/tal/consents/receipt-style-123/revoke"
    assert fake.calls[1][2]["params"]["subject_id"] == "signed-user-42"


def test_wardrobe_manual_item_creation_binds_verified_owner_and_activates(client, monkeypatch):
    from uuid import UUID
    identifiers = iter([
        UUID("33333333-3333-4333-8333-333333333333"),
        UUID("44444444-4444-4444-8444-444444444444"),
    ])
    monkeypatch.setattr(main.uuid, "uuid4", lambda: next(identifiers))
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"item": {
            "owner_user_id": "signed-user-42", "item_id": "33333333-3333-4333-8333-333333333333",
            "version": 1, "status": "draft",
        }}, status_code=201),
        FakeResponse({"item": {
            "owner_user_id": "signed-user-42", "item_id": "33333333-3333-4333-8333-333333333333",
            "version": 2, "status": "active",
        }}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/items",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "display_name": "Blue linen shirt",
            "category": "tops",
            "attributes": ["blue", "linen", "relaxed"],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["item"]["status"] == "active"
    created = fake.calls[1][2]["json"]
    transition = fake.calls[2][2]["json"]
    assert created["owner_user_id"] == "signed-user-42"
    assert created["image_asset_id"] is None
    assert created["image_storage_consent"] is False
    assert transition["owner_user_id"] == "signed-user-42"
    assert transition["target_status"] == "active"


def test_wardrobe_consent_listing_allows_closet_browse_when_learning_provider_absent(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.delenv("IDENTITY_SERVICE_URL", raising=False)
    monkeypatch.delenv("IDENTITY_SERVICE_TOKEN", raising=False)
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/wardrobe/consents", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 200
    assert response.json()["learning_configured"] is False
    assert response.json()["items"] == []
    assert len(fake.calls) == 1



def test_wardrobe_item_edit_binds_verified_owner_and_updates_only_requested_item(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"item": {
            "item_id": "item-001", "owner_user_id": "signed-user-42",
            "display_name": "Updated linen shirt", "category": "tops",
            "attributes": ["blue", "linen"], "version": 2, "status": "active",
        }, "status": "updated"}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.patch(
        "/api/wardrobe/items/item-001",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "expected_version": 1, "command_id": "edit-command-001",
            "display_name": "Updated linen shirt", "attributes": ["blue", "linen"],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["item"]["version"] == 2
    assert fake.calls[1][0] == "PATCH"
    assert fake.calls[1][1] == "https://wardrobe.example.test/v1/items/item-001"
    sent = fake.calls[1][2]["json"]
    assert sent["owner_user_id"] == "signed-user-42"
    assert sent["expected_version"] == 1
    assert sent["command_id"] == "edit-command-001"
    assert sent["display_name"] == "Updated linen shirt"


def test_wardrobe_item_edit_rejects_client_supplied_owner_and_empty_change(client, monkeypatch):
    response = client.patch(
        "/api/wardrobe/items/item-001",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "owner_user_id": "attacker", "expected_version": 1, "command_id": "edit-command-002",
            "display_name": "Forged edit",
        },
    )
    assert response.status_code == 422
    empty = client.patch(
        "/api/wardrobe/items/item-001",
        headers={"Authorization": "Bearer signed-session"},
        json={"expected_version": 1, "command_id": "edit-command-003"},
    )
    assert empty.status_code == 422
    assert empty.json()["detail"]["code"] == "WARDROBE_EDIT_EMPTY"


def test_wardrobe_item_edit_preserves_version_conflict(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"detail": {"code": "WARDROBE_VERSION_CONFLICT", "current_version": 3}}, status_code=409),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.patch(
        "/api/wardrobe/items/item-001",
        headers={"Authorization": "Bearer signed-session"},
        json={"expected_version": 1, "command_id": "edit-command-004", "category": "outerwear"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "WARDROBE_VERSION_CONFLICT"
    assert response.json()["detail"]["current_version"] == 3


def test_wardrobe_item_edit_rejects_mismatched_upstream_owner(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"item": {
            "item_id": "item-001", "owner_user_id": "another-user",
            "display_name": "Not yours", "category": "tops", "attributes": [], "version": 2,
        }}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.patch(
        "/api/wardrobe/items/item-001",
        headers={"Authorization": "Bearer signed-session"},
        json={"expected_version": 1, "command_id": "edit-command-005", "display_name": "Changed"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "WARDROBE_ITEM_EDIT_SCOPE_MISMATCH"


def test_saved_outfit_bff_creates_owner_bound_outfit_and_server_generated_slots(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"outfit": {
            "outfit_id": "outfit-1", "owner_user_id": "signed-user-42",
            "name": "Weekend", "version": 1, "pieces": [],
        }, "status": "created"}, status_code=201),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post("/api/wardrobe/outfits", headers={"Authorization": "Bearer signed-session"}, json={
        "name": "Weekend", "wardrobe_item_ids": ["shirt-1", "trousers-1"],
    })
    assert response.status_code == 201, response.text
    sent = fake.calls[1][2]["json"]
    assert sent["owner_user_id"] == "signed-user-42"
    assert sent["outfit_id"]
    assert len(sent["pieces"]) == 2
    assert all(piece["slot_id"] for piece in sent["pieces"])
    assert "owner_user_id" not in response.request.content.decode(errors="ignore")


def test_saved_outfit_bff_lists_only_verified_subject_data(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"owner_user_id": "signed-user-42", "outfits": [{
            "outfit_id": "outfit-1", "owner_user_id": "signed-user-42",
            "name": "Weekend", "version": 1, "pieces": [],
        }]}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/wardrobe/outfits", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["outfits"][0]["name"] == "Weekend"
    assert fake.calls[1][2]["params"]["owner_user_id"] == "signed-user-42"


def test_saved_outfit_bff_rejects_cross_subject_payload(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"owner_user_id": "signed-user-42", "outfits": [{
            "outfit_id": "outfit-1", "owner_user_id": "different-user",
            "name": "Foreign", "pieces": [],
        }]}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/wardrobe/outfits", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "WARDROBE_OUTFIT_SCOPE_MISMATCH"


def test_saved_outfit_bff_replaces_only_selected_piece_and_forwards_version(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"outfit": {
            "outfit_id": "outfit-1", "owner_user_id": "signed-user-42",
            "name": "Weekend", "version": 2, "pieces": [],
        }, "status": "updated"}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.patch(
        "/api/wardrobe/outfits/outfit-1/pieces/top-slot",
        headers={"Authorization": "Bearer signed-session"},
        json={"expected_version": 1, "command_id": "replace-piece-001", "wardrobe_item_id": "shirt-2"},
    )
    assert response.status_code == 200, response.text
    assert fake.calls[1][0] == "PATCH"
    assert fake.calls[1][1] == "https://wardrobe.example.test/v1/outfits/outfit-1/pieces/top-slot"
    sent = fake.calls[1][2]["json"]
    assert sent["owner_user_id"] == "signed-user-42"
    assert sent["expected_version"] == 1
    assert sent["wardrobe_item_id"] == "shirt-2"


def test_wardrobe_page_exposes_saved_outfit_piece_editor(client):
    response = client.get("/wardrobe")
    assert response.status_code == 200
    assert 'id="outfitsPanel"' in response.text
    assert 'id="createOutfitForm"' in response.text
    assert 'fetch("/api/wardrobe/outfits"' in response.text or 'api("/api/wardrobe/outfits"' in response.text
    assert 'method:"PATCH"' in response.text
    assert "Other pieces were preserved." in response.text


def test_saved_outfit_bff_adds_piece_with_server_generated_slot(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"outfit": {
            "outfit_id": "outfit-1", "owner_user_id": "signed-user-42",
            "name": "Weekend", "version": 2, "pieces": [],
        }, "status": "updated"}, status_code=201),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/outfits/outfit-1/pieces",
        headers={"Authorization": "Bearer signed-session"},
        json={"expected_version": 1, "command_id": "add-piece-001", "wardrobe_item_id": "shoe-1"},
    )
    assert response.status_code == 201, response.text
    sent = fake.calls[1][2]["json"]
    assert sent["owner_user_id"] == "signed-user-42"
    assert sent["slot_id"]
    assert sent["wardrobe_item_id"] == "shoe-1"


def test_saved_outfit_bff_requires_explicit_replace_or_remove(client):
    response = client.patch(
        "/api/wardrobe/outfits/outfit-1/pieces/top-slot",
        headers={"Authorization": "Bearer signed-session"},
        json={"expected_version": 1, "command_id": "missing-piece-action"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "OUTFIT_PIECE_ACTION_REQUIRED"

def test_style_color_profile_bff_binds_verified_subject_and_reads_profile(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({
            "subject_id": "signed-user-42", "profile_version": 1,
            "liked_colors": ["emerald"], "disliked_colors": ["neon yellow"],
            "best_version_colors": ["burgundy"],
            "analysis": {"status": "unavailable", "reason_code": "NO_VALIDATED_COLOR_ANALYSIS_MODEL"},
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/style/color-profile", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["liked_colors"] == ["emerald"]
    assert fake.calls[1][1] == "https://identity.example.test/v1/color-profiles/signed-user-42"
    assert fake.calls[1][2]["headers"]["Authorization"] == "Bearer identity-internal-token-more-than-thirty-two-bytes"


def test_style_color_profile_bff_saves_only_for_verified_subject(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({
            "subject_id": "signed-user-42", "profile_version": 2,
            "liked_colors": ["emerald", "cobalt"], "disliked_colors": [],
            "best_version_colors": ["burgundy"],
            "analysis": {"status": "unavailable"},
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.put(
        "/api/style/color-profile",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "expected_version": 1, "liked_colors": ["emerald", "cobalt"],
            "disliked_colors": [], "best_version_colors": ["burgundy"],
        },
    )
    assert response.status_code == 200, response.text
    assert fake.calls[1][0] == "PUT"
    assert fake.calls[1][1] == "https://identity.example.test/v1/color-profiles/signed-user-42"
    assert fake.calls[1][2]["json"]["expected_version"] == 1
    assert "subject_id" not in fake.calls[1][2]["json"]
    assert "owner_user_id" not in response.request.content.decode(errors="ignore")


def test_wardrobe_page_exposes_personal_color_profile_and_analysis_boundary(client):
    response = client.get("/wardrobe")
    assert response.status_code == 200
    assert 'id="colorProfilePanel"' in response.text
    assert 'id="likedColors"' in response.text
    assert 'id="dislikedColors"' in response.text
    assert 'id="bestVersionColors"' in response.text
    assert 'api("/api/style/color-profile")' in response.text
    assert "NO_VALIDATED_COLOR_ANALYSIS_MODEL" not in response.text
    assert "Objective skin-tone and undertone analysis is not yet available" in response.text


def test_wardrobe_learning_export_combines_verified_tal_npl_feedback_and_rotation(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({
            "subject_id": "signed-user-42",
            "tal": {"events": [{"event_id": "tal-event-1"}]},
            "npl": {"user_id": "signed-user-42", "preferences": [{"preference_id": "avoid-blue"}]},
        }),
        FakeResponse({"owner_user_id": "signed-user-42", "items": [{"event_id": "wardrobe-event-1"}]}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": [
            {"owner_user_id": "signed-user-42", "item_id": "shirt-001", "status": "active"},
        ]}),
        FakeResponse({
            "state": {
                "owner_user_id": "signed-user-42", "cycle_number": 2,
                "cycle_started_at": "2026-11-07T00:00:00+00:00",
                "surfaced_item_ids": ["shirt-001"], "version": 4,
            },
            "version": 4,
        }),
        FakeResponse({"owner_user_id": "signed-user-42", "items": [
            {"event_id": "wear-001", "outfit_id": "outfit-001",
             "items": [{"item_id": "archived-shirt-001", "item_version": 1}],
             "context": {"occasion": "work"}, "observed_at": "2026-11-07T15:00:00+00:00"},
        ]}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/wardrobe/learning/export", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["subject_id"] == "signed-user-42"
    assert data["tal"]["events"][0]["event_id"] == "tal-event-1"
    assert data["npl"]["preferences"][0]["preference_id"] == "avoid-blue"
    assert data["wardrobe_feedback"][0]["event_id"] == "wardrobe-event-1"
    assert data["wardrobe_rotation"]["version"] == 4
    assert data["wardrobe_rotation"]["seen_item_ids"] == ["shirt-001"]
    assert data["wardrobe_wear_history"][0]["event_id"] == "wear-001"
    assert data["wardrobe_wear_history"][0]["items"][0]["item_id"] == "archived-shirt-001"
    assert fake.calls[1][1] == "https://decision.example.test/v1/me/learning/export"
    assert fake.calls[2][1] == "https://wardrobe.example.test/v1/feedback"
    assert fake.calls[3][1] == "https://wardrobe.example.test/v1/items"
    assert fake.calls[4][1] == "https://wardrobe.example.test/v1/rotation-state"
    assert fake.calls[5][1] == "https://wardrobe.example.test/v1/wear-history"



def test_wardrobe_learning_export_rejects_cross_subject_npl_payload(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({
            "subject_id": "signed-user-42",
            "tal": {"events": []},
            "npl": {"user_id": "another-user", "preferences": []},
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/wardrobe/learning/export", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LEARNING_EXPORT_SCOPE_MISMATCH"
    assert len(fake.calls) == 2

def test_wardrobe_preference_retraction_uses_gateway_verified_subject(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"preference": {"preference_id": "avoid-blue", "active": False}, "retracted": True}, status_code=200),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/preferences/avoid-blue/retract",
        headers={"Authorization": "Bearer signed-session"},
        json={"correction_event_id": "correction-123"},
    )
    assert response.status_code == 200, response.text
    assert fake.calls[1][1] == "https://decision.example.test/v1/me/npl/preferences/avoid-blue/retract"
    assert fake.calls[1][2]["json"] == {"correction_event_id": "correction-123"}
    assert fake.calls[1][2]["headers"]["X-End-User-Authorization"] == "Bearer signed-session"

def test_wardrobe_preference_retraction_rejects_client_subject_override(client, monkeypatch):
    response = client.post(
        "/api/wardrobe/preferences/avoid-blue/retract",
        headers={"Authorization": "Bearer signed-session"},
        json={"correction_event_id": "correction-123", "user_id": "another-user"},
    )
    assert response.status_code == 422

def test_wardrobe_learning_delete_erases_gateway_audit_and_rotation_state(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"status": "deleted", "tal": {}, "npl": {}}),
        FakeResponse({"status": "deleted", "deleted_feedback_events": 3}),
        FakeResponse({"status": "deleted", "owner_user_id": "signed-user-42"}),
        FakeResponse({"status": "deleted", "owner_user_id": "signed-user-42", "deleted_wear_events": 2}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.delete("/api/wardrobe/learning", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "deleted"
    assert result["identity_and_npl_deleted"] is True
    assert result["wardrobe_audit_deleted"] is True
    assert result["wardrobe_rotation_state_deleted"] is True
    assert result["wardrobe_wear_history_deleted"] is True
    assert result["deleted_wardrobe_feedback_events"] == 3
    assert result["deleted_wear_events"] == 2
    assert fake.calls[1][0] == "DELETE"
    assert fake.calls[1][1] == "https://decision.example.test/v1/me/learning/data"
    assert fake.calls[2][0] == "DELETE"
    assert fake.calls[2][2]["params"]["owner_user_id"] == "signed-user-42"
    assert fake.calls[3][0] == "DELETE"
    assert fake.calls[3][1] == "https://wardrobe.example.test/v1/rotation-state"
    assert fake.calls[3][2]["params"]["owner_user_id"] == "signed-user-42"
    assert fake.calls[4][1] == "https://wardrobe.example.test/v1/wear-history"
    assert fake.calls[4][2]["params"]["owner_user_id"] == "signed-user-42"



def test_wardrobe_learning_delete_reports_partial_erasure_without_deleting_local_audit(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"detail": {"code": "LEARNING_DELETION_PARTIAL"}}, status_code=503),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.delete("/api/wardrobe/learning", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "LEARNING_DELETION_PARTIAL"
    assert len(fake.calls) == 2

def test_wardrobe_learning_export_requires_signed_session(client):
    response = client.get("/api/wardrobe/learning/export")
    assert response.status_code == 401

def test_pnelly_daily_looks_uses_verified_wardrobe_and_gateway_subject(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")

    active_item = {
        "owner_user_id": "signed-user-42", "item_id": "shirt-001",
        "display_name": "Blue linen shirt", "category": "tops",
        "attributes": ["blue", "linen"], "status": "active",
        "image_asset_id": "private-asset-must-not-be-forwarded",
    }
    recommendation = {
        "look_count": 3,
        "looks": [
            {"role": role, "status": "needs_input", "item_ids": [], "items": [],
             "missing": ["a top and a bottom, or a one-piece outfit"],
             "virtual_twin_preview": {"status": "unavailable"}}
            for role in ("everyday", "elevated", "explore")
        ],
        "wardrobe_rotation": {
            "policy_version": "wardrobe-revival-v1",
            "cycle_complete": False,
            "cycle_overdue": False,
            "revival_queue_item_ids": ["shirt-001"],
            "next_state": {
                "cycle_number": 1,
                "cycle_started_at": "2026-11-07",
                "seen_item_ids": [],
            },
        },
    }
    gateway_response = FakeResponse({
        "schema_version": "1.0",
        "request_id": "will-be-uuid",
        "mode": "pnelly_wardrobe_daily_looks",
        "recommendation": recommendation,
    })
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": [active_item]}),
        FakeResponse({"state": None, "version": 0}),
        gateway_response,
        FakeResponse({
            "state": {
                "owner_user_id": "signed-user-42", "cycle_number": 1,
                "surfaced_item_ids": [], "version": 1,
            },
            "version": 1, "status": "created",
        }),
    ])

    original_post = fake.post
    async def post_with_rotation_date(url, **kwargs):
        if url == "https://decision.example.test/v1/pnelly/daily-looks":
            request_body = kwargs["json"]
            gateway_response._payload["request_id"] = request_body["request_id"]
            gateway_response._payload["recommendation"]["wardrobe_rotation"]["next_state"]["cycle_started_at"] = request_body["local_date"]
        return await original_post(url, **kwargs)

    fake.post = post_with_rotation_date
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/daily-looks",
        headers={"Authorization": "Bearer signed-session"},
        json={"occasion": "work", "climate": "hot_dry", "timezone": "Africa/Nairobi"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    gateway_call = fake.calls[3]
    assert gateway_call[1] == "https://decision.example.test/v1/pnelly/daily-looks"
    assert gateway_call[2]["headers"]["X-End-User-Authorization"] == "Bearer signed-session"
    sent_items = gateway_call[2]["json"]["wardrobe_items"]
    assert sent_items[0]["owner_user_id"] == "signed-user-42"
    assert "image_asset_id" not in sent_items[0]
    assert gateway_call[2]["json"]["occasion"] == "work"
    assert gateway_call[2]["json"]["climate"] == "hot_dry"
    assert gateway_call[2]["json"]["rotation_seen_item_ids"] == []
    assert gateway_call[2]["json"]["rotation_cycle_started_at"] is None
    assert gateway_call[2]["json"]["rotation_cycle_number"] == 1
    put_call = fake.calls[4]
    assert put_call[0] == "PUT"
    assert put_call[1] == "https://wardrobe.example.test/v1/rotation-state"
    assert put_call[2]["json"]["request_id"] == gateway_call[2]["json"]["request_id"]
    assert put_call[2]["json"]["expected_version"] == 0
    assert put_call[2]["json"]["surfaced_item_ids"] == []
    assert "DECISION_GATEWAY_TOKEN" not in response.text


def test_pnelly_daily_looks_rejects_cross_subject_wardrobe_data(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({
            "owner_user_id": "signed-user-42",
            "items": [{"owner_user_id": "another-user", "item_id": "foreign-001", "status": "active"}],
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/daily-looks",
        headers={"Authorization": "Bearer signed-session"},
        json={"timezone": "Africa/Nairobi"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "PNELLY_WARDROBE_SCOPE_MISMATCH"

def test_pnelly_daily_looks_rejects_gateway_response_with_missing_or_reordered_roles(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    malformed = {
        "mode": "pnelly_wardrobe_daily_looks",
        "recommendation": {
            "look_count": 3,
            "looks": [
                {"role": "everyday"},
                {"role": "explore"},
                {"role": "elevated"},
            ],
        },
    }
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": []}),
        FakeResponse({"state": None, "version": 0}),
        FakeResponse(malformed),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/daily-looks",
        headers={"Authorization": "Bearer signed-session"},
        json={"timezone": "Africa/Nairobi"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "PNELLY_RECOMMENDATION_SCHEMA_INVALID"

def test_pnelly_daily_looks_rejects_unverified_twin_preview_claims(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    forged_preview = {
        "mode": "pnelly_wardrobe_daily_looks",
        "recommendation": {
            "look_count": 3,
            "looks": [
                {
                    "role": role,
                    "status": "ready",
                    "items": [],
                    "virtual_twin_preview": {
                        "status": "available",
                        "output_asset_id": "unverified-render-asset-001",
                    },
                }
                for role in ("everyday", "elevated", "explore")
            ],
        },
    }
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": []}),
        FakeResponse({"state": None, "version": 0}),
        FakeResponse(forged_preview),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/daily-looks",
        headers={"Authorization": "Bearer signed-session"},
        json={"timezone": "Africa/Nairobi"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "PNELLY_RECOMMENDATION_SCHEMA_INVALID"

def test_legacy_daily_looks_bff_route_is_hidden_compatibility_alias(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/wardrobe/pnelly/daily-looks" in paths
    assert "/api/wardrobe/daily-looks" not in paths

def test_pnelly_daily_looks_hides_server_side_evaluation_trace_from_browser(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    item = {
        "owner_user_id": "signed-user-42", "item_id": "shirt-001",
        "display_name": "Blue linen shirt", "category": "tops",
        "attributes": ["blue", "linen"], "status": "active",
    }
    recommendation = {
        "look_count": 3,
        "looks": [
            {"role": role, "status": "needs_input", "item_ids": [], "items": [],
             "missing": ["a top and a bottom"], "virtual_twin_preview": {"status": "unavailable"}}
            for role in ["everyday", "elevated", "explore"]
        ],
        "evaluation_trace": {
            "trace_version": "1.0",
            "participant_key": "participant_do_not_expose",
            "cases": [{"case_id": "case_do_not_expose"}],
        },
        "wardrobe_rotation": {
            "policy_version": "wardrobe-revival-v1",
            "cycle_complete": False,
            "cycle_overdue": False,
            "revival_queue_item_ids": ["shirt-001"],
            "next_state": {"cycle_number": 1, "cycle_started_at": "2026-11-07", "seen_item_ids": []},
        },
    }
    gateway_response = FakeResponse({"mode": "pnelly_wardrobe_daily_looks", "recommendation": recommendation})
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": [item]}),
        FakeResponse({"state": None, "version": 0}),
        gateway_response,
        FakeResponse({
            "state": {"owner_user_id": "signed-user-42", "cycle_number": 1,
                      "surfaced_item_ids": [], "version": 1},
            "version": 1, "status": "created",
        }),
    ])
    original_post = fake.post
    async def post_with_gateway_envelope(url, **kwargs):
        response = await original_post(url, **kwargs)
        body = response.json()
        body["schema_version"] = "1.0"
        body["request_id"] = kwargs["json"]["request_id"]
        body["recommendation"]["wardrobe_rotation"]["next_state"]["cycle_started_at"] = kwargs["json"]["local_date"]
        return FakeResponse(body, status_code=response.status_code)
    fake.post = post_with_gateway_envelope
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/daily-looks",
        headers={"Authorization": "Bearer signed-session"},
        json={"occasion": "work", "timezone": "Africa/Nairobi"},
    )
    assert response.status_code == 200, response.text
    assert "evaluation_trace" not in response.json()["recommendation"]
    assert "participant_do_not_expose" not in response.text
    assert "case_do_not_expose" not in response.text





def test_pnelly_daily_looks_reloads_and_recomposes_after_rotation_compare_and_swap_conflict(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    items = [
        {"owner_user_id": "signed-user-42", "item_id": "shirt-001",
         "display_name": "Linen shirt", "category": "tops", "attributes": ["linen"], "status": "active"},
        {"owner_user_id": "signed-user-42", "item_id": "pants-001",
         "display_name": "Cotton trousers", "category": "trousers", "attributes": ["cotton"], "status": "active"},
    ]
    initial_state = {
        "state": {
            "owner_user_id": "signed-user-42", "cycle_number": 1,
            "cycle_started_at": "2026-11-07T00:00:00+00:00",
            "surfaced_item_ids": ["shirt-001"], "version": 1,
        },
        "version": 1,
    }
    refreshed_state = {
        "state": {
            "owner_user_id": "signed-user-42", "cycle_number": 1,
            "cycle_started_at": "2026-11-07T00:00:00+00:00",
            "surfaced_item_ids": ["shirt-001", "pants-001"], "version": 2,
        },
        "version": 2,
    }
    roles = ["everyday", "elevated", "explore"]
    def recommendation(*, complete, cycle, start, seen, queue):
        return {
            "look_count": 3,
            "looks": [
                {"role": role, "status": "needs_input", "item_ids": [], "items": [],
                 "missing": ["a complete outfit"], "virtual_twin_preview": {"status": "unavailable"}}
                for role in roles
            ],
            "wardrobe_rotation": {
                "policy_version": "wardrobe-revival-v1",
                "cycle_complete": complete, "cycle_overdue": False,
                "revival_queue_item_ids": queue,
                "next_state": {
                    "cycle_number": cycle, "cycle_started_at": start,
                    "seen_item_ids": seen,
                },
            },
        }
    first_gateway = FakeResponse({
        "mode": "pnelly_wardrobe_daily_looks",
        "recommendation": recommendation(
            complete=False, cycle=1, start="2026-11-07", seen=["shirt-001"], queue=["pants-001"],
        ),
    })
    second_gateway = FakeResponse({
        "mode": "pnelly_wardrobe_daily_looks",
        "recommendation": recommendation(
            complete=True, cycle=2, start="2026-11-07", seen=[], queue=[],
        ),
    })
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": items}),
        FakeResponse(initial_state),
        first_gateway,
        FakeResponse({"detail": {"code": "WARDROBE_ROTATION_VERSION_CONFLICT"}}, status_code=409),
        FakeResponse(refreshed_state),
        second_gateway,
        FakeResponse({
            "state": {
                "owner_user_id": "signed-user-42", "cycle_number": 2,
                "cycle_started_at": "2026-11-07T00:00:00+00:00",
                "surfaced_item_ids": [], "version": 3,
            },
            "version": 3, "status": "updated",
        }),
    ])
    original_post = fake.post
    gateway_request_snapshots = []
    async def echo_local_dates(url, **kwargs):
        if url == "https://decision.example.test/v1/pnelly/daily-looks":
            import copy
            gateway_request_snapshots.append(copy.deepcopy(kwargs["json"]))
        response = await original_post(url, **kwargs)
        if url == "https://decision.example.test/v1/pnelly/daily-looks":
            body = kwargs["json"]
            response._payload["request_id"] = body["request_id"]
            rotation = response._payload["recommendation"]["wardrobe_rotation"]
            if rotation["cycle_complete"]:
                rotation["next_state"]["cycle_started_at"] = body["local_date"]
            else:
                rotation["next_state"]["cycle_started_at"] = body["rotation_cycle_started_at"]
        return response
    fake.post = echo_local_dates
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/daily-looks",
        headers={"Authorization": "Bearer signed-session"},
        json={"timezone": "Africa/Nairobi"},
    )
    assert response.status_code == 200, response.text
    gateway_calls = [call for call in fake.calls if call[0] == "POST"]
    rotation_writes = [call for call in fake.calls if call[0] == "PUT"]
    assert len(gateway_calls) == 2
    assert len(rotation_writes) == 2
    assert gateway_request_snapshots[0]["rotation_seen_item_ids"] == ["shirt-001"]
    assert gateway_request_snapshots[1]["rotation_seen_item_ids"] == ["shirt-001", "pants-001"]
    assert gateway_request_snapshots[1]["rotation_cycle_number"] == 1
    assert rotation_writes[0][2]["json"]["expected_version"] == 1
    assert rotation_writes[1][2]["json"]["expected_version"] == 2
    assert rotation_writes[1][2]["json"]["cycle_number"] == 2
    assert rotation_writes[1][2]["json"]["surfaced_item_ids"] == []





def test_pnelly_mark_worn_creates_stable_owned_outfit_and_records_factual_wear(client, monkeypatch):
    import uuid
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    event_id = "wear-event-frontend-001"
    outfit_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cirvanna:pnelly-wear:signed-user-42:{event_id}"))
    items = [
        {"owner_user_id": "signed-user-42", "item_id": "shirt-001",
         "display_name": "Linen shirt", "category": "tops", "attributes": ["linen"], "status": "active"},
        {"owner_user_id": "signed-user-42", "item_id": "pants-001",
         "display_name": "Cotton trousers", "category": "trousers", "attributes": ["cotton"], "status": "active"},
    ]
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": items}),
        FakeResponse({
            "outfit": {
                "owner_user_id": "signed-user-42", "outfit_id": outfit_id,
                "version": 1, "pieces": [
                    {"wardrobe_item_id": "shirt-001"}, {"wardrobe_item_id": "pants-001"},
                ],
            },
            "status": "created",
        }, status_code=201),
        FakeResponse({
            "status": "recorded", "event_id": event_id, "outfit_id": outfit_id,
            "outfit_version": 1,
            "items": [
                {"item_id": "shirt-001", "item_version": 1},
                {"item_id": "pants-001", "item_version": 1},
            ],
            "delivery": [{"item_id": "shirt-001"}, {"item_id": "pants-001"}],
        }, status_code=201),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/looks/wear",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "item_ids": ["shirt-001", "pants-001"], "event_id": event_id,
            "consent_receipt_id": "active-style-receipt",
            "observed_at": "2026-11-07T18:00:00+03:00",
            "name": "PNELLY Everyday 2026-11-07",
            "context": {"occasion": "work"},
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["event_id"] == event_id
    assert response.json()["items"][0]["item_id"] == "shirt-001"
    assert fake.calls[0][1] == "https://commerce.example.test/me"
    assert fake.calls[1][2]["params"]["owner_user_id"] == "signed-user-42"
    create_body = fake.calls[2][2]["json"]
    assert create_body["owner_user_id"] == "signed-user-42"
    assert create_body["outfit_id"] == outfit_id
    assert [piece["wardrobe_item_id"] for piece in create_body["pieces"]] == ["shirt-001", "pants-001"]
    wear_call = fake.calls[3]
    assert wear_call[1] == "https://wardrobe.example.test/v1/outfits/" + outfit_id + "/wear"
    assert wear_call[2]["json"]["owner_user_id"] == "signed-user-42"
    assert wear_call[2]["json"]["event_id"] == event_id
    assert wear_call[2]["json"]["expected_outfit_version"] == 1





def test_pnelly_mark_worn_retries_after_outfit_creation_without_duplicate_events(client, monkeypatch):
    import uuid
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    event_id = "wear-event-retry-001"
    outfit_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cirvanna:pnelly-wear:signed-user-42:{event_id}"))
    existing = {
        "owner_user_id": "signed-user-42", "outfit_id": outfit_id, "version": 1,
        "pieces": [{"slot_id": "top", "wardrobe_item_id": "shirt-001"}],
    }
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": [
            {"owner_user_id": "signed-user-42", "item_id": "shirt-001",
             "display_name": "Linen shirt", "category": "tops", "attributes": ["linen"], "status": "active"},
        ]}),
        FakeResponse({"detail": {"code": "WARDROBE_OUTFIT_STORE_UNAVAILABLE"}}, status_code=503),
        FakeResponse({"owner_user_id": "signed-user-42", "outfits": [existing]}),
        FakeResponse({
            "status": "replayed", "event_id": event_id, "outfit_id": outfit_id,
            "items": [{"item_id": "shirt-001", "item_version": 1}], "delivery": [],
        }, status_code=201),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/looks/wear",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "item_ids": ["shirt-001"], "event_id": event_id,
            "consent_receipt_id": "active-style-receipt",
            "observed_at": "2026-11-07T18:00:00+03:00",
            "name": "PNELLY Everyday", "context": {"occasion": "work"},
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "replayed"
    assert fake.calls[2][0] == "POST"
    assert fake.calls[3][0] == "GET"
    assert fake.calls[3][1] == "https://wardrobe.example.test/v1/outfits"
    assert fake.calls[4][1] == "https://wardrobe.example.test/v1/outfits/" + outfit_id + "/wear"


def test_pnelly_mark_worn_rejects_another_users_wardrobe_item(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": [
            {"owner_user_id": "another-user", "item_id": "foreign-shirt",
             "display_name": "Foreign shirt", "category": "tops", "attributes": [], "status": "active"},
        ]}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/looks/wear",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "item_ids": ["foreign-shirt"], "event_id": "wear-cross-user-001",
            "consent_receipt_id": "active-style-receipt",
            "observed_at": "2026-11-07T18:00:00+03:00",
            "name": "PNELLY work", "context": {},
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PNELLY_WEAR_ITEM_NOT_ACTIVE_OR_NOT_OWNED"
    assert len(fake.calls) == 2





def test_wardrobe_category_bff_uses_verified_session_and_validates_taxonomy(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({
            "taxonomy_version": "1.0.0",
            "categories": [
                {"id": "shoes", "label": "Shoes and footwear", "group": "footwear"},
                {"id": "makeup", "label": "Makeup", "group": "beauty"},
            ],
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/wardrobe/categories", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["taxonomy_version"] == "1.0.0"
    assert {item["id"] for item in response.json()["categories"]} == {"shoes", "makeup"}
    assert fake.calls[1][1] == "https://wardrobe.example.test/v1/categories"


def test_wardrobe_category_bff_rejects_malformed_upstream_taxonomy(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"taxonomy_version": "1.0.0", "categories": [{"id": "shoes"}]}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/wardrobe/categories", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "WARDROBE_CATEGORY_RESPONSE_INVALID"



def test_wardrobe_try_on_derives_subject_and_uses_exact_owned_private_garment(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("VIRTUAL_TRY_ON_API_URL", "https://tryon.example.test")
    monkeypatch.setenv("VIRTUAL_TRY_ON_API_TOKEN", "virtual-try-on-internal-token-more-than-32-bytes")
    garment_asset = "6e7a22a4-2f3b-4fb7-86a2-4a0e83dcf26d"
    output_asset = "7e7a22a4-2f3b-4fb7-86a2-4a0e83dcf26d"
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"item": {
            "owner_user_id": "signed-user-42", "item_id": "closet-item-1",
            "status": "active", "category": "dress", "image_asset_id": garment_asset,
            "image_storage_consent": True,
        }}),
        FakeResponse({
            "request_id": "request-tryon-1234", "status": "complete",
            "output_asset_id": output_asset, "renderer_id": "fashn-vton-1.5",
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/items/closet-item-1/try-on",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "wardrobe_item_id": "closet-item-1",
            "twin_id": "persistent-twin-42",
            "person_image_asset_id": "5e7a22a4-2f3b-4fb7-86a2-4a0e83dcf26d",
            "consent_id": "consent-receipt-1234",
            "consent_image_processing": True,
            "consent_virtual_try_on": True,
            "request_id": "request-tryon-1234",
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["output_asset_id"] == output_asset
    assert [call[0] for call in fake.calls] == ["GET", "GET", "POST"]
    assert fake.calls[1][2]["params"]["owner_user_id"] == "signed-user-42"
    forwarded = fake.calls[2][2]["json"]
    assert forwarded["subject_id"] == "signed-user-42"
    assert forwarded["product_id"] == "wardrobe:closet-item-1"
    assert forwarded["garment_image_asset_id"] == garment_asset
    assert forwarded["garment_asset_purpose"] == "wardrobe_garment_image"
    assert forwarded["garment_asset_parent_id"] == "closet-item-1"
    assert forwarded["garment_category"] == "dress"
    assert forwarded["consent"]["retention_policy"] == "ephemeral"


def test_wardrobe_try_on_rejects_cross_subject_item_before_renderer_call(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("VIRTUAL_TRY_ON_API_URL", "https://tryon.example.test")
    monkeypatch.setenv("VIRTUAL_TRY_ON_API_TOKEN", "virtual-try-on-internal-token-more-than-32-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"item": {
            "owner_user_id": "another-user", "item_id": "foreign-item",
            "status": "active", "category": "dress",
            "image_asset_id": "6e7a22a4-2f3b-4fb7-86a2-4a0e83dcf26d",
            "image_storage_consent": True,
        }}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/items/foreign-item/try-on",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "wardrobe_item_id": "foreign-item", "twin_id": "persistent-twin-42",
            "person_image_asset_id": "5e7a22a4-2f3b-4fb7-86a2-4a0e83dcf26d",
            "consent_id": "consent-receipt-1234",
            "consent_image_processing": True, "consent_virtual_try_on": True,
        },
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "WARDROBE_ITEM_SCOPE_MISMATCH"
    assert len(fake.calls) == 2


def test_wardrobe_try_on_requires_both_explicit_consent_flags_before_upstream(client, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Try-on must reject missing consent before contacting any provider")
    monkeypatch.setattr(main.httpx, "AsyncClient", forbidden)
    response = client.post(
        "/api/wardrobe/items/closet-item-1/try-on",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "wardrobe_item_id": "closet-item-1", "twin_id": "persistent-twin-42",
            "person_image_asset_id": "5e7a22a4-2f3b-4fb7-86a2-4a0e83dcf26d",
            "consent_id": "consent-receipt-1234",
            "consent_image_processing": False, "consent_virtual_try_on": True,
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "TRY_ON_CONSENT_REQUIRED"


def test_virtual_twin_capabilities_are_authenticated_minimal_and_no_store(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("VIRTUAL_TWIN_API_URL", "https://twin.example.test")
    source = {
        "twin_generation": False, "persistent_twin_generation": False,
        "persistent_twin_preview": False, "pose_skeleton_inference": True,
        "body_reconstruction": False, "full_surface_mesh": False,
        "calibrated_body_measurements": False, "fit_prediction": False,
        "ar_rendering": False, "image_persistence": False,
        "click_it_twin_personalization": False,
        "reason": "vision_worker_not_ready", "private_internal_url": "https://secret",
    }
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse(source),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get(
        "/api/virtual-twin/capabilities",
        headers={"Authorization": "Bearer signed-session"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    body = response.json()
    assert body["persistent_twin_generation"] is False
    assert body["persistent_twin_preview"] is False
    assert body["pose_skeleton_inference"] is True
    assert body["try_on_available"] is False
    assert "private_internal_url" not in body
    assert len(fake.calls) == 2
    assert fake.calls[1][0] == "GET"
    assert fake.calls[1][1] == "https://twin.example.test/capabilities"


def test_virtual_twin_capabilities_reject_invalid_boolean_contract(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("VIRTUAL_TWIN_API_URL", "https://twin.example.test")
    source = {
        "persistent_twin_generation": "false", "persistent_twin_preview": False,
        "pose_skeleton_inference": False, "body_reconstruction": False,
        "full_surface_mesh": False, "calibrated_body_measurements": False,
        "fit_prediction": False, "ar_rendering": False, "image_persistence": False,
        "click_it_twin_personalization": False,
    }
    fake = FakeAsyncClient([FakeResponse({"user_id": "signed-user-42"}), FakeResponse(source)])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get(
        "/api/virtual-twin/capabilities",
        headers={"Authorization": "Bearer signed-session"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "VIRTUAL_TWIN_CAPABILITIES_INVALID"


def test_brand_and_founder_portals_are_served_same_origin(client):
    brand = client.get("/brand-portal")
    founder = client.get("/founder-console")
    css = client.get("/assets/portal.css")
    brand_js = client.get("/assets/brand-portal.js")
    assert brand.status_code == founder.status_code == css.status_code == brand_js.status_code == 200
    assert brand.headers["cache-control"] == "no-store"
    assert founder.headers["cache-control"] == "no-store"
    assert "Brand Partner Portal" in brand.text
    assert "Founder console" in founder.text
    assert "/merchant/listings" in brand_js.text
    assert "localStorage" not in brand_js.text
    assert "sessionStorage" not in brand_js.text


def test_commerce_proxy_allowlist_routes_role_based_operations():
    allowed = [
        ("GET", "me"), ("POST", "merchants/applications"), ("GET", "merchants/me"),
        ("GET", "merchants/me/markets"), ("POST", "merchant/markets"),
        ("GET", "merchant/listings"), ("GET", "merchant/orders"), ("POST", "merchant/listings"),
        ("POST", "merchant/listings/123e4567-e89b-12d3-a456-426614174000/variants"),
        ("POST", "merchant/variants/123e4567-e89b-12d3-a456-426614174000/inventory-adjustments"),
        ("GET", "admin/merchants"), ("GET", "admin/merchant-decisions"),
        ("POST", "admin/merchants/123e4567-e89b-12d3-a456-426614174000/decision"),
        ("GET", "admin/merchants/123e4567-e89b-12d3-a456-426614174000/markets"),
        ("PUT", "admin/merchants/123e4567-e89b-12d3-a456-426614174000/markets/KE"),
    ]
    for method, route in allowed:
        assert main._authorized_commerce_path(method, route), (method, route)
    blocked = [
        ("POST", "admin/merchants"), ("POST", "webhooks/stripe"),
        ("POST", "internal/expire-reservations"),
        ("POST", "merchant/listings/not-a-uuid/variants"),
        ("DELETE", "admin/merchant-decisions"),
        ("PUT", "admin/merchants/123e4567-e89b-12d3-a456-426614174000/markets/not-a-country"),
        ("POST", "admin/merchants/123e4567-e89b-12d3-a456-426614174000/markets"),
    ]
    for method, route in blocked:
        assert not main._authorized_commerce_path(method, route), (method, route)


def test_marketplace_comparison_route_is_registered_once():
    matching = [
        route for route in main.app.routes
        if getattr(route, "path", None) == "/api/commerce/marketplace/compare"
    ]
    assert len(matching) == 1






def test_offer_comparison_fails_closed_without_candidate_bound_cal_receipt(client, monkeypatch):
    configure_upstreams(monkeypatch)
    calls = []
    monkeypatch.setattr(main.httpx, "post", lambda *args, **kwargs: calls.append((args, kwargs)))
    response = client.post("/api/commerce/marketplace/compare", json={
        "variant_ids": [
            "11111111-1111-4111-8111-111111111111",
            "22222222-2222-4222-8222-222222222222",
        ],
        "destination_country_code": "KE",
        "destination_key": "Nakuru/Subukia",
        "fulfillment_mode": "courier_delivery",
        "display_currency": "KES",
        "payment_method": "card",
        "radius_km": 75,
    })
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CAL_AUTHORIZATION_REQUIRED"
    assert "comparison" not in response.json()
    assert calls == []


def test_offer_comparison_never_contacts_commerce_without_cal_authorization(client, monkeypatch):
    configure_upstreams(monkeypatch)
    calls = []
    monkeypatch.setattr(main.httpx, "post", lambda *args, **kwargs: calls.append(args))
    response = client.post("/api/commerce/marketplace/compare", json={
        "variant_ids": ["not-a-uuid", "also-not-a-uuid"],
        "destination_country_code": "KE",
        "destination_key": "Nakuru",
        "fulfillment_mode": "collection",
        "display_currency": "KES",
    })
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CAL_AUTHORIZATION_REQUIRED"
    assert calls == []

class LookItLifecycleClient:
    def __init__(self, *, fail_scope=None, fail_revoke=False):
        self.calls = []
        self.receipts = []
        self.fail_scope = fail_scope
        self.fail_revoke = fail_revoke

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url == "https://identity.example.test/v1/tal/consents":
            body = kwargs["json"]
            if body["scope"] == self.fail_scope:
                return FakeResponse({"detail": {"code": "CONSENT_WRITE_FAILED"}}, status_code=503)
            self.receipts.append(body)
            return FakeResponse({
                "receipt_id": body["receipt_id"],
                "consent_id": body["consent_id"],
                "resource_id": body["resource_id"],
                "granted": True,
                "expires_at": body["expires_at"],
            })
        if url == "https://identity.example.test/internal/v1/consents/verify":
            body = kwargs["json"]
            assert body["subject_id"] == "verified-customer-01"
            assert {item["scope"] for item in self.receipts} == {"image_processing", "look_it"}
            return FakeResponse({
                "verified": True, "active": True,
                "subject_id": body["subject_id"],
                "consent_id": body["consent_id"],
                "resource_id": body["resource_id"],
                "consent_version": body["consent_version"],
                "expires_at": self.receipts[0]["expires_at"],
                "granted_scopes": ["image_processing", "look_it"],
            })
        if url == "https://pnelly.example.test/v1/marketplace/search/image":
            fields = kwargs["data"]
            assert fields["subject_id"] == "verified-customer-01"
            assert fields["consent_id"] == self.receipts[0]["consent_id"]
            assert fields["resource_id"] == self.receipts[0]["resource_id"]
            assert kwargs["files"]["image"][1] == b"private-outfit-reference"
            return FakeResponse({
                "status": "complete",
                "candidate_count": 2,
                "display_authorized": False,
                "decision_status": "PENDING_CAL",
                "image_persisted": False,
                "outfit_decomposition": {
                    "status": "unavailable",
                    "reason": "VALIDATED_OUTFIT_DECOMPOSITION_PROVIDER_NOT_CONFIGURED",
                    "components": [],
                },
                "merchant_comparison": {"status": "pending_cal"},
            })
        if url.startswith("https://identity.example.test/v1/tal/consents/") and url.endswith("/revoke"):
            return FakeResponse({"status": "revoked"}, status_code=503 if self.fail_revoke else 200)
        pytest.fail("Unexpected Look It upstream URL: " + url)


def _configure_look_it_bff(monkeypatch, fake):
    async def verified_subject(_client, _request):
        return "verified-customer-01", "signed-user-session-token"

    monkeypatch.setattr(main, "_verified_commerce_subject", verified_subject)
    monkeypatch.setattr(main, "_identity_learning_service", lambda: (
        "https://identity.example.test", "identity-service-token-with-at-least-32-bytes"
    ))
    monkeypatch.setattr(main, "_pnelly_internal_service", lambda: (
        "https://pnelly.example.test", "pnelly-service-token-with-at-least-32-bytes"
    ))
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **_kwargs: fake)


def test_look_it_records_verifies_and_revokes_request_scoped_consent(client, monkeypatch):
    fake = LookItLifecycleClient()
    _configure_look_it_bff(monkeypatch, fake)
    response = client.post(
        "/api/vision/look-it",
        headers={"Authorization": "Bearer signed-user-session-token"},
        data={"consent_image_processing": "true", "consent_look_it": "true"},
        files={"reference_image": ("outfit.png", b"private-outfit-reference", "image/png")},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["candidate_count"] == 2
    assert data["display_authorized"] is False
    assert data["decision_status"] == "PENDING_CAL"
    assert data["image_persisted"] is False
    assert data["outfit_decomposition"]["status"] == "unavailable"
    assert response.headers["cache-control"] == "no-store, private"
    assert len(fake.receipts) == 2
    assert {row["scope"] for row in fake.receipts} == {"image_processing", "look_it"}
    assert len({row["consent_id"] for row in fake.receipts}) == 1
    assert len({row["resource_id"] for row in fake.receipts}) == 1
    assert all(row["expires_at"] for row in fake.receipts)
    assert any(url.endswith("/internal/v1/consents/verify") for _method, url, _kwargs in fake.calls)
    assert any(url.endswith("/revoke") for _method, url, _kwargs in fake.calls)
    for forbidden in ("variant_id", "product_name", "price_minor", "merchant_id", "image_urls"):
        assert forbidden not in response.text


def test_look_it_revokes_partial_consent_write_before_returning_failure(client, monkeypatch):
    fake = LookItLifecycleClient(fail_scope="look_it")
    _configure_look_it_bff(monkeypatch, fake)
    response = client.post(
        "/api/vision/look-it",
        headers={"Authorization": "Bearer signed-user-session-token"},
        data={"consent_image_processing": "true", "consent_look_it": "true"},
        files={"reference_image": ("outfit.png", b"private-outfit-reference", "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "LOOK_IT_CONSENT_WRITE_FAILED"
    assert len(fake.receipts) == 1
    assert not any(url == "https://pnelly.example.test/v1/marketplace/search/image" for _m, url, _k in fake.calls)
    assert any(url.endswith("/revoke") for _m, url, _k in fake.calls)


def test_look_it_suppresses_results_when_consent_revocation_fails(client, monkeypatch):
    fake = LookItLifecycleClient(fail_revoke=True)
    _configure_look_it_bff(monkeypatch, fake)
    response = client.post(
        "/api/vision/look-it",
        headers={"Authorization": "Bearer signed-user-session-token"},
        data={"consent_image_processing": "true", "consent_look_it": "true"},
        files={"reference_image": ("outfit.png", b"private-outfit-reference", "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "LOOK_IT_CONSENT_REVOCATION_FAILED"
    assert "candidate_count" not in response.text


def test_look_it_authenticates_before_multipart_parser(client, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Unauthenticated Look It must reject before parsing multipart bytes")
    monkeypatch.setattr(Request, "form", forbidden)
    monkeypatch.setattr(Request, "body", forbidden)
    monkeypatch.setattr(Request, "stream", forbidden)
    response = client.post(
        "/api/vision/look-it",
        data={"consent_image_processing": "true", "consent_look_it": "true"},
        files={"reference_image": ("outfit.png", b"private-outfit-reference", "image/png")},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "USER_BEARER_REQUIRED"


def test_look_it_requires_both_consents_before_identity_consent_or_pnelly_calls(client, monkeypatch):
    async def verified_subject(_client, _request):
        return "verified-customer-01", "signed-user-session-token"
    def forbidden(*_args, **_kwargs):
        pytest.fail("Look It must reject before contacting consent or PNELLY services")
    monkeypatch.setattr(main, "_verified_commerce_subject", verified_subject)
    monkeypatch.setattr(main, "_identity_learning_service", forbidden)
    monkeypatch.setattr(main, "_pnelly_internal_service", forbidden)
    response = client.post(
        "/api/vision/look-it",
        headers={"Authorization": "Bearer signed-user-session-token"},
        data={"consent_image_processing": "true", "consent_look_it": "false"},
        files={"reference_image": ("outfit.png", b"private-outfit-reference", "image/png")},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "EXPLICIT_LOOK_IT_CONSENT_REQUIRED"


def test_wardrobe_recommendations_reject_candidate_id_mismatch_before_display(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({
            "request_id": "req-mismatch",
            "ranked_candidate_count": 1,
            "displayable_products": [{
                "product": {"product_id": "product-1", "catalog_version": 3},
                "offer": {"catalog_product_id": "different-product", "variant_id": "variant-1"},
                "decision": {"product_id": "product-1", "catalog_version": 3,
                             "verdict": "show", "may_display": True},
                "cil_serving_assessment": {"status": "eligible", "assessed_catalog_version": 3},
            }],
            "withheld_candidate_ids": [],
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/recommendations",
        headers={"Authorization": "Bearer signed-session"},
        json={"query": "linen layer for a blue shirt"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "WARDROBE_CANDIDATE_CAL_CIL_AUTHORIZATION_INVALID"


def test_complementer_bff_uses_verified_subject_and_returns_advisory_only(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-customer-42", "role": "customer"}),
        FakeResponse({
            "mode": "advisory_only",
            "display_authorized": False,
            "durable_personal_memory": False,
            "recommendation": {"summary": "Try softer contrast and a structured layer."},
            "candidates": [{"product_name": "must not escape"}],
            "merchant_name": "must not escape",
            "price_minor": 999,
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/vision/complementer",
        headers={"Authorization": "Bearer signed-customer-session"},
        json={
            "request_id": "complementer-test-001",
            "preferences": {"style": "minimal"},
            "look": {"description": "navy trousers and cream knit"},
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data == {
        "mode": "advisory_only",
        "display_authorized": False,
        "durable_personal_memory": False,
        "recommendation": {"summary": "Try softer contrast and a structured layer."},
    }
    assert response.headers["cache-control"] == "no-store, private"
    assert "must not escape" not in response.text
    assert "merchant_name" not in response.text
    assert "price_minor" not in response.text
    assert fake.calls[0][0] == "GET"
    assert fake.calls[0][1] == "https://commerce.example.test/me"
    assert fake.calls[1][0] == "POST"
    assert fake.calls[1][1] == "https://decision.example.test/v1/complementer/recommend"
    assert fake.calls[1][2]["headers"]["X-End-User-Authorization"] == "Bearer signed-customer-session"
    assert fake.calls[1][2]["json"]["user_id"] == "verified-customer-42"


def test_complementer_requires_authenticated_user_before_upstream_calls(client, monkeypatch):
    class ForbiddenAsyncClient:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def get(self, *args, **kwargs):
            pytest.fail("Missing user bearer must be rejected before Commerce identity lookup")

    monkeypatch.setattr(main.httpx, "AsyncClient", ForbiddenAsyncClient)
    response = client.post(
        "/api/vision/complementer",
        json={"request_id": "complementer-test-002", "look": {"description": "blue shirt"}},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "USER_BEARER_REQUIRED"



def test_complementer_feedback_writes_only_consented_minimal_event_to_verified_tal(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-customer-42", "role": "customer"}),
        FakeResponse({
            "status": "recorded",
            "event_id": "feedback-event-001",
            "durable_persistence": True,
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/vision/complementer/feedback",
        headers={"Authorization": "Bearer signed-customer-session"},
        json={
            "feedback_id": "feedback-event-001",
            "request_id": "complementer-request-001",
            "outcome": "rejected",
            "consent_receipt_id": "personalization-consent-001",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "recorded",
        "feedback_id": "feedback-event-001",
        "durable_persistence": True,
        "learning_owner": "TAL",
    }
    assert fake.calls[0][0] == "GET"
    assert fake.calls[0][1] == "https://commerce.example.test/me"
    assert fake.calls[1][0] == "POST"
    assert fake.calls[1][1] == "https://decision.example.test/v1/me/tal/events"
    sent = fake.calls[1][2]
    assert sent["headers"]["X-End-User-Authorization"] == "Bearer signed-customer-session"
    assert sent["json"]["event_id"] == "feedback-event-001"
    assert sent["json"]["idempotency_key"] == "feedback-event-001"
    assert sent["json"]["consent_receipt_id"] == "personalization-consent-001"
    assert sent["json"]["feature_key"] == "complementer.recommendation_feedback"
    assert json.loads(sent["json"]["value"]) == {
        "request_id": "complementer-request-001",
        "outcome": "rejected",
    }
    assert "navy trousers" not in response.text
    assert response.headers["cache-control"] == "no-store, private"


def test_complementer_feedback_requires_authenticated_user(client, monkeypatch):
    class ForbiddenAsyncClient:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def get(self, *args, **kwargs):
            pytest.fail("Feedback must reject before Commerce identity lookup without a bearer")

    monkeypatch.setattr(main.httpx, "AsyncClient", ForbiddenAsyncClient)
    response = client.post(
        "/api/vision/complementer/feedback",
        json={
            "feedback_id": "feedback-event-002",
            "request_id": "complementer-request-002",
            "outcome": "approved",
            "consent_receipt_id": "personalization-consent-002",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "USER_BEARER_REQUIRED"


def test_complementer_feedback_does_not_claim_persistence_on_upstream_rejection(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-customer-42", "role": "customer"}),
        FakeResponse({"detail": {"code": "ACTIVE_TAL_CONSENT_REQUIRED"}}, status_code=403),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/vision/complementer/feedback",
        headers={"Authorization": "Bearer signed-customer-session"},
        json={
            "feedback_id": "feedback-event-003",
            "request_id": "complementer-request-003",
            "outcome": "approved",
            "consent_receipt_id": "revoked-consent-003",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ACTIVE_TAL_CONSENT_REQUIRED"
