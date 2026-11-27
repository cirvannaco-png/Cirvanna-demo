import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import main


def future_expiry(hours: int = 12) -> str:
    """Return a moving expiry so consent tests remain valid at any run time."""
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


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


def test_api_error_responses_are_never_cacheable(client):
    # Framework-generated auth errors must receive the same cache policy as
    # successful personalized responses; otherwise intermediaries may retain
    # stale authorization-dependent representations.
    offers = client.get("/api/commerce/marketplace/offers")
    assert offers.status_code == 401
    assert "no-store" in offers.headers["cache-control"].casefold()
    assert offers.headers["pragma"] == "no-cache"
    assert offers.headers["expires"] == "0"

    click_it = client.post("/api/vision/click-it", headers={"Authorization": "Bearer test-user-token"})
    assert click_it.status_code == 503
    assert "no-store" in click_it.headers["cache-control"].casefold()


def test_marketplace_pnelly_search_uses_wardrobe_cil_path_and_complementer_advisory(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="aiDiscoveryResults"' in response.text
    assert '"/api/wardrobe/recommendations"' in response.text
    assert '"/api/vision/complementer"' in response.text
    assert 'id="pnellyConversationConsent"' in response.text
    assert 'window.addEventListener("cirvanna:session-ready"' in response.text
    assert 'function acceptMarketplaceSession(token)' in response.text
    assert 'if(previousToken&&previousConversationId)' in response.text
    assert "marketplaceSessionGeneration" in response.text
    assert "restorePnellyConversationForSession" in response.text
    assert "sessionStorage.setItem(PNELLY_CONVERSATION_STORAGE_KEY" in response.text
    assert "deletePnellyConversationRemotely(creatingToken,conversationId)" in response.text
    assert "requestGeneration!==marketplaceSessionGeneration" in response.text
    assert '$("aiDiscoveryResults").replaceChildren();' in response.text
    assert "The previous account's conversation could not be deleted during account switching" in response.text
    assert 'Its structured context remains bound to that account and expires within 24 hours' in response.text
    assert 'bootstrap.publicOffersBase.replace(/\\/$/,"")' in response.text
    assert 'id="pnellyStartConversationBtn"' in response.text
    assert 'id="pnellyEndConversationBtn"' in response.text
    assert '"/api/wardrobe/pnelly/conversations"' in response.text
    assert 'body.conversation_id=pnellyConversationId' in response.text
    assert 'body.conversation_turn_id="pnelly-turn-"+crypto.randomUUID()' in response.text
    assert 'raw_transcript_stored!==false' in response.text
    assert 'localStorage.setItem("cirvanna-pnelly-conversation"' not in response.text
    assert "CAL SHOW" in response.text
    assert "wardrobe-aware marketplace" in response.text
    # Click It stays explicitly unavailable while its publication lifecycle remains unverified.
    assert "Click It · Temporarily paused" in response.text
    assert "No photo is requested or sent from this page" in response.text


def test_marketplace_offers_rejects_unbound_or_cil_ineligible_cal_decisions(client, monkeypatch):
    invalid_decisions = [
        {"product_id": "other-product", "catalog_version": 7, "verdict": "show",
         "may_display": True, "cil_serving_status": "eligible"},
        {"product_id": "product-1", "catalog_version": 8, "verdict": "show",
         "may_display": True, "cil_serving_status": "eligible"},
        {"product_id": "product-1", "catalog_version": 7, "verdict": "show",
         "may_display": True, "cil_serving_status": "review"},
        {"product_id": "product-1", "catalog_version": 7, "verdict": "show",
         "may_display": True, "cil_serving_status": "not_assessed",
         "policy_version": "policy-1", "arbitration_contract_version": "1",
         "decision_pipeline_contract_version": "1"},
        {"product_id": "product-1", "catalog_version": 7, "verdict": "show",
         "may_display": True, "cil_serving_status": "eligible",
         "policy_version": "", "arbitration_contract_version": "1",
         "decision_pipeline_contract_version": "1"},
        {"product_id": "product-1", "catalog_version": 7, "verdict": "show",
         "may_display": True, "cil_serving_status": "eligible",
         "policy_version": "policy-1", "arbitration_contract_version": "1",
         "decision_pipeline_contract_version": ""},
        {"product_id": "product-1", "catalog_version": 7, "verdict": "block",
         "may_display": False, "cil_serving_status": "eligible",
         "policy_version": "policy-1", "arbitration_contract_version": "1",
         "decision_pipeline_contract_version": "1"},
        {"product_id": "product-1", "catalog_version": 7, "verdict": "review",
         "may_display": False, "cil_serving_status": "eligible",
         "policy_version": "policy-1", "arbitration_contract_version": "1",
         "decision_pipeline_contract_version": "1"},
    ]
    for decision in invalid_decisions:
        configure_upstreams(monkeypatch)
        monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
        monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
        fake = FakeAsyncClient([
            FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
            FakeResponse({
                "request_id": "req-marketplace-invalid",
                "display_authority": "CaTaCaCi/CAL",
                "ranked_candidate_count": 1,
                "displayable_products": [{
                    "product": {"product_id": "product-1", "catalog_version": 7,
                                "name": "Linen shirt", "image_urls": []},
                    "offer": {"catalog_product_id": "product-1", "variant_id": "variant-1",
                              "price_minor": 2500, "currency": "KES"},
                    "decision": decision,
                }],
                "withheld_candidate_ids": [],
            }),
        ])
        monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
        response = client.get(
            "/api/commerce/marketplace/offers?q=linen",
            headers={"Authorization": "Bearer signed-session"},
        )
        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "CAL_MARKETPLACE_CANDIDATE_AUTHORIZATION_INVALID"


def test_page_bootstraps_same_origin_live_offers_not_demo_data(client, monkeypatch):
    monkeypatch.delenv("MARKETPLACE_ENABLE_DEVELOPER_TOKEN_INPUT", raising=False)
    monkeypatch.delenv("MARKETPLACE_ENVIRONMENT", raising=False)
    response = client.get("/")
    assert response.status_code == 200
    assert 'window.CIRVANNA_MARKETPLACE_CONFIG = Object.freeze({publicOffersBase:"/api/commerce",allowDeveloperTokenInput:false});' in response.text
    assert "bootstrap.publicOffersBase" in response.text
    assert 'window.dispatchEvent(new CustomEvent("cirvanna:session-ready"' in response.text
    assert "accessToken:token" in response.text
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
                    "product_id": "product-1", "catalog_version": 7,
                    "name": "Linen shirt", "brand": "Cirvanna",
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
                "decision": {"product_id": "product-1", "catalog_version": 7, "verdict": "show", "may_display": True, "cil_serving_status": "eligible", "policy_version": "policy-1", "arbitration_contract_version": "1", "decision_pipeline_contract_version": "1"},
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
    assert data["request_id"] == "req-marketplace-1"
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
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"user_id": "signed-user-42"}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
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
    assert [call[1] for call in fake.calls] == ["https://commerce.example.test/me"] * 4
    assert calls == []

    # Removing an existing cart line is a safe cleanup operation and remains available.
    removed = client.delete(f"/api/commerce/cart/items/{variant}", headers=headers)
    assert removed.status_code == 200
    assert calls and calls[0][0][0] == "DELETE"

def test_account_proxy_does_not_forward_checkout_without_candidate_authorization(client, monkeypatch):
    configure_upstreams(monkeypatch)
    fake = FakeAsyncClient([FakeResponse({"user_id": "signed-user-42"})])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
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
    assert [call[1] for call in fake.calls] == ["https://commerce.example.test/me"]
    assert calls == []

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
        self.auto_echo_identity_consent = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url.endswith("/v1/tal/consents") and self.auto_echo_identity_consent:
            response = self.responses.pop(0) if self.responses else FakeResponse({})
            if response.status_code >= 400:
                return response
            payload = dict(response._payload) if isinstance(response._payload, dict) else {}
            payload.update({
                "receipt_id": kwargs["json"]["receipt_id"],
                "consent_id": kwargs["json"].get("consent_id") or kwargs["json"]["receipt_id"],
                "resource_id": kwargs["json"].get("resource_id"),
                "granted": kwargs["json"]["granted"],
            })
            payload.setdefault("status", "recorded")
            return FakeResponse(payload, status_code=response.status_code)
        if url.endswith("/revoke") and self.auto_echo_identity_consent:
            return self.responses.pop(0) if self.responses else FakeResponse({"status": "revoked"})
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

    async def request(self, method, url, **kwargs):
        self.calls.append((method.upper(), url, kwargs))
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
    # PNELLY now uses the authenticated, wardrobe-aware discovery path.
    # The retrieval-only legacy endpoint is not a customer-facing product-card path.
    assert 'fetch("/api/wardrobe/recommendations"' in response.text
    assert 'fetch("/api/vision/marketplace-search"' not in response.text
    assert 'fetch("/api/vision/click-it"' not in response.text
    assert 'data.display_authority!=="CaTaCaCi/CAL"' in response.text
    assert 'decision.verdict!=="show"' in response.text
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


