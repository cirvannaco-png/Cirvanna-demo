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

    async def patch(self, url, **kwargs):
        self.calls.append(("PATCH", url, kwargs))
        return self.responses.pop(0)

    async def put(self, url, **kwargs):
        self.calls.append(("PUT", url, kwargs))
        return self.responses.pop(0)

    async def delete(self, url, **kwargs):
        self.calls.append(("DELETE", url, kwargs))
        return self.responses.pop(0)



def test_description_search_fails_closed_without_xari_or_legacy_secret(client, monkeypatch):
    monkeypatch.delenv("TARI_API_URL", raising=False)
    monkeypatch.delenv("TARI_API_TOKEN", raising=False)
    monkeypatch.delenv("XARI_API_URL", raising=False)
    monkeypatch.delenv("XARI_API_TOKEN", raising=False)
    response = client.post("/api/vision/marketplace-search", json={"query": "blue linen summer dress"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "XARI_API_URL_NOT_CONFIGURED"


def test_description_search_forwards_to_legacy_tari_alias_and_keeps_candidates_pending_cal(client, monkeypatch):
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

