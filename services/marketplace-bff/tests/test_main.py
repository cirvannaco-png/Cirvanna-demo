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
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_URL", "https://privacy.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_TOKEN", "privacy-governance-test-token-at-least-32-bytes")


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
        return FakeResponse({"order_id": "order-123", "image_url": "https://cdn.example.test/unmasked.jpg", "order": {"thumbnail_url": "https://cdn.example.test/private.jpg"}}, status_code=201)

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
    assert response.json()["image_url"] is None
    assert response.json()["order"]["thumbnail_url"] is None
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


def test_description_search_forwards_to_legacy_tari_alias_and_keeps_candidates_pending_cal(client, monkeypatch):
    monkeypatch.setenv("XARI_API_URL", "https://xari.example.test")
    monkeypatch.setenv("XARI_API_TOKEN", "xari-internal-token-at-least-thirty-two-bytes")
    fake = FakeAsyncClient([FakeResponse({
        "status": "complete",
        "query": "green linen dress",
        "candidate_count": 2,
        "candidates": [{"variant_id": "offer-1", "product_name": "green dress", "image_url": "https://cdn.example.test/unmasked.jpg", "thumbnail_url": "https://cdn.example.test/thumbnail.jpg", "image_asset_id": "private-asset-1", "details": {"photo_url": "https://cdn.example.test/photo.jpg"}}],
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
    candidate = data["candidates"][0]
    assert candidate["image_url"] is None
    assert candidate["thumbnail_url"] is None
    assert candidate["image_asset_id"] is None
    assert candidate["details"]["photo_url"] is None
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
            "candidates": [{"variant_id": "variant-3", "product_name": "linen shirt", "render_url": "https://cdn.example.test/render.png", "media": {"photo_asset_id": "asset-private", "src": "https://cdn.example.test/private-src.jpg", "type": "image"}, "assets": [{"url": "https://cdn.example.test/asset.jpg", "storage_key": "private-key", "type": "image"}], "gallery": [{"href": "https://cdn.example.test/gallery.jpg", "caption": "look"}]}],
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
            "photographed_people_status": "adults_only",
            "capture_jurisdiction_hint": "Unverified Capture Region",
        },
        files={"product_image": ("dress.png", b"validated-photo-bytes", "image/png")},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["display_authorized"] is False
    assert response.json()["candidates"][0]["variant_id"] == "variant-3"
    assert response.json()["candidates"][0]["render_url"] is None
    assert response.json()["candidates"][0]["media"]["photo_asset_id"] is None
    assert response.json()["candidates"][0]["media"]["src"] is None
    assert response.json()["candidates"][0]["media"]["type"] == "image"
    assert response.json()["candidates"][0]["assets"][0]["url"] is None
    assert response.json()["candidates"][0]["assets"][0]["storage_key"] is None
    assert response.json()["candidates"][0]["assets"][0]["type"] == "image"
    assert response.json()["candidates"][0]["gallery"][0]["href"] is None
    assert response.json()["candidates"][0]["gallery"][0]["caption"] == "look"
    assert len(fake.calls) == 2
    assert fake.calls[0][1] == "https://commerce.example.test/me"
    assert fake.calls[1][1] == "https://virtual-twin.example.test/click-it"
    assert fake.calls[1][2]["data"]["subject_id"] == "signed-user-42"
    assert fake.calls[1][2]["data"]["photographed_people_status"] == "adults_only"
    assert fake.calls[1][2]["data"]["capture_jurisdiction_hint"] == "Unverified Capture Region"
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
            "photographed_people_status": "no_people",
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
    assert 'id="clickItPeopleStatus"' in response.text
    assert 'id="clickItGuardianVerificationRef"' in response.text
    assert 'id="clickItPeopleConsent"' in response.text
    assert 'photographed_people_consent_confirmed:$("clickItPeopleConsent").checked' in response.text
    assert 'id="clickItRevokeConsentBtn"' in response.text
    assert 'const twinResourceAllowed=photographedPeopleStatus!=="contains_minor"' in response.text
    assert 'if(twinId&&twinResourceAllowed)consentPayload.twin_id=twinId' in response.text
    assert 'form.append("consent_id",$("clickItConsentId").value.trim())' not in response.text
    assert 'fetch("/api/privacy/consents"' in response.text
    assert 'id="clickItCaptureJurisdiction"' in response.text
    assert 'id="imageRightsForm"' in response.text
    assert 'fetch("/api/privacy/image-requests"' in response.text
    assert 'id="imageRightsStatusForm"' in response.text
    assert 'X-Privacy-Request-Token' in response.text
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
            "items": [{"owner_user_id": "signed-user-42", "item_id": "closet-1", "status": "active", "image_asset_id": "private-asset-1", "image_url": "https://cdn.example.test/private.jpg", "assets": [{"url": "https://cdn.example.test/nested.jpg", "storage_key": "private-key"}]}],
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get("/api/wardrobe/items", headers={"Authorization": "Bearer signed-session"})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["items"][0]["item_id"] == "closet-1"
    assert response.json()["items"][0]["image_asset_id"] is None
    assert response.json()["items"][0]["image_url"] is None
    assert response.json()["items"][0]["assets"][0]["url"] is None
    assert response.json()["items"][0]["assets"][0]["storage_key"] is None
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
            "ranked_candidate_count": 0,
            "displayable_products": [{
                "product": {"product_id": "p1", "image_urls": ["https://cdn.example.test/unmasked-product.jpg"], "image_url": "https://cdn.example.test/product.jpg"},
                "offer": {"variant_id": "v1", "image_urls": ["https://cdn.example.test/unmasked-offer.jpg"], "media_url": "https://cdn.example.test/offer.jpg"},
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
    assert response.json()["displayable_products"][0]["product"]["image_urls"] == []
    assert response.json()["displayable_products"][0]["offer"]["image_urls"] == []
    assert response.json()["displayable_products"][0]["product"]["image_url"] is None
    assert response.json()["displayable_products"][0]["offer"]["media_url"] is None
    assert "Authorization" not in response.text


def test_wardrobe_page_exposes_feedback_and_consent_controls(client):
    response = client.get("/wardrobe")
    assert response.status_code == 200
    assert "Enable style learning" in response.text
    assert "Dislike" in response.text
    assert "Avoid" in response.text
    assert "/api/wardrobe/recommendations" in response.text
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
            "version": 2, "status": "active", "image_asset_id": "unverified-asset-2",
            "thumbnail_url": "https://cdn.example.test/preview.jpg",
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
    assert response.json()["item"]["image_asset_id"] is None
    assert response.json()["item"]["thumbnail_url"] is None
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



def test_readiness_reports_click_it_privacy_provider_separately(client, monkeypatch):
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_URL", "https://privacy.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_TOKEN", "privacy-governance-internal-token-at-least-32-bytes")
    monkeypatch.setattr(main, "_upstream_ready", lambda base: base == "https://privacy.example.test")
    monkeypatch.setattr(main, "_upstream_base", lambda key: {
        "CATALOG_API_URL": "https://catalog.example.test",
        "COMMERCE_API_URL": "https://commerce.example.test",
        "PRIVACY_GOVERNANCE_API_URL": "https://privacy.example.test",
    }[key])
    response = client.get("/ready")
    assert response.status_code == 503  # catalog/Commerce are intentionally not ready in this test
    assert response.json()["detail"]["privacy_governance_configured"] is True
    assert response.json()["detail"]["privacy_governance_ready"] is True


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



def test_click_it_refuses_to_bind_a_minor_photo_to_any_virtual_twin(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: calls.append(kwargs))
    response = client.post(
        "/api/privacy/consents",
        headers={"Authorization": "Bearer signed-parent-token"},
        json={
            "consent_image_processing": True,
            "consent_click_it": True,
            "photographed_people_status": "contains_minor",
            "consent_version": "click-it-privacy-v1",
            "twin_id": "twin-123",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CHILD_TWIN_PERSONALIZATION_DISABLED"
    assert not calls



def test_click_it_rejects_unknown_people_status_before_buffering_or_upstream_calls(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: calls.append(kwargs))
    response = client.post(
        "/api/vision/click-it",
        headers={"Authorization": "Bearer signed-user-token"},
        data={
            "consent_id": "consent-record-1234",
            "consent_image_processing": "true",
            "consent_click_it": "true",
            "photographed_people_status": "unknown",
        },
        files={"product_image": ("photo.png", b"photo-bytes", "image/png")},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CHILD_SAFETY_STATUS_UNCONFIRMED"
    assert not calls

