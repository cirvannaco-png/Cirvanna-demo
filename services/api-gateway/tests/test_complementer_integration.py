from __future__ import annotations

from fastapi.testclient import TestClient

from app import main


GATEWAY_TOKEN = "integration-gateway-token"
COMPLEMENTER_TOKEN = "complementer-internal-token-with-at-least-32-bytes"
END_USER_TOKEN = "integration-customer-bearer"


def advisory_request():
    return {
        "request_id": "look-session-001",
        "user_id": "request-scoped-user-001",
        "preferences": {
            "aesthetics": ["elegant"],
            "favorite_colors": ["teal"],
            "favorite_fragrance_families": ["woody"],
        },
        "look": {
            "outfit_colors": ["navy"],
            "climate": "hot_humid",
            "occasion": "evening",
        },
    }


def upstream_result(body):
    return {
        "schema_version": "2.0",
        "contract_version": "2.0.0",
        "request_id": body["request_id"],
        "user_id": body["user_id"],
        "status": "ready",
        "palette": {},
        "colour_coordination": {},
        "fragrance": {},
        "earrings": {},
        "necklaces": {},
        "glasses": {},
        "other_accessories": {},
        "aesthetic": {},
        "look_completion": {},
        "next_inputs": [],
        "limits": ["Advisory styling only; no product display authority."],
        "persistence": "stateless_request_only",
    }


class FakeResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


class FakeHttpClient:
    def __init__(self, response, expected_body=None):
        self.response = response
        self.expected_body = expected_body

    def get(self, url, *, headers):
        assert url == "https://commerce.internal/me"
        assert headers["Authorization"] == f"Bearer {END_USER_TOKEN}"
        return FakeResponse(200, {"user_id": self.expected_body["user_id"]})

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, *, headers, json):
        assert url == "https://complementer.internal/v1/complementer/recommend"
        assert headers["Authorization"] == f"Bearer {COMPLEMENTER_TOKEN}"
        assert json == self.expected_body
        return self.response


def configure_complementer(monkeypatch):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", GATEWAY_TOKEN)
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.internal")
    monkeypatch.setenv("COMPLEMENTER_SERVICE_URL", "https://complementer.internal")
    monkeypatch.setenv("COMPLEMENTER_SERVICE_TOKEN", COMPLEMENTER_TOKEN)


def test_gateway_complementer_proxy_requires_gateway_authentication(monkeypatch):
    configure_complementer(monkeypatch)
    with TestClient(main.app) as client:
        response = client.post("/v1/complementer/recommend", json=advisory_request())
    assert response.status_code == 401



def test_gateway_complementer_proxy_requires_verified_end_user_token(monkeypatch):
    configure_complementer(monkeypatch)
    with TestClient(main.app) as client:
        response = client.post(
            "/v1/complementer/recommend",
            headers={"Authorization": f"Bearer {GATEWAY_TOKEN}"},
            json=advisory_request(),
        )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "END_USER_BEARER_REQUIRED"


def test_gateway_complementer_proxy_calls_contract_and_remains_advisory(monkeypatch):
    configure_complementer(monkeypatch)
    body = advisory_request()
    response_payload = upstream_result(body)

    class Client(FakeHttpClient):
        def __init__(self, *args, **kwargs):
            super().__init__(FakeResponse(200, response_payload), expected_body=body)

    with TestClient(main.app) as client:
        monkeypatch.setattr(main.httpx, "Client", Client)
        response = client.post(
            "/v1/complementer/recommend",
            headers={
                "Authorization": f"Bearer {GATEWAY_TOKEN}",
                "X-End-User-Authorization": f"Bearer {END_USER_TOKEN}",
            },
            json=body,
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["mode"] == "advisory_only"
    assert result["display_authorized"] is False
    assert result["durable_personal_memory"] is False
    assert result["recommendation"]["request_id"] == body["request_id"]
    assert result["recommendation"]["user_id"] == body["user_id"]


def test_gateway_fails_closed_when_complementer_is_not_configured(monkeypatch):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", GATEWAY_TOKEN)
    monkeypatch.delenv("COMPLEMENTER_SERVICE_URL", raising=False)
    monkeypatch.delenv("COMPLEMENTER_SERVICE_TOKEN", raising=False)
    with TestClient(main.app) as client:
        response = client.post(
            "/v1/complementer/recommend",
            headers={
                "Authorization": f"Bearer {GATEWAY_TOKEN}",
                "X-End-User-Authorization": f"Bearer {END_USER_TOKEN}",
            },
            json=advisory_request(),
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "COMPLEMENTER_PROVIDER_CONFIGURATION_INVALID"


def test_gateway_rejects_upstream_scope_mismatch(monkeypatch):
    configure_complementer(monkeypatch)
    body = advisory_request()
    bad_response = upstream_result(body)
    bad_response["user_id"] = "different-user"

    class Client(FakeHttpClient):
        def __init__(self, *args, **kwargs):
            super().__init__(FakeResponse(200, bad_response), expected_body=body)

    with TestClient(main.app) as client:
        monkeypatch.setattr(main.httpx, "Client", Client)
        response = client.post(
            "/v1/complementer/recommend",
            headers={
                "Authorization": f"Bearer {GATEWAY_TOKEN}",
                "X-End-User-Authorization": f"Bearer {END_USER_TOKEN}",
            },
            json=body,
        )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "COMPLEMENTER_SCHEMA_OR_SCOPE_MISMATCH"


def test_gateway_rejects_upstream_claim_of_persistent_memory(monkeypatch):
    configure_complementer(monkeypatch)
    body = advisory_request()
    bad_response = upstream_result(body)
    bad_response["persistence"] = "durable"

    class Client(FakeHttpClient):
        def __init__(self, *args, **kwargs):
            super().__init__(FakeResponse(200, bad_response), expected_body=body)

    with TestClient(main.app) as client:
        monkeypatch.setattr(main.httpx, "Client", Client)
        response = client.post(
            "/v1/complementer/recommend",
            headers={
                "Authorization": f"Bearer {GATEWAY_TOKEN}",
                "X-End-User-Authorization": f"Bearer {END_USER_TOKEN}",
            },
            json=body,
        )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "COMPLEMENTER_SCHEMA_OR_SCOPE_MISMATCH"


def test_gateway_complementer_capability_is_optional_and_explicit(monkeypatch):
    configure_complementer(monkeypatch)
    with TestClient(main.app) as client:
        capabilities = client.get("/capabilities").json()
    assert capabilities["complementer_advisory_integration_configured"] is True
    assert capabilities["complementer_product_retrieval"] is False
    assert capabilities["complementer_display_authority"] is False
    assert capabilities["durable_complementer_memory"] is False
