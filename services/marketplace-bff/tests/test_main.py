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
        return FakeResponse({"items": [{"variant_id": "v1"}], "total": 1, "offset": 0, "limit": 20})

    monkeypatch.setattr(main.httpx, "get", fake_get)
    response = client.get("/api/commerce/marketplace/offers?q=linen&category=Fashion&offset=20&limit=10")
    assert response.status_code == 200
    assert response.json()["total"] == 1
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


def test_description_search_forwards_to_legacy_tari_alias_and_keeps_candidates_pending_cal(client, monkeypatch):
    monkeypatch.setenv("XARI_API_URL", "https://xari.example.test")
    monkeypatch.setenv("XARI_API_TOKEN", "xari-internal-token-at-least-thirty-two-bytes")
    fake = FakeAsyncClient([FakeResponse({
        "status": "complete",
        "query": "green linen dress",
        "candidate_count": 2,
        "candidates": [{"variant_id": "offer-1", "product_name": "green dress"}],
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
            "candidates": [{"variant_id": "variant-3", "product_name": "linen shirt"}],
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



def test_look_it_requires_signed_user_token_before_any_upstream_call(client):
    response = client.post(
        "/api/vision/look-it",
        data={
            "consent_id": "look-consent-1234",
            "consent_image_processing": "true",
            "consent_look_it": "true",
        },
        files={"reference_image": ("sketch.png", b"not-used", "image/png")},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "USER_BEARER_REQUIRED"


def test_look_it_uses_verified_subject_and_dedicated_pnelly_endpoint(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("PNELLY_API_URL", "https://pnelly.example.test")
    monkeypatch.setenv("PNELLY_API_TOKEN", "pnelly-internal-token-at-least-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-77", "role": "customer"}),
        FakeResponse({
            "status": "complete",
            "search_mode": "pnelly_look_it_image_to_catalog_text_similarity",
            "candidate_count": 1,
            "candidates": [{"variant_id": "variant-look-1", "product_name": "blue dress"}],
            "display_authorized": False,
            "decision_status": "PENDING_CAL",
            "outfit_decomposition": {"status": "unavailable", "components": []},
            "merchant_comparison": {"status": "unavailable"},
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post(
        "/api/vision/look-it",
        headers={"Authorization": "Bearer signed-user-token"},
        data={
            "consent_id": "look-consent-1234",
            "consent_image_processing": "true",
            "consent_look_it": "true",
            "category": "dress",
            "limit": "5",
        },
        files={"reference_image": ("sketch.png", b"reference-image-bytes", "image/png")},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["display_authorized"] is False
    assert response.json()["decision_status"] == "PENDING_CAL"
    assert len(fake.calls) == 2
    assert fake.calls[0][1] == "https://commerce.example.test/me"
    assert fake.calls[1][1] == "https://pnelly.example.test/v1/marketplace/search/image"
    assert fake.calls[1][2]["data"]["subject_id"] == "signed-user-77"
    assert fake.calls[1][2]["data"]["consent_look_it"] == "true"
    assert fake.calls[1][2]["files"]["image"][1] == b"reference-image-bytes"
    assert "subject_id" not in response.request.content.decode(errors="ignore")


def test_pnelly_configuration_is_preferred_over_legacy_xari_aliases(client, monkeypatch):
    monkeypatch.setenv("PNELLY_API_URL", "https://pnelly.example.test")
    monkeypatch.setenv("PNELLY_API_TOKEN", "pnelly-internal-token-at-least-thirty-two-bytes")
    monkeypatch.setenv("XARI_API_URL", "https://legacy-xari.example.test")
    monkeypatch.setenv("XARI_API_TOKEN", "legacy-xari-token-at-least-thirty-two-bytes")
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
    assert fake.calls[0][1] == "https://pnelly.example.test/v1/marketplace/search"


def test_marketplace_ui_keeps_click_it_and_exposes_look_it_inside_pnelly(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="lookItForm"' in response.text
    assert 'id="lookItImage"' in response.text
    assert 'id="lookItConsentId"' in response.text
    assert 'fetch("/api/vision/look-it"' in response.text
    assert 'fetch("/api/vision/click-it"' in response.text
