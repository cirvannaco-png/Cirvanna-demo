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


def test_public_offers_fail_closed_until_cal_governance_is_configured(client, monkeypatch):
    configure_upstreams(monkeypatch)
    monkeypatch.delenv("GOVERNANCE_EVIDENCE_API_URL", raising=False)
    monkeypatch.delenv("GOVERNANCE_EVIDENCE_API_TOKEN", raising=False)
    monkeypatch.delenv("DECISION_SERVICE_API_URL", raising=False)
    monkeypatch.delenv("DECISION_SERVICE_TOKEN", raising=False)
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42"}),
        FakeResponse({"items": [{"variant_id": "v-1", "product_name": "linen shirt"}], "total": 1, "offset": 20, "limit": 10}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.get(
        "/api/commerce/marketplace/offers?q=linen&category=Fashion&offset=20&limit=10",
        headers={"Authorization": "Bearer signed-user-token"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CAL_GOVERNANCE_NOT_ENFORCED"
    assert "linen shirt" not in response.text
    assert [call[1] for call in fake.calls] == [
        "https://commerce.example.test/me",
        "https://commerce.example.test/marketplace/offers",
    ]


@pytest.mark.parametrize("path,method", [
    ("/api/commerce/cart", "GET"),
    ("/api/commerce/cart/items", "POST"),
    ("/api/commerce/cart/items/123e4567-e89b-42d3-a456-426614174000", "PATCH"),
    ("/api/commerce/saved-products", "GET"),
    ("/api/commerce/saved-products/123e4567-e89b-42d3-a456-426614174000", "DELETE"),
    ("/api/commerce/orders", "GET"),
    ("/api/commerce/orders/123e4567-e89b-42d3-a456-426614174000", "GET"),
    ("/api/commerce/checkout", "POST"),
])
def test_customer_account_and_checkout_routes_forward_to_commerce(client, monkeypatch, path, method):
    configure_upstreams(monkeypatch)
    calls = []
    def fake_request(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeResponse({"ok": True})
    monkeypatch.setattr(main.httpx, "request", fake_request)
    response = client.request(method, path, headers={"Authorization": "Bearer signed-user-token", "Idempotency-Key": "checkout-test-key"}, json={} if method == "POST" else None)
    assert response.status_code == 200, response.text
    assert len(calls) == 1
    assert calls[0][0][0] == method
    assert calls[0][0][1] == "https://commerce.example.test/" + path.removeprefix("/api/commerce/")
    assert calls[0][1]["headers"]["Authorization"] == "Bearer signed-user-token"
    assert "cookie" not in {key.lower() for key in calls[0][1]["headers"]}


def test_account_proxy_requires_bearer_and_blocks_admin_routes(client, monkeypatch):
    configure_upstreams(monkeypatch)
    calls = []
    monkeypatch.setattr(main.httpx, "request", lambda *args, **kwargs: calls.append(args) or FakeResponse({}))
    assert client.get("/api/commerce/cart").status_code == 401
    denied = client.get("/api/commerce/admin/inventory/audit", headers={"Authorization": "Bearer customer-token"})
    assert denied.status_code == 404
    assert calls == []


def test_checkout_proxy_forwards_to_commerce_for_transaction_time_cal_revalidation(client, monkeypatch):
    configure_upstreams(monkeypatch)
    seen = []
    monkeypatch.setattr(main.httpx, "request", lambda *args, **kwargs: seen.append((args, kwargs)) or FakeResponse({"checkout": "handled-by-commerce"}))
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
    assert response.status_code == 200
    assert response.json()["checkout"] == "handled-by-commerce"
    assert len(seen) == 1
    assert seen[0][1]["headers"]["Authorization"] == "Bearer user-session-token"
    assert seen[0][1]["headers"]["Idempotency-Key"] == "checkout-test-key"
    assert "cookie" not in {key.lower() for key in seen[0][1]["headers"]}


def test_readiness_requires_catalog_commerce_and_cal_services(client, monkeypatch):
    configure_upstreams(monkeypatch)
    monkeypatch.setattr(main.httpx, "get", lambda *args, **kwargs: FakeResponse({"ready": True}))

    # Catalog and Commerce alone must never make the purchase-governance BFF ready.
    missing_cal = client.get("/ready")
    assert missing_cal.status_code == 503
    assert missing_cal.json()["detail"]["ready"] is False
    assert missing_cal.json()["detail"]["catalog_ready"] is True
    assert missing_cal.json()["detail"]["commerce_ready"] is True
    assert missing_cal.json()["detail"]["governance_evidence_ready"] is False
    assert missing_cal.json()["detail"]["decision_service_ready"] is False

    monkeypatch.setenv("GOVERNANCE_EVIDENCE_API_URL", "https://evidence.example.test")
    monkeypatch.setenv("GOVERNANCE_EVIDENCE_API_TOKEN", "evidence-service-token-at-least-thirty-two-bytes")
    monkeypatch.setenv("DECISION_SERVICE_API_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_SERVICE_TOKEN", "decision-service-token-at-least-thirty-two-bytes")
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    assert ready.json()["governance_evidence_ready"] is True
    assert ready.json()["decision_service_ready"] is True

    monkeypatch.setattr(main.httpx, "get", lambda *args, **kwargs: FakeResponse({"ready": False}, status_code=503))
    pending = client.get("/ready")
    assert pending.status_code == 503
    assert pending.json()["detail"]["ready"] is False


def test_external_upstream_must_use_https(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "http://commerce.example.test")
    response = client.get(
        "/api/commerce/marketplace/offers",
        headers={"Authorization": "Bearer signed-user-token"},
    )
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


def test_description_search_requires_verified_user_before_upstream_access(client, monkeypatch):
    monkeypatch.delenv("XARI_API_URL", raising=False)
    monkeypatch.delenv("XARI_API_TOKEN", raising=False)
    response = client.post("/api/vision/marketplace-search", json={"query": "blue linen summer dress"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "USER_BEARER_REQUIRED"


def test_description_search_forwards_to_xari_and_keeps_candidates_pending_cal(client, monkeypatch):
    monkeypatch.setenv("XARI_API_URL", "https://xari.example.test")
    monkeypatch.setenv("XARI_API_TOKEN", "xari-internal-token-at-least-thirty-two-bytes")
    fake = FakeAsyncClient([
        FakeResponse({"user_id": "signed-user-42", "role": "customer", "email": None}),
        FakeResponse({
            "status": "complete",
            "query": "green linen dress",
            "candidate_count": 2,
            "candidates": [{"variant_id": "offer-1", "product_name": "green dress"}],
            "display_authorized": True,
            "decision_status": "SHOW",
            "scores_are_probabilities": False,
        }),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: fake)
    response = client.post("/api/vision/marketplace-search", json={"query": " green   linen dress ", "limit": 5})
    assert response.status_code == 401
    response = client.post("/api/vision/marketplace-search", headers={"Authorization": "Bearer signed-user-token"}, json={"query": " green   linen dress ", "limit": 5})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["candidate_count"] == 0
    assert data["candidates"] == []
    assert data["display_authorized"] is False
    assert data["decision_status"] == "PENDING_CAL"
    assert data["governance_status"] == "CAL_GATE_NOT_CONNECTED"
    assert "offer-1" not in response.text
    assert "green dress" not in response.text
    assert fake.calls[0][1] == "https://commerce.example.test/me"
    assert fake.calls[1][1] == "https://xari.example.test/v1/marketplace/search"
    assert fake.calls[1][2]["json"]["query"] == "green linen dress"
    assert data["user_id"] == "signed-user-42"
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
            "display_authorized": True,
            "decision_status": "SHOW",
            "candidates": [{"variant_id": "variant-3", "product_name": "linen shirt"}],
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
    assert response.json()["candidates"] == []
    assert response.json()["decision_status"] == "PENDING_CAL"
    assert response.json()["governance_status"] == "CAL_GATE_NOT_CONNECTED"
    assert "variant-3" not in response.text
    assert "linen shirt" not in response.text
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
    assert 'cal_decision.verdict==="SHOW"' in response.text
    assert 'config.userToken)headers.Authorization="Bearer "+config.userToken' in response.text
    assert 'id="savedBtn" disabled' in response.text
    assert 'id="cartBtn" disabled' in response.text
    assert "config.commerceBase" not in response.text
    assert 'config.base+"/products"' not in response.text
    assert "Radiant Skin Serum" not in response.text
    assert 'fetch(config.commerceBase+"/checkout"' not in response.text
