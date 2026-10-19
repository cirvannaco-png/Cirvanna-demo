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
    monkeypatch.setenv("CATALOG_API_TOKEN", "catalog-server-only-test-token")
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
    monkeypatch.setattr(main.httpx, "get", lambda *args, **kwargs: FakeResponse({"ready": True}))
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    assert ready.json()["catalog_ready"] is True
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
