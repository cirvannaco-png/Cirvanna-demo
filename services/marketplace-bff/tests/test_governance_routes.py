import json

from fastapi.testclient import TestClient

from app import main


class Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode()

    def json(self):
        return self.payload


class Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        self.calls.append(url)
        return self.responses.pop(0)

    async def post(self, url, **kwargs):
        self.calls.append(url)
        return self.responses.pop(0)


def test_offers_route_passes_verified_user_and_candidates_through_cal(monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    upstream = Client([
        Response({"user_id": "verified-user"}),
        Response({"items": [
            {"variant_id": "show-1", "product_name": "allowed"},
            {"variant_id": "block-1", "product_name": "must-not-leak"},
        ], "total": 2}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: upstream)
    seen = {}

    async def fake_govern_candidates(subject_id, candidates):
        seen["subject_id"] = subject_id
        seen["candidate_ids"] = [candidate["variant_id"] for candidate in candidates]
        return {
            "candidate_count": 1,
            "candidates": [{
                "variant_id": "show-1",
                "product_name": "allowed",
                "display_authorized": True,
                "decision_status": "SHOW",
                "cal_decision": {
                    "verdict": "SHOW",
                    "may_display": True,
                    "request_id": "bound-request",
                    "policy_version": "test-policy",
                },
            }],
            "display_authorized": True,
            "decision_status": "SHOW",
            "governance_status": "CAL_PARTIAL_FAIL_CLOSED",
            "scores_are_probabilities": False,
        }

    monkeypatch.setattr(main, "govern_candidates", fake_govern_candidates)
    with TestClient(main.app) as client:
        response = client.get(
            "/api/commerce/marketplace/offers",
            headers={"Authorization": "Bearer user-session"},
        )

    assert response.status_code == 200, response.text
    assert seen == {
        "subject_id": "verified-user",
        "candidate_ids": ["show-1", "block-1"],
    }
    assert [item["variant_id"] for item in response.json()["items"]] == ["show-1"]
    assert "must-not-leak" not in response.text



def test_xari_route_runs_retrieved_candidates_through_cal(monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("XARI_API_URL", "https://xari.example.test")
    monkeypatch.setenv("XARI_API_TOKEN", "x" * 40)
    upstream = Client([
        Response({"user_id": "verified-user"}),
        Response({"status": "complete", "candidates": [
            {"variant_id": "xari-1", "product_name": "xari result"},
        ]}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: upstream)
    seen = {}

    async def fake_govern_candidates(subject_id, candidates):
        seen["subject_id"] = subject_id
        seen["candidate_ids"] = [candidate["variant_id"] for candidate in candidates]
        return {
            "candidate_count": 0, "candidates": [], "display_authorized": False,
            "decision_status": "NO_SHOW", "governance_status": "CAL_PARTIAL_FAIL_CLOSED",
            "scores_are_probabilities": False,
        }

    monkeypatch.setattr(main, "govern_candidates", fake_govern_candidates)
    with TestClient(main.app) as client:
        response = client.post(
            "/api/vision/marketplace-search",
            headers={"Authorization": "Bearer user-session"},
            json={"query": "linen shirt"},
        )
    assert response.status_code == 200, response.text
    assert seen == {"subject_id": "verified-user", "candidate_ids": ["xari-1"]}
    assert response.json()["candidates"] == []
    assert "xari result" not in response.text


def test_click_it_route_runs_reconstructed_candidates_through_cal(monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    monkeypatch.setenv("VIRTUAL_TWIN_API_URL", "https://twin.example.test")
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "x" * 40)
    upstream = Client([
        Response({"user_id": "verified-user"}),
        Response({"status": "complete", "candidates": [
            {"variant_id": "click-1", "product_name": "click result"},
        ], "image_persisted": False}),
    ])
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: upstream)
    seen = {}

    async def fake_govern_candidates(subject_id, candidates):
        seen["subject_id"] = subject_id
        seen["candidate_ids"] = [candidate["variant_id"] for candidate in candidates]
        return {
            "candidate_count": 0, "candidates": [], "display_authorized": False,
            "decision_status": "NO_SHOW", "governance_status": "CAL_PARTIAL_FAIL_CLOSED",
            "scores_are_probabilities": False,
        }

    monkeypatch.setattr(main, "govern_candidates", fake_govern_candidates)
    with TestClient(main.app) as client:
        response = client.post(
            "/api/vision/click-it",
            headers={"Authorization": "Bearer user-session"},
            data={
                "consent_id": "consent-record-1234",
                "consent_image_processing": "true",
                "consent_click_it": "true",
            },
            files={"product_image": ("photo.png", b"test-image-bytes", "image/png")},
        )
    assert response.status_code == 200, response.text
    assert seen == {"subject_id": "verified-user", "candidate_ids": ["click-1"]}
    assert response.json()["candidates"] == []
    assert "click result" not in response.text


def test_internal_checkout_authorization_requires_service_token_and_exact_show(monkeypatch):
    monkeypatch.setenv("CAL_GATEWAY_SERVICE_TOKEN", "internal-cal-token-that-is-at-least-32-bytes")
    calls = []

    async def fake_govern(subject_id, candidates):
        calls.append((subject_id, candidates))
        return {"candidates": [{
            "candidate_id": candidates[0]["candidate_id"],
            "cal_decision": {"verdict": "SHOW", "may_display": True, "request_id": "req-1", "policy_version": "policy-1"},
        }]}

    monkeypatch.setattr(main, "govern_candidates", fake_govern)
    with TestClient(main.app) as client:
        denied = client.post("/internal/cal/authorize", json={"subject_id": "u1", "candidate_id": "p1"})
        assert denied.status_code == 401
        allowed = client.post("/internal/cal/authorize",
            headers={"Authorization": "Bearer internal-cal-token-that-is-at-least-32-bytes"},
            json={"subject_id": "u1", "candidate_id": "p1"})
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["decision"] == "SHOW" and allowed.json()["may_display"] is True
    assert allowed.json()["request_id"] == "req-1"
    assert calls[0][0] == "u1"


def test_internal_checkout_authorization_never_upgrades_no_show(monkeypatch):
    monkeypatch.setenv("CAL_GATEWAY_SERVICE_TOKEN", "internal-cal-token-that-is-at-least-32-bytes")

    async def fake_govern(_subject_id, _candidates):
        return {"candidates": [], "governance_status": "CAL_GATE_NOT_CONNECTED"}

    monkeypatch.setattr(main, "govern_candidates", fake_govern)
    with TestClient(main.app) as client:
        response = client.post("/internal/cal/authorize",
            headers={"Authorization": "Bearer internal-cal-token-that-is-at-least-32-bytes"},
            json={"subject_id": "u1", "candidate_id": "p1"})
    assert response.status_code == 200
    assert response.json()["decision"] == "NO_SHOW"
    assert response.json()["may_display"] is False
