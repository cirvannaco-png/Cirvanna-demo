from __future__ import annotations

from fastapi.testclient import TestClient
from fastapi import HTTPException

from app import main

client = TestClient(main.app)
TOKEN = "xari-test-token-at-least-thirty-two-bytes"
PAYLOAD = {"query": "a modest green linen dress for warm weather", "category": "dress", "limit": 5}


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_marketplace_search_requires_internal_authentication(monkeypatch):
    monkeypatch.delenv("XARI_API_TOKEN", raising=False)
    response = client.post("/v1/marketplace/search", json=PAYLOAD)
    assert response.status_code == 401


def test_text_search_fails_closed_without_vision_adapter(monkeypatch):
    monkeypatch.setenv("XARI_API_TOKEN", TOKEN)
    monkeypatch.delenv("VISION_INTELLIGENCE_API_URL", raising=False)
    monkeypatch.delenv("VISION_INTELLIGENCE_API_TOKEN", raising=False)
    response = client.post("/v1/marketplace/search", headers=auth(), json=PAYLOAD)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MARKETPLACE_SEARCH_NOT_CONFIGURED"


def test_text_search_normalizes_description_and_marks_candidates_pending_cal(monkeypatch):
    monkeypatch.setenv("XARI_API_TOKEN", TOKEN)

    async def fake_search(payload):
        assert payload.normalized_query == "a modest green linen dress for warm weather"
        assert payload.category == "dress"
        assert payload.limit == 5
        return {
            "status": "complete",
            "candidate_count": 1,
            "results": [{"variant_id": "variant-1", "product_name": "Green linen dress", "match_score": 0.38}],
            "catalog_truncated": False,
            "model": {"id": "clip", "revision": "a" * 40},
        }

    monkeypatch.setattr(main, "_execute_marketplace_search", fake_search)
    response = client.post(
        "/v1/marketplace/search",
        headers=auth(),
        json={"query": "  a   modest green linen dress for warm weather ", "category": "dress", "limit": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["candidates"][0]["variant_id"] == "variant-1"
    assert body["candidate_count"] == 1
    assert body["display_authorized"] is False
    assert body["decision_status"] == "PENDING_CAL"
    assert body["scores_are_probabilities"] is False
    assert "results" not in body


def test_text_search_does_not_expose_upstream_exceptions(monkeypatch):
    monkeypatch.setenv("XARI_API_TOKEN", TOKEN)

    async def fail(_payload):
        raise HTTPException(503, detail={"code": "MARKETPLACE_SEARCH_UNAVAILABLE"})

    monkeypatch.setattr(main, "_execute_marketplace_search", fail)
    response = client.post("/v1/marketplace/search", headers=auth(), json=PAYLOAD)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MARKETPLACE_SEARCH_UNAVAILABLE"


def test_capabilities_report_search_contract_without_claiming_cal_display(monkeypatch):
    monkeypatch.setenv("XARI_API_TOKEN", TOKEN)
    monkeypatch.delenv("VISION_INTELLIGENCE_API_URL", raising=False)
    monkeypatch.delenv("VISION_INTELLIGENCE_API_TOKEN", raising=False)
    data = client.get("/capabilities").json()
    assert data["marketplace_description_search"]["implemented"] is True
    assert data["marketplace_description_search"]["configured"] is False
    assert data["marketplace_description_search"]["cal_authorization_required_before_display"] is True

def test_tari_token_is_preferred_over_legacy_xari_token(monkeypatch):
    tari_token = "tari-test-token-at-least-thirty-two-bytes"
    xari_token = "xari-legacy-token-at-least-thirty-two-bytes"
    monkeypatch.setenv("TARI_API_TOKEN", tari_token)
    monkeypatch.setenv("XARI_API_TOKEN", xari_token)
    wrong = client.post("/v1/marketplace/search", headers={"Authorization": f"Bearer {xari_token}"}, json=PAYLOAD)
    assert wrong.status_code == 401
    right = client.post("/v1/marketplace/search", headers={"Authorization": f"Bearer {tari_token}"}, json=PAYLOAD)
    assert right.status_code == 503
    assert right.json()["detail"]["code"] == "MARKETPLACE_SEARCH_NOT_CONFIGURED"

def test_capabilities_name_tari_as_canonical_and_keep_xari_as_legacy(monkeypatch):
    monkeypatch.setenv("TARI_API_TOKEN", "tari-test-token-at-least-thirty-two-bytes")
    data = client.get("/capabilities").json()
    assert data["canonical_name"] == "Tari"
    assert data["legacy_names"] == ["Xari", "Xyra"]