def test_pnelly_conversation_restore_is_subject_scoped_and_returns_metadata_only(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    conversation_id = "4a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({
            "status": "active",
            "conversation_id": conversation_id,
            "state_version": 3,
            "expires_at": future_expiry(),
            "context": {"query": "private phrase must not reach the browser"},
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get(
        "/api/wardrobe/pnelly/conversations/" + conversation_id,
        headers={"Authorization": "Bearer signed-session"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["status"] == "active"
    assert response.json()["conversation_id"] == conversation_id
    assert response.json()["state_version"] == 3
    assert response.json()["retention_hours"] == 24
    assert response.json()["raw_transcript_stored"] is False
    assert "context" not in response.json()
    assert "private phrase must not reach the browser" not in response.text
    assert fake.calls[1][1].endswith("/v1/pnelly/conversations/" + conversation_id)
    assert fake.calls[1][2]["params"]["subject_id"] == "signed-user-42"


def test_pnelly_conversation_restore_does_not_disclose_foreign_subject_context(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    conversation_id = "4a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "different-signed-user", "role": "customer"}),
        FakeResponse({"detail": "not found"}, status_code=404),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get(
        "/api/wardrobe/pnelly/conversations/" + conversation_id,
        headers={"Authorization": "Bearer other-session"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PNELLY_CONVERSATION_NOT_FOUND_FOR_SUBJECT"
    assert fake.calls[1][2]["params"]["subject_id"] == "different-signed-user"


def test_pnelly_conversation_delete_requires_confirmed_inactive_consent(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    conversation_id = "4a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"status": "deleted", "conversation_id": conversation_id, "consent_inactive": True}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.delete(
        "/api/wardrobe/pnelly/conversations/" + conversation_id,
        headers={"Authorization": "Bearer signed-session"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    assert response.json()["conversation_id"] == conversation_id
    assert response.json()["consent_inactive"] is True
    assert fake.calls[1][1].endswith("/v1/pnelly/conversations/" + conversation_id)
    assert fake.calls[1][2]["params"]["subject_id"] == "signed-user-42"

    unsafe_fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"status": "deleted", "conversation_id": conversation_id, "consent_inactive": False}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: unsafe_fake)
    unsafe = client.delete(
        "/api/wardrobe/pnelly/conversations/" + conversation_id,
        headers={"Authorization": "Bearer signed-session"},
    )
    assert unsafe.status_code == 502
    assert unsafe.json()["detail"]["code"] == "PNELLY_CONVERSATION_DELETE_RESPONSE_INVALID"


def test_pnelly_conversation_creation_revokes_malformed_partial_consent(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    conversation_id = "4a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
    receipt_id = "5b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e"
    identifiers = iter([__import__("uuid").UUID(conversation_id), __import__("uuid").UUID(receipt_id)])
    monkeypatch.setattr(main.uuid, "uuid4", lambda: next(identifiers))
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({
            "receipt_id": receipt_id, "consent_id": "wrong-conversation",
            "resource_id": conversation_id, "granted": True,
        }),
        FakeResponse({"status": "revoked"}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/conversations",
        headers={"Authorization": "Bearer signed-session"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "PNELLY_CONVERSATION_CONSENT_BINDING_INVALID"
    assert fake.calls[2][1].endswith("/v1/tal/consents/" + receipt_id + "/revoke")


def test_pnelly_conversation_creation_records_explicit_resource_bound_24_hour_consent(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    conversation_id = "4a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
    receipt_id = "5b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e"
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({
            "receipt_id": receipt_id, "consent_id": conversation_id,
            "resource_id": conversation_id, "granted": True, "status": "recorded",
        }),
        FakeResponse({
            "status": "created", "conversation_id": conversation_id, "state_version": 0,
            "expires_at": future_expiry(), "context": {},
        }),
    ])
    identifiers = iter([__import__("uuid").UUID(conversation_id), __import__("uuid").UUID(receipt_id)])
    monkeypatch.setattr(main.uuid, "uuid4", lambda: next(identifiers))
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/conversations",
        headers={"Authorization": "Bearer signed-session"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["conversation_id"] == conversation_id
    assert response.json()["retention_hours"] == 24
    assert response.json()["raw_transcript_stored"] is False
    consent = fake.calls[1][2]["json"]
    assert consent["scope"] == "pnelly_conversation"
    assert consent["consent_id"] == conversation_id
    assert consent["resource_id"] == conversation_id
    assert consent["granted"] is True
    assert consent["expires_at"]
    assert fake.calls[2][1].endswith("/v1/pnelly/conversations?subject_id=signed-user-42")


def test_wardrobe_recommendations_persist_context_before_cal_discovery(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    conversation_id = "4a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({
            "status": "active", "conversation_id": conversation_id, "state_version": 1,
            "expires_at": future_expiry(),
            "context": {
                "query": "green dress",
                "category": "dress",
                "currency": "KES",
                "location": "Subukia",
                "occasion": "work",
                "climate": "warm",
                "constraints": ["linen"],
                "exclude_owned_products": True,
            },
        }),
        FakeResponse({
            "status": "updated", "conversation_id": conversation_id, "state_version": 2,
            "expires_at": future_expiry(),
            "context": {
                "query": "make it more formal",
                "category": "dress",
                "currency": "KES",
                "location": "Subukia",
                "occasion": "evening",
                "climate": "warm",
                "constraints": ["linen"],
                "exclude_owned_products": True,
            },
        }),
        FakeResponse({
            "request_id": "req-conversation-1", "display_authority": "CaTaCaCi/CAL", "ranked_candidate_count": 0,
            "displayable_products": [], "withheld_candidate_ids": [],
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/recommendations",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "query": "make it more formal",
            "occasion": "evening",
            "conversation_id": conversation_id,
            "conversation_turn_id": "pnelly-turn-0002",
        },
    )
    assert response.status_code == 200, response.text
    assert fake.calls[1][1].endswith("/v1/pnelly/conversations/" + conversation_id)
    update = fake.calls[2][2]["json"]
    assert update["expected_version"] == 1
    assert update["turn_id"] == "pnelly-turn-0002"
    assert update["context"]["category"] == "dress"
    assert update["context"]["currency"] == "KES"
    assert update["context"]["location"] == "Subukia"
    assert update["context"]["occasion"] == "evening"
    gateway = fake.calls[3][2]["json"]
    assert gateway["query"] == "make it more formal linen"
    assert gateway["category"] == "dress"
    assert gateway["currency"] == "KES"
    assert gateway["context"]["location"] == "Subukia"
    assert response.json()["conversation"]["state_version"] == 2
    assert response.json()["conversation"]["raw_transcript_stored"] is False


def test_wardrobe_recommendations_block_revoked_conversation_before_gateway(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"detail": {"code": "ACTIVE_PNELLY_CONVERSATION_CONSENT_REQUIRED"}}, status_code=403),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/recommendations",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "query": "green dress",
            "conversation_id": "4a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
            "conversation_turn_id": "pnelly-turn-0003",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PNELLY_CONVERSATION_EXPIRED_OR_REVOKED"
    assert len(fake.calls) == 2


def test_wardrobe_recommendations_forward_verified_token_to_cal_decision_gateway(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({
            "request_id": "req-1",
            "display_authority": "CaTaCaCi/CAL",
            "ranked_candidate_count": 2,
            "displayable_products": [{
                "product": {"product_id": "product-1", "catalog_version": 3,
                            "image_urls": ["https://cdn.example.test/product.jpg"]},
                "offer": {"catalog_product_id": "product-1", "variant_id": "variant-1",
                          "image_urls": ["https://cdn.example.test/offer.jpg"],
                          "product": {"image_urls": ["https://cdn.example.test/nested-offer.jpg"]}},
                "decision": {"product_id": "product-1", "catalog_version": 3,
                             "verdict": "show", "may_display": True,
                             "policy_version": "policy-1", "arbitration_contract_version": "1",
                             "decision_pipeline_contract_version": "1"},
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


def test_sanctuary_and_twin_onboarding_pages_are_served_without_cache(client):
    sanctuary = client.get("/sanctuary.html")
    assert sanctuary.status_code == 200
    assert "Cirvanna — Your Sanctuary" in sanctuary.text
    assert "twin-onboarding.html" in sanctuary.text
    assert sanctuary.headers["cache-control"] == "no-store"

    onboarding = client.get("/twin-onboarding.html")
    assert onboarding.status_code == 200
    assert "Cirvanna — Your Twin Journey" in onboarding.text
    assert "cirvanna-twin-onboarding.js" in onboarding.text
    assert "No consent is being recorded on this page" in onboarding.text
    assert "Capture is currently locked" in onboarding.text
    assert onboarding.headers["cache-control"] == "no-store"
    assert onboarding.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"

    stylesheet = client.get("/assets/cirvanna-twin-onboarding.css")
    script = client.get("/assets/cirvanna-twin-onboarding.js")
    assert stylesheet.status_code == 200
    assert script.status_code == 200
    assert "prefers-reduced-motion" in stylesheet.text
    assert "localStorage" not in script.text
    assert "sessionStorage" not in script.text


def test_wardrobe_page_exposes_feedback_and_consent_controls(client):
    response = client.get("/wardrobe")
    assert response.status_code == 200
    assert "Enable style learning" in response.text
    assert "Dislike" in response.text
    assert "Avoid" in response.text
    assert "/api/wardrobe/recommendations" in response.text
    assert "/api/vision/complementer" in response.text
    assert "/api/vision/complementer/feedback" in response.text
    assert "Ask Complementer" in response.text
    assert "Refine with Complementer" not in response.text
    assert "24-hour discovery continuity" in response.text
    assert "Remember my discovery context for 24 hours" in response.text
    assert "/api/wardrobe/pnelly/conversations" in response.text
    assert "Clear saved context" in response.text
    assert "Save to Wardrobe" in response.text
    assert "/api/wardrobe/pnelly/save-look" in response.text
    assert "/api/wardrobe/pnelly/look-feedback" in response.text
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
        "eligibility": {"verdict": "PASS", "candidate_id": "will-be-uuid", "reason_codes": ["EEPL_POLICY_PASSED"],
                        "explanations": ["Context passed."], "cal_authorized": False},
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
            gateway_response._payload["eligibility"]["candidate_id"] = request_body["request_id"]
            gateway_response._payload["recommendation"]["wardrobe_rotation"]["next_state"]["cycle_started_at"] = request_body["local_date"]
        return await original_post(url, **kwargs)

    fake.post = post_with_rotation_date
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/daily-looks",
        headers={"Authorization": "Bearer signed-session"},
        json={"location": "Nairobi, Kenya", "occasion": "work", "climate": "hot_dry", "timezone": "Africa/Nairobi"},
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
    context = gateway_call[2]["json"]["context"]
    assert context["location"] == "Nairobi, Kenya"
    assert context["location_source"] == "user_declared"
    assert context["occasion_source"] == "user_declared"
    assert context["climate_source"] == "user_declared"
    assert context["location_observed_at"] == context["occasion_observed_at"] == context["climate_observed_at"]
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


def test_pnelly_daily_looks_returns_eepl_review_without_writing_rotation(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-internal-token-more-than-thirty-two")
    review_response = FakeResponse({
            "schema_version": "1.0", "request_id": "review-request-001",
            "mode": "pnelly_wardrobe_daily_looks",
            "eligibility": {
                "verdict": "REVIEW", "candidate_id": "review-request-001", "cal_authorized": False,
                "reason_codes": ["EEPL_REQUIRED_CONTEXT_MISSING_LOCATION"],
                "explanations": ["Location is required."],
            },
            "recommendation": {"look_count": 0, "ready_count": 0, "looks": []},
        })
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": []}),
        FakeResponse({"state": None, "version": 0}),
        review_response,
    ])
    original_post = fake.post
    async def post_with_review_envelope(url, **kwargs):
        if url == "https://decision.example.test/v1/pnelly/daily-looks":
            review_response._payload["request_id"] = kwargs["json"]["request_id"]
            review_response._payload["eligibility"]["candidate_id"] = kwargs["json"]["request_id"]
        return await original_post(url, **kwargs)
    fake.post = post_with_review_envelope
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/daily-looks",
        headers={"Authorization": "Bearer signed-session"},
        json={"timezone": "Africa/Nairobi"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["eligibility"]["verdict"] == "REVIEW"
    assert response.json()["recommendation"]["looks"] == []
    assert len(fake.calls) == 4
    assert not any(call[0] == "PUT" for call in fake.calls)


def test_pnelly_daily_looks_does_not_accept_browser_supplied_context_timestamps(client):
    response = client.post(
        "/api/wardrobe/pnelly/daily-looks",
        headers={"Authorization": "Bearer signed-session"},
        json={"location": "Nairobi, Kenya", "context": {"location_observed_at": "2020-01-01T00:00:00Z"}},
    )
    assert response.status_code == 422


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
        "schema_version": "1.0", "request_id": "malformed-request-001",
        "mode": "pnelly_wardrobe_daily_looks",
        "eligibility": {"verdict": "PASS", "candidate_id": "malformed-request-001",
                        "reason_codes": ["EEPL_POLICY_PASSED"], "explanations": ["Context passed."],
                        "cal_authorized": False},
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
    original_post = fake.post
    async def post_with_request_id(url, **kwargs):
        if url == "https://decision.example.test/v1/pnelly/daily-looks":
            malformed["request_id"] = kwargs["json"]["request_id"]
            malformed["eligibility"]["candidate_id"] = kwargs["json"]["request_id"]
        return await original_post(url, **kwargs)
    fake.post = post_with_request_id
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
        "schema_version": "1.0", "request_id": "forged-preview-request-001",
        "mode": "pnelly_wardrobe_daily_looks",
        "eligibility": {"verdict": "PASS", "candidate_id": "forged-preview-request-001",
                        "reason_codes": ["EEPL_POLICY_PASSED"], "explanations": ["Context passed."],
                        "cal_authorized": False},
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
    original_post = fake.post
    async def post_with_forged_preview_envelope(url, **kwargs):
        if url == "https://decision.example.test/v1/pnelly/daily-looks":
            forged_preview["request_id"] = kwargs["json"]["request_id"]
            forged_preview["eligibility"]["candidate_id"] = kwargs["json"]["request_id"]
        return await original_post(url, **kwargs)
    fake.post = post_with_forged_preview_envelope
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
    gateway_response = FakeResponse({
        "schema_version": "1.0", "request_id": "will-be-uuid",
        "mode": "pnelly_wardrobe_daily_looks",
        "eligibility": {"verdict": "PASS", "candidate_id": "will-be-uuid",
                        "reason_codes": ["EEPL_POLICY_PASSED"], "explanations": ["Context passed."],
                        "cal_authorized": False},
        "recommendation": recommendation,
    })
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
        body["eligibility"]["candidate_id"] = kwargs["json"]["request_id"]
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
                "cycle_complete": complete, "cycle_overdue": not complete,
                "revival_queue_item_ids": queue,
                "next_state": {
                    "cycle_number": cycle, "cycle_started_at": start,
                    "seen_item_ids": seen,
                },
            },
        }
    first_gateway = FakeResponse({
        "schema_version": "1.0", "request_id": "will-be-uuid",
        "mode": "pnelly_wardrobe_daily_looks",
        "eligibility": {"verdict": "PASS", "candidate_id": "will-be-uuid",
                        "reason_codes": ["EEPL_POLICY_PASSED"], "explanations": ["Context passed."],
                        "cal_authorized": False},
        "recommendation": recommendation(
            complete=False, cycle=1, start="2026-11-07", seen=["shirt-001"], queue=["pants-001"],
        ),
    })
    second_gateway = FakeResponse({
        "schema_version": "1.0", "request_id": "will-be-uuid",
        "mode": "pnelly_wardrobe_daily_looks",
        "eligibility": {"verdict": "PASS", "candidate_id": "will-be-uuid",
                        "reason_codes": ["EEPL_POLICY_PASSED"], "explanations": ["Context passed."],
                        "cal_authorized": False},
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
            response._payload["eligibility"]["candidate_id"] = body["request_id"]
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
            "taxonomy_version": "1.1.0",
            "categories": [
                {"id": "shoes", "label": "Shoes and footwear", "group": "footwear"},
                {"id": "makeup", "label": "Makeup", "group": "beauty"},
                {"id": "brow_products", "label": "Eyebrow products", "group": "beauty"},
                {"id": "lash_products", "label": "Eyelash products", "group": "beauty"},
                {"id": "lip_products", "label": "Lip products and lipstick", "group": "beauty"},
                {"id": "wigs_extensions", "label": "Wigs, extensions and hairpieces", "group": "hair"},
                {"id": "hair_colour", "label": "Hair colour products", "group": "beauty"},
                {"id": "hair_styling", "label": "Hair styling products and tools", "group": "beauty"},
                {"id": "earrings", "label": "Earrings", "group": "accessories"},
                {"id": "necklaces", "label": "Necklaces and pendants", "group": "accessories"},
            ],
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/wardrobe/categories", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["taxonomy_version"] == "1.1.0"
    assert {item["id"] for item in response.json()["categories"]} == {"shoes", "makeup", "brow_products", "lash_products", "lip_products", "wigs_extensions", "hair_colour", "hair_styling", "earrings", "necklaces"}
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
    assert forwarded["garment_asset_purpose"] == "wardrobe_garment_flat_lay"
    assert forwarded["garment_photo_type"] == "flat-lay"
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


def test_my_virtual_twins_uses_verified_owner_and_returns_metadata_only(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("TWIN_REGISTRY_API_URL", "https://registry.example.test")
    monkeypatch.setenv("TWIN_REGISTRY_API_TOKEN", "twin-registry-internal-token-at-least-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"count": 1, "twins": [{
            "twin_id": "twin-owned-001",
            "status": "active",
            "version": 2,
            "representation_type": "full_body_mesh",
            "model_id": "cirvanna-full-body-mesh",
            "model_revision": "a" * 40,
            "model_release_sha256": "c" * 64,
            "created_at": "2026-11-17T10:00:00+00:00",
            "updated_at": "2026-11-17T10:05:00+00:00",
            "subject_id": "signed-user-42",
            "mesh_asset_id": "private-mesh-secret",
            "source_image_asset_ids": ["private-source-secret"],
            "object_store_key": "must-not-leak",
        }]}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get(
        "/api/virtual-twin/me",
        headers={"Authorization": "Bearer signed-session"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    payload = response.json()
    assert payload["count"] == 1
    assert payload["twins"][0]["twin_id"] == "twin-owned-001"
    assert payload["twins"][0]["status"] == "active"
    assert payload["twins"][0]["model_release_sha256"] == "c" * 64
    for secret in ("subject_id", "mesh_asset_id", "source_image_asset_ids", "object_store_key"):
        assert secret not in response.text
    assert fake.calls[1][1] == "https://registry.example.test/internal/v1/twins"
    assert fake.calls[1][2]["params"] == {"subject_id": "signed-user-42", "limit": 10}
    assert fake.calls[1][2]["headers"]["Authorization"].startswith("Bearer ")


def test_my_virtual_twins_requires_signed_customer_identity_before_registry(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    fake = FakeAsyncClient([])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/virtual-twin/me")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "USER_BEARER_REQUIRED"
    assert fake.calls == []


def test_my_virtual_twins_rejects_registry_payload_with_invalid_model_revision(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("TWIN_REGISTRY_API_URL", "https://registry.example.test")
    monkeypatch.setenv("TWIN_REGISTRY_API_TOKEN", "twin-registry-internal-token-at-least-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"count": 1, "twins": [{
            "twin_id": "twin-owned-001", "status": "active", "version": 1,
            "representation_type": "full_body_mesh", "model_id": "body-model",
            "model_revision": "latest", "model_release_sha256": "c" * 64,
            "created_at": "2026-11-17T10:00:00Z",
            "updated_at": "2026-11-17T10:00:00Z",
        }]}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/virtual-twin/me", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "TWIN_REGISTRY_RESPONSE_INVALID"


def test_my_virtual_twins_rejects_malformed_model_release_digest(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("TWIN_REGISTRY_API_URL", "https://registry.example.test")
    monkeypatch.setenv("TWIN_REGISTRY_API_TOKEN", "twin-registry-internal-token-at-least-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"count": 1, "twins": [{
            "twin_id": "twin-owned-001", "status": "active", "version": 1,
            "representation_type": "full_body_mesh", "model_id": "body-model",
            "model_revision": "a" * 40, "model_release_sha256": "latest",
            "created_at": "2026-11-17T10:00:00Z", "updated_at": "2026-11-17T10:00:00Z",
        }]}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/virtual-twin/me", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "TWIN_REGISTRY_RESPONSE_INVALID"


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


def test_brand_portal_exposes_shopify_merchant_controls(client):
    response = client.get("/brand-portal")
    script = client.get("/assets/brand-portal.js")
    assert response.status_code == script.status_code == 200
    for element in ("shopifyPanel", "shopifyDomain", "shopifyConnectForm", "shopifySync", "shopifyStaged"):
        assert element in response.text
    for behavior in ("startShopifyOAuth", "loadShopifyConnection", "loadShopifyStaged", "mapShopifyProduct"):
        assert behavior in script.text
    assert "credentials: \"same-origin\"" in script.text
    assert "redirect: \"manual\"" in script.text


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
        ("GET", "admin/operations/alerts"),
        ("POST", "admin/operations/alerts/123e4567-e89b-12d3-a456-426614174000/acknowledge"),
        ("POST", "admin/merchants/123e4567-e89b-12d3-a456-426614174000/decision"),
        ("GET", "admin/merchants/123e4567-e89b-12d3-a456-426614174000/markets"),
        ("PUT", "admin/merchants/123e4567-e89b-12d3-a456-426614174000/markets/KE"),
        ("GET", "integrations/shopify/install"),
        ("GET", "integrations/shopify/connection"),
        ("GET", "integrations/shopify/readiness"),
        ("GET", "integrations/shopify/staged-products"),
        ("POST", "integrations/shopify/disconnect"),
        ("POST", "integrations/shopify/sync/products"),
        ("POST", "integrations/shopify/products/123e4567-e89b-12d3-a456-426614174000/map"),
        ("POST", "integrations/shopify/products/123e4567-e89b-12d3-a456-426614174000/reactivate"),
        ("POST", "integrations/shopify/markets/KE/sync-pricing"),
    ]
    for method, route in allowed:
        assert main._authorized_commerce_path(method, route), (method, route)
    blocked = [
        ("POST", "admin/merchants"), ("POST", "webhooks/stripe"),
        ("POST", "admin/operations/alerts/not-a-uuid/acknowledge"),
        ("POST", "internal/expire-reservations"),
        ("POST", "merchant/listings/not-a-uuid/variants"),
        ("DELETE", "admin/merchant-decisions"),
        ("PUT", "admin/merchants/123e4567-e89b-12d3-a456-426614174000/markets/not-a-country"),
        ("POST", "admin/merchants/123e4567-e89b-12d3-a456-426614174000/markets"),
        ("GET", "integrations/shopify/callback"),
        ("POST", "webhooks/shopify"),
        ("POST", "internal/shopify/process-events"),
        ("POST", "integrations/shopify/products/not-a-uuid/map"),
        ("POST", "integrations/shopify/products/not-a-uuid/reactivate"),
        ("DELETE", "integrations/shopify/disconnect"),
    ]
    for method, route in blocked:
        assert not main._authorized_commerce_path(method, route), (method, route)


def test_shopify_oauth_callback_relay_forwards_same_origin_state_cookie(client, monkeypatch):
    configure_upstreams(monkeypatch)
    fake = FakeAsyncClient([FakeResponse(
        {"status": "redirect"},
        status_code=303,
        content=b"",
        headers={
            "content-type": "text/plain; charset=utf-8",
            "location": "https://cirvanna.example.test/brand-portal.html?shopify=connected",
            "set-cookie": "cirvanna_shopify_oauth_state=; Max-Age=0; Path=/integrations/shopify/callback; HttpOnly; SameSite=lax",
        },
    )])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get(
        "/integrations/shopify/callback?code=oauth-code&shop=northwind.myshopify.com&state=one-time-state-value",
        cookies={"cirvanna_shopify_oauth_state": "one-time-state-value"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "https://cirvanna.example.test/brand-portal.html?shopify=connected"
    assert "Max-Age=0" in response.headers["set-cookie"]
    method, url, kwargs = fake.calls[0]
    assert method == "GET"
    assert url == "https://commerce.example.test/integrations/shopify/callback"
    assert kwargs["headers"]["Cookie"] == "cirvanna_shopify_oauth_state=one-time-state-value"
    assert kwargs["params"] == [
        ("code", "oauth-code"),
        ("shop", "northwind.myshopify.com"),
        ("state", "one-time-state-value"),
    ]


def test_shopify_install_proxy_preserves_redirect_and_oauth_cookie(client, monkeypatch):
    configure_upstreams(monkeypatch)
    calls = []
    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse(
            {},
            status_code=302,
            content=b"",
            headers={
                "location": "https://northwind.myshopify.com/admin/oauth/authorize?client_id=app-key",
                "set-cookie": "cirvanna_shopify_oauth_state=opaque-state; Max-Age=600; Path=/integrations/shopify/callback; HttpOnly; SameSite=lax",
            },
        )
    monkeypatch.setattr(main.httpx, "request", fake_request)
    response = client.get(
        "/api/commerce/integrations/shopify/install?shop=northwind.myshopify.com",
        headers={"Authorization": "Bearer merchant-session"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"].startswith("https://northwind.myshopify.com/admin/oauth/authorize?")
    assert "HttpOnly" in response.headers["set-cookie"]
    assert calls[0][0] == "GET"
    assert calls[0][1] == "https://commerce.example.test/integrations/shopify/install"
    assert calls[0][2]["headers"]["Authorization"] == "Bearer merchant-session"


def test_shopify_oauth_callback_relay_requires_state_cookie(client, monkeypatch):
    configure_upstreams(monkeypatch)
    response = client.get(
        "/integrations/shopify/callback?code=oauth-code&shop=northwind.myshopify.com&state=one-time-state-value",
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "SHOPIFY_OAUTH_STATE_COOKIE_MISSING"


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
    revoke_urls = [url for _method, url, _kwargs in fake.calls if url.endswith("/revoke")]
    assert len(revoke_urls) == 2
    assert {url.rsplit("/", 2)[-2] for url in revoke_urls} == {row["receipt_id"] for row in fake.receipts}
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
            "display_authority": "CaTaCaCi/CAL",
            "ranked_candidate_count": 1,
            "displayable_products": [{
                "product": {"product_id": "product-1", "catalog_version": 3},
                "offer": {"catalog_product_id": "different-product", "variant_id": "variant-1"},
                "decision": {"product_id": "product-1", "catalog_version": 3,
                             "verdict": "show", "may_display": True,
                             "policy_version": "policy-1", "arbitration_contract_version": "1",
                             "decision_pipeline_contract_version": "1"},
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


def test_wardrobe_ui_is_packaged_in_the_marketplace_bff_image(client):
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    dockerfile = (root / "services/marketplace-bff/Dockerfile").read_text()
    assert "COPY services/marketplace-bff /app/services/marketplace-bff" in dockerfile
    assert "COPY apps/demo-web /app/apps/demo-web" in dockerfile
    assert "COPY packages/http_observability /app/packages/http_observability" in dockerfile
    assert "WORKDIR /app/services/marketplace-bff" in dockerfile
    assert "WARDROBE_HTML_PATH=/app/apps/demo-web/wardrobe.html" in dockerfile
    response = client.get("/wardrobe")
    assert response.status_code == 200
    assert "/api/wardrobe/pnelly/preferences" in response.text


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


def test_pnelly_preference_list_is_scoped_to_verified_customer_and_exact_profile_receipt(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-learning-internal-token-more-than-32")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-customer-42", "role": "customer"}),
        FakeResponse([{
            "receipt_id": "profile-consent-001", "scope": "profile_storage", "granted": True,
            "revoked_at": None, "expires_at": future_expiry(),
        }]),
        FakeResponse({"subject_id": "verified-customer-42", "profile_version": 4, "preferences": [
            {"preference_id": "pnelly-1", "attribute": "style:elegant", "weight": 0.8,
             "active": True, "source": "pnelly_user_confirmed", "source_request_id": "request-1"},
            {"preference_id": "user-1", "attribute": "style:romantic", "weight": 1.0,
             "active": True, "source": "user_declared"},
        ]}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get(
        "/api/wardrobe/pnelly/preferences?consent_receipt_id=profile-consent-001",
        headers={"Authorization": "Bearer signed-customer-session"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["profile_version"] == 4
    assert [item["preference_id"] for item in response.json()["preferences"]] == ["pnelly-1"]
    assert fake.calls[1][1] == "https://identity.example.test/v1/tal/consents/verified-customer-42"
    assert fake.calls[2][1] == "https://identity.example.test/v1/profiles/verified-customer-42"
    assert response.headers["cache-control"] == "no-store, private"


def test_pnelly_preference_write_requires_exact_profile_consent_and_uses_allowlisted_usi_value(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-learning-internal-token-more-than-32")
    expected_preference_id = "pnelly-" + hashlib.sha256(
        "verified-customer-42|complementer-request-001|color:teal".encode("utf-8")
    ).hexdigest()[:32]
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-customer-42", "role": "customer"}),
        FakeResponse([{
            "receipt_id": "profile-consent-001", "scope": "profile_storage", "granted": True,
            "revoked_at": None, "expires_at": future_expiry(),
        }]),
        FakeResponse({"subject_id": "verified-customer-42", "profile_version": 2, "preferences": [
            {"preference_id": "existing-1", "attribute": "style:classic", "weight": 0.8, "active": True},
        ]}),
        FakeResponse({"subject_id": "verified-customer-42", "profile_version": 3, "preferences": [
            {"preference_id": "existing-1", "attribute": "style:classic", "weight": 0.8, "active": True},
            {"preference_id": expected_preference_id, "attribute": "color:teal", "weight": 0.8, "active": True,
             "source": "pnelly_user_confirmed", "source_request_id": "complementer-request-001"},
        ]}),
        FakeResponse({"user_id": "verified-customer-42", "role": "customer"}),
        FakeResponse([{
            "receipt_id": "profile-consent-001", "scope": "profile_storage", "granted": True,
            "revoked_at": None, "expires_at": future_expiry(),
        }]),
        FakeResponse({"subject_id": "verified-customer-42", "profile_version": 3, "preferences": [
            {"preference_id": "existing-1", "attribute": "style:classic", "weight": 0.8, "active": True},
            {"preference_id": expected_preference_id, "attribute": "color:teal", "weight": 0.8, "active": True,
             "source": "pnelly_user_confirmed", "source_request_id": "complementer-request-001"},
        ]}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/preferences",
        headers={"Authorization": "Bearer signed-customer-session"},
        json={"request_id": "complementer-request-001", "consent_receipt_id": "profile-consent-001", "attribute": "color:teal"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "recorded"
    assert response.json()["durable_persistence"] is True
    assert response.json()["learning_owner"] == "USI"
    assert response.json()["profile_version"] == 3
    assert [call[0] for call in fake.calls] == ["GET", "GET", "GET", "PUT"]
    assert fake.calls[1][1] == "https://identity.example.test/v1/tal/consents/verified-customer-42"
    assert fake.calls[2][1] == "https://identity.example.test/v1/profiles/verified-customer-42"
    saved = fake.calls[3][2]["json"]["preferences"][-1]
    assert saved["preference_id"] == expected_preference_id
    assert saved["attribute"] == "color:teal"
    assert saved["source"] == "pnelly_user_confirmed"
    assert saved["source_request_id"] == "complementer-request-001"
    assert fake.calls[3][2]["json"]["consent_receipt_id"] == "profile-consent-001"
    assert response.headers["cache-control"] == "no-store, private"

    replay = client.post(
        "/api/wardrobe/pnelly/preferences",
        headers={"Authorization": "Bearer signed-customer-session"},
        json={"request_id": "complementer-request-001", "consent_receipt_id": "profile-consent-001", "attribute": "color:teal"},
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "replayed"
    assert replay.json()["preference_id"] == expected_preference_id
    assert len(fake.calls) == 7
    assert [call[0] for call in fake.calls] == ["GET", "GET", "GET", "PUT", "GET", "GET", "GET"]


def test_pnelly_preference_write_rejects_revoked_or_wrong_scope_receipt(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-learning-internal-token-more-than-32")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-customer-42", "role": "customer"}),
        FakeResponse([{
            "receipt_id": "revoked-profile-consent", "scope": "profile_storage", "granted": True,
            "revoked_at": "2026-11-22T00:00:00Z", "expires_at": future_expiry(),
        }]),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/preferences",
        headers={"Authorization": "Bearer signed-customer-session"},
        json={"request_id": "complementer-request-002", "consent_receipt_id": "revoked-profile-consent", "attribute": "style:elegant"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ACTIVE_PROFILE_STORAGE_CONSENT_REQUIRED"
    assert len(fake.calls) == 2


def test_pnelly_preference_write_rejects_style_learning_receipt_for_profile_storage(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-learning-internal-token-more-than-32")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-customer-42", "role": "customer"}),
        FakeResponse([{
            "receipt_id": "style-consent-004", "scope": "style_learning", "granted": True,
            "revoked_at": None, "expires_at": future_expiry(),
        }]),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/preferences",
        headers={"Authorization": "Bearer signed-customer-session"},
        json={"request_id": "complementer-request-004", "consent_receipt_id": "style-consent-004", "attribute": "style:elegant"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ACTIVE_PROFILE_STORAGE_CONSENT_REQUIRED"
    assert len(fake.calls) == 2


def test_pnelly_preference_write_rejects_unbounded_values_before_identity_lookup(client, monkeypatch):
    fake = FakeAsyncClient([])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/preferences",
        headers={"Authorization": "Bearer signed-customer-session"},
        json={"request_id": "complementer-request-003", "consent_receipt_id": "profile-consent-003", "attribute": "style:surprise-me"},
    )
    assert response.status_code == 422
    assert fake.calls == []


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



def test_pnelly_save_look_creates_owner_bound_saved_outfit(client, monkeypatch):
    import uuid
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    save_event_id = "pnelly-save-look-001"
    item_ids = ["shirt-001", "trousers-001"]
    expected_outfit_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"cirvanna:pnelly-save:signed-user-42:{save_event_id}",
    ))
    wardrobe_items = [{
        "owner_user_id": "signed-user-42", "item_id": item_id, "status": "active",
    } for item_id in item_ids]
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": wardrobe_items}),
        FakeResponse({"outfit": {
            "outfit_id": expected_outfit_id, "owner_user_id": "signed-user-42",
            "name": "PNELLY Everyday", "version": 1, "pieces": [
                {"slot_id": "slot-shirt", "wardrobe_item_id": "shirt-001"},
                {"slot_id": "slot-trousers", "wardrobe_item_id": "trousers-001"},
            ],
        }, "status": "created"}, status_code=201),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/save-look",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "item_ids": item_ids,
            "save_event_id": save_event_id,
            "name": "PNELLY Everyday",
        },
    )
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store, private"
    result = response.json()
    assert result["status"] == "created"
    assert result["outfit_id"] == expected_outfit_id
    create_body = fake.calls[2][2]["json"]
    assert create_body["owner_user_id"] == "signed-user-42"
    assert [piece["wardrobe_item_id"] for piece in create_body["pieces"]] == item_ids
    assert len({piece["slot_id"] for piece in create_body["pieces"]}) == len(item_ids)


def test_pnelly_save_look_replays_existing_outfit_after_uncertain_create(client, monkeypatch):
    import uuid
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    save_event_id = "pnelly-save-look-retry-001"
    item_ids = ["shirt-002", "skirt-002"]
    outfit_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"cirvanna:pnelly-save:signed-user-42:{save_event_id}",
    ))
    existing = {
        "outfit_id": outfit_id,
        "owner_user_id": "signed-user-42",
        "name": "PNELLY Elevated",
        "version": 1,
        "pieces": [
            {"slot_id": "slot-a", "wardrobe_item_id": "shirt-002"},
            {"slot_id": "slot-b", "wardrobe_item_id": "skirt-002"},
        ],
    }
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": [
            {"owner_user_id": "signed-user-42", "item_id": item_id, "status": "active"}
            for item_id in item_ids
        ]}),
        FakeResponse({"detail": {"code": "WARDROBE_OUTFIT_STORE_UNAVAILABLE"}}, status_code=503),
        FakeResponse({"owner_user_id": "signed-user-42", "outfits": [existing]}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/save-look",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "item_ids": item_ids,
            "save_event_id": save_event_id,
            "name": "PNELLY Elevated",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "replayed"
    assert response.json()["outfit_id"] == outfit_id
    assert len(fake.calls) == 4


def test_pnelly_save_look_rejects_non_owned_or_inactive_wardrobe_item(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": [
            {"owner_user_id": "signed-user-42", "item_id": "shirt-003", "status": "active"},
        ]}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/save-look",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "item_ids": ["foreign-or-inactive-item"],
            "save_event_id": "pnelly-save-invalid-001",
            "name": "PNELLY Explore",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PNELLY_SAVE_ITEM_NOT_ACTIVE_OR_NOT_OWNED"
    assert len(fake.calls) == 2




def test_pnelly_look_rejection_is_one_tal_event_not_item_level_npl_feedback(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    item_ids = ["shirt-001", "trousers-001"]
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": [
            {"owner_user_id": "signed-user-42", "item_id": item_id, "status": "active"}
            for item_id in item_ids
        ]}),
        FakeResponse([{
            "receipt_id": "style-receipt-001", "scope": "style_learning",
            "granted": True, "revoked_at": None, "expires_at": None,
        }]),
        FakeResponse({"status": "recorded", "event_id": "pnelly-look-reject-001"}, status_code=200),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/look-feedback",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "event_id": "pnelly-look-reject-001", "look_role": "everyday",
            "item_ids": item_ids, "signal": "rejected",
            "consent_receipt_id": "style-receipt-001",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["learning_owner"] == "TAL"
    assert response.json()["item_level_npl_rejection_created"] is False
    event_call = fake.calls[3]
    assert event_call[1] == "https://identity.example.test/v1/tal/events"
    assert event_call[2]["params"]["subject_id"] == "signed-user-42"
    assert event_call[2]["json"]["feature_key"] == "pnelly.look.feedback.rejected"
    assert event_call[2]["json"]["idempotency_key"] == "pnelly-look:pnelly-look-reject-001"
    assert '"wardrobe_item_ids":["shirt-001","trousers-001"]' in event_call[2]["json"]["value"]


def test_pnelly_look_feedback_rejects_revoked_consent_before_tal_write(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": [
            {"owner_user_id": "signed-user-42", "item_id": "shirt-001", "status": "active"},
        ]}),
        FakeResponse([{
            "receipt_id": "style-receipt-002", "scope": "style_learning",
            "granted": True, "revoked_at": "2026-11-13T18:00:00+00:00", "expires_at": None,
        }]),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/look-feedback",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "event_id": "pnelly-look-reject-002", "look_role": "explore",
            "item_ids": ["shirt-001"], "signal": "rejected",
            "consent_receipt_id": "style-receipt-002",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ACTIVE_STYLE_LEARNING_CONSENT_REQUIRED"
    assert len(fake.calls) == 3


def test_pnelly_look_feedback_rejects_expired_consent_before_tal_write(client, monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_URL", "https://wardrobe.example.test")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"owner_user_id": "signed-user-42", "items": [
            {"owner_user_id": "signed-user-42", "item_id": "shirt-001", "status": "active"},
        ]}),
        FakeResponse([{
            "receipt_id": "style-receipt-003", "scope": "personalization",
            "granted": True, "revoked_at": None, "expires_at": expired,
        }]),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/wardrobe/pnelly/look-feedback",
        headers={"Authorization": "Bearer signed-session"},
        json={
            "event_id": "pnelly-look-reject-003", "look_role": "elevated",
            "item_ids": ["shirt-001"], "signal": "rejected",
            "consent_receipt_id": "style-receipt-003",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ACTIVE_STYLE_LEARNING_CONSENT_REQUIRED"
    assert len(fake.calls) == 3





def test_appearance_source_photo_consent_is_explicit_scoped_and_expires(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "receipt_id": "consent-receipt-session",
            "consent_id": "appearance-consent-bundle",
            "resource_id": "appearance-look-0001",
            "granted": True,
            "status": "recorded",
        }),
        FakeResponse({
            "receipt_id": "consent-receipt-source",
            "consent_id": "appearance-consent-bundle",
            "resource_id": "appearance-look-0001",
            "granted": True,
            "status": "recorded",
        }),
        FakeResponse({
            "receipt_id": "consent-receipt-image",
            "consent_id": "appearance-consent-bundle",
            "resource_id": "appearance-look-0001",
            "granted": True,
            "status": "recorded",
        }),
    ])
    fake.auto_echo_identity_consent = True
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/appearance/consents",
        headers={"Authorization": "Bearer verified-browser-token"},
        json={
            "look_id": "appearance-look-0001",
            "base_kind": "source_photo",
            "accept_session_storage": True,
            "accept_source_storage": True,
            "accept_image_processing": True,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["granted_scopes"] == [
        "appearance_session_storage", "appearance_source_storage", "image_processing",
    ]
    assert data["look_id"] == "appearance-look-0001"
    assert len(data["consent_id"]) == 36
    assert data["consent_id"]
    assert data["expires_at"]
    assert len(data["receipt_ids"]) == 3
    assert fake.calls[0][0] == "GET"
    assert fake.calls[0][1] == "https://commerce.example.test/me"
    assert [call[2]["json"]["scope"] for call in fake.calls[1:]] == data["granted_scopes"]
    assert all(call[2]["json"]["resource_id"] == "appearance-look-0001" for call in fake.calls[1:])
    assert all(call[2]["json"]["consent_id"] == data["consent_id"] for call in fake.calls[1:])
    assert all(call[2]["json"]["expires_at"] == data["expires_at"] for call in fake.calls[1:])
    assert response.headers["cache-control"] == "no-store, private"


def test_appearance_twin_consent_does_not_imply_source_photo_storage(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "receipt_id": "consent-receipt-session-only",
            "consent_id": "appearance-twin-consent",
            "resource_id": "appearance-twin-look-0001",
            "granted": True,
            "status": "recorded",
        }),
    ])
    fake.auto_echo_identity_consent = True
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/appearance/consents",
        headers={"Authorization": "Bearer verified-browser-token"},
        json={
            "look_id": "appearance-twin-look-0001",
            "base_kind": "virtual_twin",
            "accept_session_storage": True,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["granted_scopes"] == ["appearance_session_storage"]
    assert len(fake.calls) == 2
    assert fake.calls[1][2]["json"]["scope"] == "appearance_session_storage"


def test_appearance_source_consent_rejects_missing_explicit_source_storage_acceptance(client):
    response = client.post(
        "/api/appearance/consents",
        headers={"Authorization": "Bearer verified-browser-token"},
        json={
            "look_id": "appearance-look-invalid",
            "base_kind": "source_photo",
            "accept_session_storage": True,
            "accept_source_storage": False,
            "accept_image_processing": True,
        },
    )
    assert response.status_code == 422


def test_appearance_partial_consent_failure_revokes_every_attempted_receipt(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "receipt_id": "grant-session",
            "consent_id": "appearance-consent-failed",
            "resource_id": "appearance-look-failed",
            "granted": True,
            "status": "recorded",
        }),
        FakeResponse({"detail": {"code": "CONSENT_WRITE_FAILED"}}, status_code=503),
        FakeResponse({"status": "revoked"}),
        FakeResponse({"status": "revoked"}),
    ])
    fake.auto_echo_identity_consent = True
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/appearance/consents",
        headers={"Authorization": "Bearer verified-browser-token"},
        json={
            "look_id": "appearance-look-failed",
            "base_kind": "source_photo",
            "accept_session_storage": True,
            "accept_source_storage": True,
            "accept_image_processing": True,
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "APPEARANCE_CONSENT_WRITE_FAILED"
    revoke_calls = [call for call in fake.calls if call[1].endswith("/revoke")]
    assert len(revoke_calls) == 2
    assert all(call[2]["params"]["subject_id"] == "verified-user-appearance" for call in revoke_calls)



def test_appearance_saved_look_list_binds_verified_subject_and_strips_internal_subject(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_URL", "https://appearance.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_TOKEN", "appearance-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "count": 1,
            "looks": [{
                "look_id": "appearance-saved-look-001",
                "subject_id": "verified-user-appearance",
                "base_kind": "source_photo",
                "version": 3,
                "is_favorite": True,
                "updated_at": "2026-11-16T10:00:00+00:00",
                "consent_required": False,
            }],
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get(
        "/api/appearance/looks?limit=12",
        headers={"Authorization": "Bearer browser-token"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["looks"][0]["look_id"] == "appearance-saved-look-001"
    assert "subject_id" not in response.json()["looks"][0]
    assert fake.calls[0][1] == "https://commerce.example.test/me"
    assert fake.calls[1][1] == "https://appearance.example.test/v1/looks"
    assert fake.calls[1][2]["params"] == {"limit": 12, "subject_id": "verified-user-appearance"}
    assert "appearance-internal-token" not in response.text


def test_appearance_saved_look_list_rejects_foreign_owner_summary(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_URL", "https://appearance.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_TOKEN", "appearance-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "count": 1,
            "looks": [{
                "look_id": "appearance-saved-look-002",
                "subject_id": "another-user",
                "base_kind": "virtual_twin",
                "version": 1,
                "is_favorite": False,
                "updated_at": "2026-11-16T10:00:00+00:00",
                "consent_required": False,
            }],
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get(
        "/api/appearance/looks",
        headers={"Authorization": "Bearer browser-token"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "APPEARANCE_SESSION_SCOPE_MISMATCH"


def test_appearance_look_delete_uses_verified_subject_and_delete_method(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_URL", "https://appearance.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_TOKEN", "appearance-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "status": "deleted",
            "deletion": {"job_id": "appearance-delete-job-001", "status": "completed"},
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.request(
        "DELETE",
        "/api/appearance/looks/appearance-saved-look-003",
        headers={"Authorization": "Bearer browser-token"},
        json={
            "subject_id": "attacker-controlled-subject",
            "expected_version": 2,
            "command_id": "appearance-delete-command-001",
        },
    )
    assert response.status_code == 200, response.text
    delete_call = fake.calls[1]
    assert delete_call[0] == "DELETE"
    assert delete_call[1] == "https://appearance.example.test/v1/looks/appearance-saved-look-003"
    assert delete_call[2]["json"]["subject_id"] == "verified-user-appearance"
    assert delete_call[2]["json"]["subject_id"] != "attacker-controlled-subject"
    assert "appearance-internal-token" not in response.text


def test_appearance_source_compensation_uses_appearance_reference_guard(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_URL", "https://appearance.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_TOKEN", "appearance-internal-token-more-than-thirty-two-bytes")
    asset_id = "8c3d78e2-9f42-4b5f-a0b5-1c8831c42f1b"
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({"status": "deleted", "asset_id": asset_id}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.delete(
        "/api/appearance/looks/appearance-look-failed-001/source/" + asset_id,
        headers={"Authorization": "Bearer browser-token"},
    )
    assert response.status_code == 204
    assert fake.calls[0][1] == "https://commerce.example.test/me"
    cleanup_call = fake.calls[1]
    assert cleanup_call[0] == "POST"
    assert cleanup_call[1] == "https://appearance.example.test/internal/v1/assets/compensate"
    assert cleanup_call[2]["json"] == {
        "subject_id": "verified-user-appearance",
        "parent_look_id": "appearance-look-failed-001",
        "asset_id": asset_id,
    }
    assert "appearance-internal-token" not in response.text


def test_appearance_consent_revoke_targets_exact_user_bundle_and_resource(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse([
            {
                "receipt_id": "consent-look-one",
                "consent_id": "consent-bundle-one",
                "resource_id": "appearance-look-one",
                "scope": "appearance_session_storage",
                "granted": True,
                "revoked_at": None,
            },
            {
                "receipt_id": "consent-look-two",
                "consent_id": "consent-bundle-two",
                "resource_id": "appearance-look-two",
                "scope": "appearance_session_storage",
                "granted": True,
                "revoked_at": None,
            },
        ]),
        FakeResponse({"status": "revoked"}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/appearance/consents/revoke",
        headers={"Authorization": "Bearer browser-token"},
        json={"look_id": "appearance-look-one", "consent_id": "consent-bundle-one"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "revoked"
    assert fake.calls[1][1] == "https://identity.example.test/v1/tal/consents/verified-user-appearance"
    assert fake.calls[2][1] == "https://identity.example.test/v1/tal/consents/consent-look-one/revoke"
    assert fake.calls[2][2]["params"]["subject_id"] == "verified-user-appearance"



def test_appearance_source_upload_verifies_consent_and_uses_private_asset_service(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("ASSET_SERVICE_URL", "https://asset.example.test")
    monkeypatch.setenv("ASSET_SERVICE_TOKEN", "asset-internal-token-more-than-thirty-two-bytes")
    asset_id = "8c3d78e2-9f42-4b5f-a0b5-1c8831c42f1b"
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "verified": True,
            "active": True,
            "subject_id": "verified-user-appearance",
            "consent_id": "appearance-source-consent",
            "resource_id": "appearance-look-upload-01",
            "consent_version": "appearance-look-session-v1",
            "expires_at": future_expiry(),
            "granted_scopes": [
                "appearance_session_storage", "appearance_source_storage", "image_processing",
            ],
        }),
        FakeResponse({
            "asset_id": asset_id,
            "owner_user_id": "verified-user-appearance",
            "purpose": "appearance_source_image",
            "parent_id": "appearance-look-upload-01",
            "content_type": "image/png",
            "byte_size": 128,
            "sha256": "a" * 64,
            "status": "active",
        }, status_code=201),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/appearance/looks/appearance-look-upload-01/source",
        headers={
            "Authorization": "Bearer verified-browser-token",
            "X-Appearance-Consent-ID": "appearance-source-consent",
        },
        files={"file": ("portrait.png", b"source-photo-bytes", "image/png")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["asset_id"] == asset_id
    assert response.json()["look_id"] == "appearance-look-upload-01"
    assert response.headers["cache-control"] == "no-store, private"
    assert fake.calls[1][0] == "POST"
    assert fake.calls[1][1] == "https://identity.example.test/internal/v1/consents/verify"
    assert fake.calls[1][2]["json"]["subject_id"] == "verified-user-appearance"
    assert fake.calls[1][2]["json"]["resource_id"] == "appearance-look-upload-01"
    upload_call = fake.calls[2]
    assert upload_call[1] == "https://asset.example.test/internal/v1/assets"
    assert upload_call[2]["data"]["owner_user_id"] == "verified-user-appearance"
    assert upload_call[2]["data"]["purpose"] == "appearance_source_image"
    assert upload_call[2]["data"]["parent_id"] == "appearance-look-upload-01"
    assert "asset-internal-token" not in response.text


def test_appearance_source_upload_rejects_wrong_resource_consent_before_asset_write(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("ASSET_SERVICE_URL", "https://asset.example.test")
    monkeypatch.setenv("ASSET_SERVICE_TOKEN", "asset-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "verified": True,
            "active": True,
            "subject_id": "another-user",
            "consent_id": "appearance-source-consent",
            "resource_id": "another-look",
            "consent_version": "appearance-look-session-v1",
            "expires_at": future_expiry(),
            "granted_scopes": [
                "appearance_session_storage", "appearance_source_storage", "image_processing",
            ],
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/appearance/looks/appearance-look-upload-02/source",
        headers={
            "Authorization": "Bearer verified-browser-token",
            "X-Appearance-Consent-ID": "appearance-source-consent",
        },
        files={"file": ("portrait.png", b"source-photo-bytes", "image/png")},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "APPEARANCE_SOURCE_CONSENT_BINDING_INVALID"
    assert len(fake.calls) == 2


def test_appearance_look_proxy_binds_verified_subject_and_rejects_subject_spoofing(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_URL", "https://appearance.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_TOKEN", "appearance-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "status": "created",
            "look": {
                "look_id": "appearance-look-proxy-001",
                "subject_id": "verified-user-appearance",
                "version": 1,
                "current_version": 1,
                "base": {"kind": "source_photo", "source_asset_ids": ["private-asset-001"]},
                "operations": [],
            },
        }, status_code=201),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/appearance/looks",
        headers={"Authorization": "Bearer verified-browser-token"},
        json={
            "look_id": "appearance-look-proxy-001",
            "subject_id": "attacker-controlled-subject",
            "consent_id": "appearance-consent-proxy",
            "idempotency_key": "appearance-create-proxy-001",
            "base": {"kind": "source_photo", "source_asset_ids": ["private-asset-001"]},
            "operations": [],
        },
    )
    assert response.status_code == 201, response.text
    assert "subject_id" not in response.json()["look"]
    assert fake.calls[1][0] == "POST"
    assert fake.calls[1][1] == "https://appearance.example.test/v1/looks"
    assert fake.calls[1][2]["json"]["subject_id"] == "verified-user-appearance"
    assert fake.calls[1][2]["json"]["subject_id"] != "attacker-controlled-subject"


def test_appearance_look_proxy_rejects_cross_subject_upstream_payload(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_URL", "https://appearance.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_TOKEN", "appearance-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "look": {
                "look_id": "appearance-look-proxy-002",
                "subject_id": "another-user",
            },
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get(
        "/api/appearance/looks/appearance-look-proxy-002",
        headers={"Authorization": "Bearer verified-browser-token"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "APPEARANCE_SESSION_SCOPE_MISMATCH"


def test_appearance_look_edit_uses_verified_subject_and_does_not_expose_service_token(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_URL", "https://appearance.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_TOKEN", "appearance-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "status": "updated",
            "look": {
                "look_id": "appearance-look-edit-001",
                "subject_id": "verified-user-appearance",
                "version": 2,
                "current_version": 2,
                "operations": [{"component": "hair_colour"}],
            },
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/appearance/looks/appearance-look-edit-001/operations",
        headers={"Authorization": "Bearer verified-browser-token"},
        json={
            "subject_id": "untrusted-user",
            "expected_version": 1,
            "command_id": "appearance-edit-command-001",
            "operation": {
                "operation_id": "appearance-edit-operation-001",
                "component": "hair_colour",
                "action": "replace",
                "description": "Copper red",
            },
        },
    )
    assert response.status_code == 200, response.text
    assert fake.calls[1][2]["json"]["subject_id"] == "verified-user-appearance"
    assert response.json()["look"]["version"] == 2
    assert "appearance-internal-token" not in response.text



def test_appearance_consent_renewal_uses_verified_subject_and_source_scopes(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_URL", "https://appearance.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_TOKEN", "appearance-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "look_id": "appearance-renew-source-001",
            "subject_id": "verified-user-appearance",
            "base_kind": "source_photo",
            "required_scopes": ["appearance_session_storage", "appearance_source_storage", "image_processing"],
        }),
        FakeResponse({
            "receipt_id": "renew-session-receipt",
            "consent_id": "renewed-look-bundle",
            "resource_id": "appearance-renew-source-001",
            "granted": True,
        }),
        FakeResponse({
            "receipt_id": "renew-source-receipt",
            "consent_id": "renewed-look-bundle",
            "resource_id": "appearance-renew-source-001",
            "granted": True,
        }),
        FakeResponse({
            "receipt_id": "renew-image-processing-receipt",
            "consent_id": "renewed-look-bundle",
            "resource_id": "appearance-renew-source-001",
            "granted": True,
        }),
        FakeResponse({
            "status": "renewed",
            "look_id": "appearance-renew-source-001",
            "consent_version": "appearance-look-session-v1",
            "granted_scopes": ["appearance_session_storage", "appearance_source_storage", "image_processing"],
        }),
    ])
    fake.auto_echo_identity_consent = True
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/appearance/consents/renew",
        headers={"Authorization": "Bearer browser-token"},
        json={
            "look_id": "appearance-renew-source-001",
            "accept_session_storage": True,
            "accept_source_storage": True,
            "accept_image_processing": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["granted_scopes"] == [
        "appearance_session_storage", "appearance_source_storage", "image_processing",
    ]
    assert fake.calls[0][1] == "https://commerce.example.test/me"
    context_call = fake.calls[1]
    assert context_call[1] == "https://appearance.example.test/internal/v1/looks/appearance-renew-source-001/consent-context"
    assert context_call[2]["params"]["subject_id"] == "verified-user-appearance"
    grants = [call for call in fake.calls if call[1] == "https://identity.example.test/v1/tal/consents"]
    assert [call[2]["json"]["scope"] for call in grants] == [
        "appearance_session_storage", "appearance_source_storage", "image_processing",
    ]
    assert all(call[2]["json"]["resource_id"] == "appearance-renew-source-001" for call in grants)
    renew_call = fake.calls[-1]
    assert renew_call[1] == "https://appearance.example.test/internal/v1/looks/appearance-renew-source-001/renew-consent"
    assert renew_call[2]["json"]["subject_id"] == "verified-user-appearance"
    assert "appearance-internal-token" not in response.text
    assert "identity-internal-token" not in response.text


def test_appearance_consent_renewal_for_twin_does_not_grant_source_storage(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_URL", "https://appearance.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_TOKEN", "appearance-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "look_id": "appearance-renew-twin-001",
            "subject_id": "verified-user-appearance",
            "base_kind": "virtual_twin",
            "required_scopes": ["appearance_session_storage"],
        }),
        FakeResponse({
            "receipt_id": "renew-twin-session-receipt",
            "consent_id": "renewed-twin-bundle",
            "resource_id": "appearance-renew-twin-001",
            "granted": True,
        }),
        FakeResponse({
            "status": "renewed",
            "look_id": "appearance-renew-twin-001",
            "consent_version": "appearance-look-session-v1",
            "granted_scopes": ["appearance_session_storage"],
        }),
    ])
    fake.auto_echo_identity_consent = True
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/appearance/consents/renew",
        headers={"Authorization": "Bearer browser-token"},
        json={
            "look_id": "appearance-renew-twin-001",
            "accept_session_storage": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["granted_scopes"] == ["appearance_session_storage"]
    grants = [call for call in fake.calls if call[1] == "https://identity.example.test/v1/tal/consents"]
    assert len(grants) == 1
    assert grants[0][2]["json"]["scope"] == "appearance_session_storage"


def test_appearance_source_renewal_requires_explicit_image_processing_acceptance(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_URL", "https://appearance.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_TOKEN", "appearance-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "look_id": "appearance-renew-source-003",
            "subject_id": "verified-user-appearance",
            "base_kind": "source_photo",
            "required_scopes": [
                "appearance_session_storage", "appearance_source_storage", "image_processing",
            ],
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/appearance/consents/renew",
        headers={"Authorization": "Bearer browser-token"},
        json={
            "look_id": "appearance-renew-source-003",
            "accept_session_storage": True,
            "accept_source_storage": True,
            "accept_image_processing": False,
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "APPEARANCE_IMAGE_PROCESSING_CONSENT_REQUIRED"
    assert len(fake.calls) == 2


def test_appearance_source_renewal_requires_explicit_source_storage_acceptance(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_URL", "https://appearance.example.test")
    monkeypatch.setenv("APPEARANCE_SERVICE_TOKEN", "appearance-internal-token-more-than-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "verified-user-appearance"}),
        FakeResponse({
            "look_id": "appearance-renew-source-002",
            "subject_id": "verified-user-appearance",
            "base_kind": "source_photo",
            "required_scopes": ["appearance_session_storage", "appearance_source_storage", "image_processing"],
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/appearance/consents/renew",
        headers={"Authorization": "Bearer browser-token"},
        json={
            "look_id": "appearance-renew-source-002",
            "accept_session_storage": True,
            "accept_source_storage": False,
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "APPEARANCE_SOURCE_STORAGE_CONSENT_REQUIRED"
    assert len(fake.calls) == 2


def test_developer_token_entry_requires_explicit_nonproduction_opt_in(client, monkeypatch):
    monkeypatch.setenv("MARKETPLACE_ENVIRONMENT", "development")
    monkeypatch.setenv("MARKETPLACE_ENABLE_DEVELOPER_TOKEN_INPUT", "true")
    response = client.get("/")
    assert response.status_code == 200
    assert 'allowDeveloperTokenInput:true' in response.text
    assert "Signed customer test token" in response.text

def test_production_never_renders_developer_token_entry_even_when_opted_in(client, monkeypatch):
    monkeypatch.setenv("MARKETPLACE_ENVIRONMENT", "production")
    monkeypatch.setenv("MARKETPLACE_ENABLE_DEVELOPER_TOKEN_INPUT", "true")
    response = client.get("/")
    assert response.status_code == 200
    assert 'allowDeveloperTokenInput:false' in response.text
    assert "Signed customer test token" in response.text
    assert "Account sign-in is unavailable" in response.text

def test_cart_proxy_requires_bearer_before_cal_readiness_probe(client, monkeypatch):
    configure_upstreams(monkeypatch)
    monkeypatch.setenv("COMMERCE_CAL_PURCHASE_PROXY_ENABLED", "true")
    fake = FakeAsyncClient([])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)

    response = client.get("/api/commerce/cart")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "USER_BEARER_REQUIRED"
    assert fake.calls == []


def test_invalid_customer_token_is_rejected_before_cal_readiness_probe(client, monkeypatch):
    configure_upstreams(monkeypatch)
    monkeypatch.setenv("COMMERCE_CAL_PURCHASE_PROXY_ENABLED", "true")
    fake = FakeAsyncClient([FakeResponse({"detail": "expired"}, status_code=401)])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)

    response = client.get(
        "/api/commerce/cart",
        headers={"Authorization": "Bearer expired-customer-token"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "USER_AUTHENTICATION_FAILED"
    assert [call[1] for call in fake.calls] == ["https://commerce.example.test/me"]

def test_cart_and_checkout_proxy_only_when_operator_flag_and_live_cal_readiness_pass(client, monkeypatch):
    configure_upstreams(monkeypatch)
    monkeypatch.setenv("COMMERCE_CAL_PURCHASE_PROXY_ENABLED", "true")
    readiness = {
        "ready": True,
        "cal_purchase_gateway_configured": True,
        "cal_purchase_receipt_signer_configured": True,
        "cal_gateway_ready": True,
        "migrations_applied": True,
    }
    capabilities = {"candidate_bound_purchase_authorization_configured": True}
    fake = FakeAsyncClient([])
    for _ in range(4):
        fake.responses.extend([
            FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
            FakeResponse(readiness),
            FakeResponse(capabilities),
            FakeResponse({"accepted": True}),
        ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    headers = {"Authorization": "Bearer customer-token", "Content-Type": "application/json"}
    variant = "123e4567-e89b-12d3-a456-426614174000"

    responses = [
        client.get("/api/commerce/cart", headers=headers),
        client.post("/api/commerce/cart/items", headers=headers, json={"variant_id": variant, "quantity": 1}),
        client.patch(f"/api/commerce/cart/items/{variant}", headers=headers, json={"quantity": 2}),
        client.post("/api/commerce/checkout", headers={**headers, "Idempotency-Key": "cal-proxy-checkout-01"}, json={"confirm": True}),
    ]
    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    assert [call[0] for call in fake.calls] == [
        "GET", "GET", "GET", "GET",
        "GET", "GET", "GET", "POST",
        "GET", "GET", "GET", "PATCH",
        "GET", "GET", "GET", "POST",
    ]
    expected_urls = [
        "https://commerce.example.test/me",
        "https://commerce.example.test/ready",
        "https://commerce.example.test/capabilities",
        "https://commerce.example.test/cart",
        "https://commerce.example.test/me",
        "https://commerce.example.test/ready",
        "https://commerce.example.test/capabilities",
        "https://commerce.example.test/cart/items",
        "https://commerce.example.test/me",
        "https://commerce.example.test/ready",
        "https://commerce.example.test/capabilities",
        f"https://commerce.example.test/cart/items/{variant}",
        "https://commerce.example.test/me",
        "https://commerce.example.test/ready",
        "https://commerce.example.test/capabilities",
        "https://commerce.example.test/checkout",
    ]
    assert [call[1] for call in fake.calls] == expected_urls
    forwarded = [call for call in fake.calls if call[1] in {
        "https://commerce.example.test/cart",
        "https://commerce.example.test/cart/items",
        f"https://commerce.example.test/cart/items/{variant}",
        "https://commerce.example.test/checkout",
    }]
    assert all(call[2]["headers"]["Authorization"] == "Bearer customer-token" for call in forwarded)


def test_cart_and_checkout_remain_blocked_when_live_cal_readiness_is_incomplete(client, monkeypatch):
    configure_upstreams(monkeypatch)
    monkeypatch.setenv("COMMERCE_CAL_PURCHASE_PROXY_ENABLED", "true")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer"}),
        FakeResponse({
            "ready": False,
            "cal_purchase_gateway_configured": True,
            "cal_purchase_receipt_signer_configured": True,
            "cal_gateway_ready": False,
            "migrations_applied": True,
        }, status_code=503),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/commerce/checkout",
        headers={"Authorization": "Bearer customer-token", "Content-Type": "application/json"},
        json={"confirm": True},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CAL_CANDIDATE_PURCHASE_REAUTH_REQUIRED"
    assert [call[1] for call in fake.calls] == [
        "https://commerce.example.test/me",
        "https://commerce.example.test/ready",
    ]
def test_pnelly_conversational_discovery_delegates_to_wardrobe_cal_pipeline(client, monkeypatch):
    seen = {}

    async def fake_wardrobe_recommendations(request, payload):
        seen["path"] = request.url.path
        seen["query"] = payload.query
        seen["occasion"] = payload.occasion
        seen["climate"] = payload.climate
        return main.JSONResponse(
            content={
                "display_authority": "CaTaCaCi/CAL",
                "displayable_products": [],
                "withheld_candidate_count": 2,
                "wardrobe_context": {"used": True},
            },
            headers={"Cache-Control": "no-store, private"},
        )

    monkeypatch.setattr(main, "wardrobe_recommendations", fake_wardrobe_recommendations)
    response = client.post(
        "/api/vision/conversational-discovery",
        headers={"Authorization": "Bearer signed-user-session"},
        json={
            "query": "a light layer that works with my blue shirt",
            "occasion": "work",
            "climate": "hot_humid",
            "limit": 10,
            "exclude_owned_products": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["display_authority"] == "CaTaCaCi/CAL"
    assert response.json()["wardrobe_context"]["used"] is True
    assert seen == {
        "path": "/api/vision/conversational-discovery",
        "query": "a light layer that works with my blue shirt",
        "occasion": "work",
        "climate": "hot_humid",
    }


def test_complementer_request_id_is_a_controlled_nonblank_identifier():
    valid = main.ComplementerRequestIn(request_id="pnelly-request-001")
    assert valid.request_id == "pnelly-request-001"

    for invalid in ("        ", "short", "request id with spaces", "x" * 129):
        with pytest.raises(ValidationError):
            main.ComplementerRequestIn(request_id=invalid)


def test_image_rights_request_can_be_submitted_without_uploader_login_and_quarantines_urgent_report(client, monkeypatch):
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_URL", "https://privacy-rights.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_TOKEN", "privacy-rights-internal-token-at-least-32-bytes")
    fake = FakeAsyncClient([FakeResponse({
        "request_id": "rights-request-0001",
        "status": "quarantined",
        "quarantined": True,
        "status_token": "opaque-request-status-token-0001",
    }, status_code=202)])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post("/api/privacy/image-requests", json={
        "asset_reference": "cirvanna-share-1234",
        "request_type": "report",
        "reason_code": "possible_minor",
        "requester_relationship": "parent_guardian",
        "jurisdiction_hint": "Example Region",
    })
    assert response.status_code == 202
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["quarantined"] is True
    assert len(response.json()["status_token"]) >= 24
    assert fake.calls[0][1].endswith("/internal/v1/image-rights/requests")
    payload = fake.calls[0][2]["json"]
    assert payload["jurisdiction_hint_is_unverified"] is True
    assert payload["asset_reference"] == "cirvanna-share-1234"
    assert "image_bytes" not in payload
    assert "identity_document" not in payload

def test_image_rights_urgent_report_is_not_accepted_without_quarantine_confirmation(client, monkeypatch):
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_URL", "https://privacy-rights.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_TOKEN", "privacy-rights-internal-token-at-least-32-bytes")
    fake = FakeAsyncClient([FakeResponse({
        "request_id": "rights-request-0002",
        "status": "accepted",
        "quarantined": False,
    }, status_code=202)])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post("/api/privacy/image-requests", json={
        "asset_reference": "cirvanna-share-5678",
        "request_type": "removal",
        "reason_code": "unmasked_face",
        "requester_relationship": "photographed_person",
    })
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "IMAGE_RIGHTS_QUARANTINE_NOT_CONFIRMED"

def test_image_rights_intake_fails_closed_when_provider_is_not_configured(client, monkeypatch):
    monkeypatch.delenv("PRIVACY_GOVERNANCE_API_URL", raising=False)
    monkeypatch.delenv("PRIVACY_GOVERNANCE_API_TOKEN", raising=False)
    response = client.post("/api/privacy/image-requests", json={
        "asset_reference": "cirvanna-share-9012",
        "request_type": "removal",
        "reason_code": "privacy_concern",
        "requester_relationship": "photographed_person",
    })
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PRIVACY_GOVERNANCE_API_URL_NOT_CONFIGURED"

def test_image_rights_intake_rejects_arbitrary_urls_and_unknown_fields(client):
    response = client.post("/api/privacy/image-requests", json={
        "asset_reference": "https://attacker.example/image.jpg",
        "request_type": "removal",
        "reason_code": "privacy_concern",
        "requester_relationship": "photographed_person",
        "image_bytes": "should-not-be-accepted",
    })
    assert response.status_code == 422

def test_image_rights_status_uses_private_token_without_uploader_account(client, monkeypatch):
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_URL", "https://privacy-rights.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_TOKEN", "privacy-rights-internal-token-at-least-32-bytes")
    fake = FakeAsyncClient([FakeResponse({
        "request_id": "rights-request-0001",
        "status": "under_review",
        "quarantined": True,
        "updated_at": "2026-11-05T05:00:00Z",
        "triage_due_at": "2026-11-05T09:00:00Z",
        "legal_response_due_at": None,
        "deadline_basis": "jurisdiction_unresolved_platform_triage",
        "applicable_jurisdictions": [],
        "resolution_code": None,
        "requester_identity": "must-not-be-forwarded",
    })])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get(
        "/api/privacy/image-requests/rights-request-0001",
        headers={"X-Privacy-Request-Token": "opaque-request-status-token-123456"},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["status"] == "under_review"
    assert response.json()["quarantined"] is True
    assert response.json()["triage_due_at"] == "2026-11-05T09:00:00Z"
    assert response.json()["legal_response_due_at"] is None
    assert "requester_identity" not in response.text
    assert fake.calls[0][1] == "https://privacy-rights.example.test/internal/v1/image-rights/requests/rights-request-0001"
    assert fake.calls[0][2]["headers"]["X-Requester-Status-Token"] == "opaque-request-status-token-123456"

def test_image_rights_status_rejects_invalid_request_id(client):
    response = client.get(
        "/api/privacy/image-requests/bad.request.id",
        headers={"X-Privacy-Request-Token": "opaque-request-status-token-123456"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "IMAGE_RIGHTS_REQUEST_NOT_FOUND"

def test_image_rights_status_rejects_invalid_or_missing_status_token(client, monkeypatch):
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_URL", "https://privacy-rights.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_TOKEN", "privacy-rights-internal-token-at-least-32-bytes")
    response = client.get("/api/privacy/image-requests/rights-request-0001")
    assert response.status_code == 422

def test_image_rights_status_does_not_disclose_request_when_provider_rejects_token(client, monkeypatch):
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_URL", "https://privacy-rights.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_TOKEN", "privacy-rights-internal-token-at-least-32-bytes")
    fake = FakeAsyncClient([FakeResponse({"detail": "not found"}, status_code=403)])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get(
        "/api/privacy/image-requests/rights-request-0001",
        headers={"X-Privacy-Request-Token": "wrong-private-status-token-123456"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "IMAGE_RIGHTS_REQUEST_NOT_FOUND"

def test_click_it_consent_is_created_from_verified_commerce_subject(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_URL", "https://privacy.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_TOKEN", "privacy-governance-internal-token-at-least-32-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-customer-42"}),
        FakeResponse({
            "consent_id": "e340b1e2-7c6b-4cc2-9c0b-16dbf2e2a225",
            "active": True,
            "granted_scopes": ["image_processing", "click_it", "photographed_people_adult_attestation"],
            "photographed_people_status": "adults_only",
            "guardian_authority_verified": False,
            "consent_version": "click-it-privacy-v1",
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/privacy/consents",
        headers={"Authorization": "Bearer signed-shopper-token"},
        json={
            "consent_image_processing": True,
            "consent_click_it": True,
            "photographed_people_status": "adults_only",
            "photographed_people_consent_confirmed": True,
            "consent_version": "click-it-privacy-v1",
            "twin_id": "twin-123",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["active"] is True
    assert fake.calls[0][1] == "https://commerce.example.test/me"
    assert fake.calls[1][1] == "https://privacy.example.test/internal/v1/consents/grant"
    assert fake.calls[1][2]["json"]["subject_id"] == "signed-customer-42"
    assert fake.calls[1][2]["json"]["resource_id"] == "twin-123"
    assert "subject_id" not in response.text

def test_click_it_consent_can_only_grant_guardian_scope_via_external_reference(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_URL", "https://privacy.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_TOKEN", "privacy-governance-internal-token-at-least-32-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-parent-42"}),
        FakeResponse({
            "consent_id": "e340b1e2-7c6b-4cc2-9c0b-16dbf2e2a226",
            "active": True,
            "granted_scopes": ["image_processing", "click_it", "photographed_people_minor_attestation", "guardian_authorized"],
            "photographed_people_status": "contains_minor",
            "guardian_authority_verified": True,
            "consent_version": "click-it-privacy-v1",
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/privacy/consents",
        headers={"Authorization": "Bearer signed-parent-token"},
        json={
            "consent_image_processing": True,
            "consent_click_it": True,
            "photographed_people_status": "contains_minor",
            "photographed_people_consent_confirmed": True,
            "consent_version": "click-it-privacy-v1",
            "guardian_verification_reference": "verified-guardian-case-123",
        },
    )
    assert response.status_code == 200
    assert response.json()["guardian_authority_verified"] is True
    assert fake.calls[1][2]["json"]["guardian_verification_reference"] == "verified-guardian-case-123"

def test_click_it_consent_requires_signed_account_and_both_explicit_acceptances(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: calls.append(kwargs))
    response = client.post(
        "/api/privacy/consents",
        json={
            "consent_image_processing": True,
            "consent_click_it": True,
            "photographed_people_status": "adults_only",
            "photographed_people_consent_confirmed": True,
            "consent_version": "click-it-privacy-v1",
        },
    )
    assert response.status_code == 401
    assert not calls
    response = client.post(
        "/api/privacy/consents",
        headers={"Authorization": "Bearer signed-shopper-token"},
        json={
            "consent_image_processing": True,
            "consent_click_it": False,
            "photographed_people_status": "adults_only",
            "photographed_people_consent_confirmed": True,
            "consent_version": "click-it-privacy-v1",
        },
    )
    assert response.status_code == 403
    assert not calls

def test_consent_revocation_is_subject_bound_to_verified_commerce_session(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_URL", "https://privacy.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_TOKEN", "privacy-governance-internal-token-at-least-32-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-customer-42"}),
        FakeResponse({"consent_id": "e340b1e2-7c6b-4cc2-9c0b-16dbf2e2a227", "active": False, "revoked": True}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/privacy/consents/e340b1e2-7c6b-4cc2-9c0b-16dbf2e2a227/revoke",
        headers={"Authorization": "Bearer signed-shopper-token"},
        json={"reason_code": "user_request"},
    )
    assert response.status_code == 200
    assert response.json()["revoked"] is True
    assert fake.calls[1][1] == "https://privacy.example.test/internal/v1/consents/e340b1e2-7c6b-4cc2-9c0b-16dbf2e2a227/revoke"
    assert fake.calls[1][2]["json"]["subject_id"] == "signed-customer-42"

def test_consent_revocation_rejects_missing_user_auth_before_upstream(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: calls.append(kwargs))
    response = client.post(
        "/api/privacy/consents/e340b1e2-7c6b-4cc2-9c0b-16dbf2e2a227/revoke",
        json={"reason_code": "user_request"},
    )
    assert response.status_code == 401
    assert not calls

def test_click_it_consent_rejects_provider_receipt_missing_required_scope(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_URL", "https://privacy.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_TOKEN", "privacy-governance-internal-token-at-least-32-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-customer-42"}),
        FakeResponse({
            "consent_id": "e340b1e2-7c6b-4cc2-9c0b-16dbf2e2a228",
            "active": True,
            "granted_scopes": ["image_processing", "photographed_people_adult_attestation"],
            "photographed_people_status": "adults_only",
            "guardian_authority_verified": False,
            "consent_version": "click-it-privacy-v1",
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/privacy/consents",
        headers={"Authorization": "Bearer signed-shopper-token"},
        json={
            "consent_image_processing": True,
            "consent_click_it": True,
            "photographed_people_status": "adults_only",
            "photographed_people_consent_confirmed": True,
            "consent_version": "click-it-privacy-v1",
        },
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "CONSENT_CREATION_INVALID_RESPONSE"


def test_click_it_revocation_rejects_mismatched_provider_receipt(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_URL", "https://privacy.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_TOKEN", "privacy-governance-internal-token-at-least-32-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-customer-42"}),
        FakeResponse({"consent_id": "00000000-0000-4000-8000-000000000000", "active": False, "revoked": True}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/privacy/consents/e340b1e2-7c6b-4cc2-9c0b-16dbf2e2a227/revoke",
        headers={"Authorization": "Bearer signed-shopper-token"},
        json={"reason_code": "user_request"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "CONSENT_REVOCATION_RESPONSE_INVALID"



def test_bff_and_identity_service_use_the_same_pnelly_preference_taxonomy():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    identity_tree = ast.parse((root / "services/identity-learning-service/app/main.py").read_text())
    bff_tree = ast.parse((root / "services/marketplace-bff/app/pnelly_preferences.py").read_text())

    identity_values = None
    for node in identity_tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "PNELLY_CONFIRMED_PROFILE_ATTRIBUTES"
            for target in node.targets
        ):
            identity_values = set(ast.literal_eval(node.value))
            break

    bff_values = None
    for node in bff_tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "PnellyStyleAttribute"
            for target in node.targets
        ):
            annotation = node.value
            if isinstance(annotation, ast.Subscript) and isinstance(annotation.slice, ast.Tuple):
                bff_values = set(ast.literal_eval(value) for value in annotation.slice.elts)
            break

    assert identity_values is not None
    assert bff_values is not None
    assert bff_values == identity_values


def test_cal_discovery_envelope_requires_authority_request_id_and_complete_counts():
    valid = {
        "request_id": "req-envelope-1",
        "display_authority": "CaTaCaCi/CAL",
        "displayable_products": [],
        "withheld_candidate_ids": [],
        "ranked_candidate_count": 0,
    }
    assert main._validate_cal_discovery_envelope(valid, error_code="INVALID")[2:] == (0, "req-envelope-1")
    invalid_payloads = [
        {**valid, "request_id": " "},
        {**valid, "display_authority": "commerce"},
        {**valid, "withheld_candidate_ids": None},
        {**valid, "ranked_candidate_count": True},
        {**valid, "ranked_candidate_count": -1},
        {**valid, "ranked_candidate_count": -1},
    ]
    for payload in invalid_payloads:
        with pytest.raises(main.HTTPException) as exc:
            main._validate_cal_discovery_envelope(payload, error_code="INVALID")
        assert exc.value.status_code == 502
        assert exc.value.detail["code"] == "INVALID"
