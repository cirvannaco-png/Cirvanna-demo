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
    def __init__(self):
        self.responses = [
            Response({"user_id": "verified-user"}),
            Response({"items": [
                {"variant_id": "show-1", "product_name": "allowed"},
                {"variant_id": "block-1", "product_name": "must-not-leak"},
            ], "total": 2}),
        ]
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        self.calls.append(url)
        return self.responses.pop(0)


def test_offers_route_passes_verified_user_and_candidates_through_cal(monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.example.test")
    upstream = Client()
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
