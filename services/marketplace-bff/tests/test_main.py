import json

import pytest
from fastapi.testclient import TestClient

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


def test_page_bootstraps_same_origin_live_offers_not_demo_data(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'window.CIRVANNA_MARKETPLACE_CONFIG = Object.freeze({publicOffersBase:"/api/commerce"});' in response.text
    assert "bootstrap.publicOffersBase" in response.text
    assert "connect-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_public_offers_are_proxied_without_exposing_catalog_credentials(client, monkeypatch):
    configure_upstreams(monkeypatch)
    seen = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return FakeResponse({"items": [{"variant_id": "v1", "image_urls": ["https://cdn.example.test/unmasked.jpg"], "product": {"image_urls": ["https://cdn.example.test/nested.jpg"]}}], "total": 1, "offset": 0, "limit": 20})

    monkeypatch.setattr(main.httpx, "get", fake_get)
    response = client.get("/api/commerce/marketplace/offers?q=linen&category=Fashion&offset=20&limit=10")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["image_urls"] == []
    assert response.json()["items"][0]["product"]["image_urls"] == []
    assert seen["url"] == "https://commerce.example.test/marketplace/offers"
    assert seen["params"] == {"offset": 20, "limit": 10, "q": "linen", "category": "Fashion"}
    assert "Authorization" not in seen["headers"]
    assert "catalog-server-only-test-token" not in response.text


def test_account_proxy_requires_bearer_and_blocks_admin_routes(client, monkeypatch):
    configure_upstreams(monkeypatch)
    calls = []
    monkeypatch.setattr(main.httpx, "request", lambda *args, **kwargs: calls.append(args) or FakeResponse({}))
    assert client.get("/api/commerce/cart").status_code == 401
    denied = client.get("/api/commerce/admin/inventory/audit", headers={"Authorization": "Bearer customer-token"})
    assert denied.status_code == 404
    assert calls == []


def test_account_proxy_forwards_only_allowlisted_headers_and_bearer(client, monkeypatch):
    configure_upstreams(monkeypatch)
    seen = {}

    def fake_request(method, url, **kwargs):
        seen["method"] = method
        seen["url"] = url
        seen.update(kwargs)
        return FakeResponse({"order_id": "order-123"}, status_code=201)

    monkeypatch.setattr(main.httpx, "request", fake_request)
    response = client.post(
        "/api/commerce/checkout",
        headers={
            "Authorization": "Bearer user-session-token",
            "Content-Type": "application/json",
            "Idempotency-Key": "checkout-test-key",
            "Cookie": "untrusted=not-forwarded",
        },
        json={"confirm": True},
    )
    assert response.status_code == 201
    assert seen["method"] == "POST"
    assert seen["url"] == "https://commerce.example.test/checkout"
    assert seen["headers"]["Authorization"] == "Bearer user-session-token"
    assert seen["headers"]["idempotency-key"] == "checkout-test-key"
    assert "cookie" not in seen["headers"]
    assert "follow_redirects" in seen and seen["follow_redirects"] is False


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


def test_external_upstream_must_use_https(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "http://commerce.example.test")
    response = client.get("/api/commerce/marketplace/offers")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "COMMERCE_API_URL_MUST_BE_TRUSTED_HTTPS"

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


def test_description_search_fails_closed_without_xari_or_legacy_secret(client, monkeypatch):
    monkeypatch.delenv("TARI_API_URL", raising=False)
    monkeypatch.delenv("TARI_API_TOKEN", raising=False)
    monkeypatch.delenv("XARI_API_URL", raising=False)
    monkeypatch.delenv("XARI_API_TOKEN", raising=False)
    response = client.post("/api/vision/marketplace-search", json={"query": "blue linen summer dress"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "XARI_API_URL_NOT_CONFIGURED"


def test_description_search_forwards_to_legacy_xari_alias_and_keeps_candidates_pending_cal(client, monkeypatch):
    monkeypatch.setenv("XARI_API_URL", "https://xari.example.test")
    monkeypatch.setenv("XARI_API_TOKEN", "xari-internal-token-at-least-thirty-two-bytes")
    fake = FakeAsyncClient([FakeResponse({
        "status": "complete",
        "query": "green linen dress",
        "candidate_count": 2,
        "candidates": [{"variant_id": "offer-1", "product_name": "green dress", "image_urls": ["https://cdn.example.test/unverified.jpg"], "product": {"image_urls": ["https://cdn.example.test/nested.jpg"]}}],
        "display_authorized": False,
        "decision_status": "PENDING_CAL",
        "scores_are_probabilities": False,
    })])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post("/api/vision/marketplace-search", json={"query": " green   linen dress ", "limit": 5})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["candidate_count"] == 2
    assert data["display_authorized"] is False
    assert data["decision_status"] == "PENDING_CAL"
    assert data["candidates"][0]["image_urls"] == []
    assert data["candidates"][0]["product"]["image_urls"] == []
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


def test_click_it_uses_verified_commerce_subject_and_returns_only_pending_candidates(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("VIRTUAL_TWIN_API_URL", "https://virtual-twin.example.test")
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "virtual-twin-internal-token-at-least-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer", "email": None}),
        FakeResponse({
            "status": "complete",
            "candidates": [{"variant_id": "variant-3", "product_name": "linen shirt", "image_urls": ["https://cdn.example.test/unverified.jpg"], "product": {"image_urls": ["https://cdn.example.test/nested.jpg"]}}],
            "candidate_count": 1,
            "display_authorized": False,
            "decision_status": "PENDING_CAL",
            "image_persisted": False,
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/vision/click-it",
        headers={"Authorization": "Bearer signed-user-token"},
        data={
            "consent_id": "consent-record-1234",
            "consent_image_processing": "true",
            "consent_click_it": "true",
        },
        files={"product_image": ("dress.png", b"validated-photo-bytes", "image/png")},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["display_authorized"] is False
    assert response.json()["candidates"][0]["variant_id"] == "variant-3"
    assert response.json()["candidates"][0]["image_urls"] == []
    assert response.json()["candidates"][0]["product"]["image_urls"] == []
    assert len(fake.calls) == 2
    assert fake.calls[0][1] == "https://commerce.example.test/me"
    assert fake.calls[1][1] == "https://virtual-twin.example.test/click-it"
    assert fake.calls[1][2]["data"]["subject_id"] == "signed-user-42"
    assert "subject_id" not in response.request.content.decode(errors="ignore")
    assert fake.calls[1][2]["files"]["product_image"][1] == b"validated-photo-bytes"


def test_click_it_rejects_unsupported_image_before_calling_services(client, monkeypatch):
    response = client.post(
        "/api/vision/click-it",
        headers={"Authorization": "Bearer signed-user-token"},
        data={
            "consent_id": "consent-record-1234",
            "consent_image_processing": "true",
            "consent_click_it": "true",
        },
        files={"product_image": ("payload.bin", b"x", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "UNSUPPORTED_PRODUCT_IMAGE_TYPE"

def test_marketplace_ui_has_xari_description_search_and_mobile_click_it_capture(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="aiQuery"' in response.text
    assert 'id="aiSearchBtn"' in response.text
    assert 'id="clickItImage"' in response.text
    assert 'capture="environment"' in response.text
    assert 'id="clickItConsentId"' in response.text
    assert 'id="clickItImageConsent"' in response.text
    assert 'id="clickItSearchConsent"' in response.text
    assert 'fetch("/api/vision/marketplace-search"' in response.text
    assert 'fetch("/api/vision/click-it"' in response.text
    assert "display_authorized===true" in response.text
    assert "PENDING_CAL" in response.text

def test_description_search_prefers_xari_environment_names(client, monkeypatch):
    monkeypatch.setenv("XARI_API_URL", "https://xari.example.test")
    monkeypatch.setenv("XARI_API_TOKEN", "xari-internal-token-at-least-thirty-two-bytes")
    monkeypatch.setenv("TARI_API_URL", "https://legacy-xari.example.test")
    monkeypatch.setenv("TARI_API_TOKEN", "legacy-xari-token-at-least-thirty-two-bytes")
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
                "product": {"product_id": "product-1", "image_urls": ["https://cdn.example.test/product.jpg"]},
                "offer": {"variant_id": "variant-1", "image_urls": ["https://cdn.example.test/offer.jpg"],
                          "product": {"image_urls": ["https://cdn.example.test/nested-offer.jpg"]}},
            }],
            "withheld_candidate_ids": [],
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
    assert "Authorization" not in response.text


def test_wardrobe_page_exposes_feedback_and_consent_controls(client):
    response = client.get("/wardrobe")
    assert response.status_code == 200
    assert "Enable style learning" in response.text
    assert "Dislike" in response.text
    assert "Avoid" in response.text
    assert "/api/wardrobe/recommendations" in response.text
    assert "PNELLY · daily look intelligence" in response.text
    assert "/api/wardrobe/pnelly/daily-looks" in response.text
    assert "Mark this look worn" in response.text
    assert "Not my style" in response.text
    assert "profile_storage" in response.text


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


def test_pnelly_daily_looks_uses_verified_wardrobe_and_gateway_subject(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")

    active_item = {
        "owner_user_id": "signed-user-42",
        "item_id": "shirt-001",
        "display_name": "Blue linen shirt",
        "category": "tops",
        "attributes": ["blue", "linen"],
        "status": "active",
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
    }
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": [active_item]}),
        FakeResponse({
            "schema_version": "1.0",
            "request_id": "will-be-uuid",
            "mode": "pnelly_wardrobe_daily_looks",
            "recommendation": recommendation,
        }),
    ])

    # The BFF generates the request ID; mirror it in the fake upstream result.
    original_post = fake.post

    async def post_with_request_echo(url, **kwargs):
        if url == "https://decision.example.test/v1/pnelly/daily-looks":
            fake.responses[0]._payload["request_id"] = kwargs["json"]["request_id"]
        return await original_post(url, **kwargs)

    fake.post = post_with_request_echo
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/daily-looks",
        headers={"Authorization": "Bearer signed-session"},
        json={"occasion": "work", "climate": "hot_dry", "timezone": "Africa/Nairobi"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    call = fake.calls[2]
    assert call[1] == "https://decision.example.test/v1/pnelly/daily-looks"
    assert call[2]["headers"]["X-End-User-Authorization"] == "Bearer signed-session"
    sent_items = call[2]["json"]["wardrobe_items"]
    assert sent_items[0]["owner_user_id"] == "signed-user-42"
    assert "image_asset_id" not in sent_items[0]
    assert call[2]["json"]["occasion"] == "work"
    assert call[2]["json"]["climate"] == "hot_dry"
    assert call[2]["json"]["local_date"]
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
