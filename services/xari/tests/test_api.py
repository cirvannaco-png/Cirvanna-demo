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

def test_xari_token_is_preferred_over_legacy_tari_token(monkeypatch):
    xari_token = "xari-test-token-at-least-thirty-two-bytes"
    tari_token = "tari-legacy-token-at-least-thirty-two-bytes"
    monkeypatch.setenv("XARI_API_TOKEN", xari_token)
    monkeypatch.setenv("TARI_API_TOKEN", tari_token)
    monkeypatch.delenv("VISION_INTELLIGENCE_API_URL", raising=False)
    monkeypatch.delenv("VISION_INTELLIGENCE_API_TOKEN", raising=False)
    wrong = client.post("/v1/marketplace/search", headers={"Authorization": f"Bearer {tari_token}"}, json=PAYLOAD)
    assert wrong.status_code == 401
    right = client.post("/v1/marketplace/search", headers={"Authorization": f"Bearer {xari_token}"}, json=PAYLOAD)
    assert right.status_code == 503
    assert right.json()["detail"]["code"] == "MARKETPLACE_SEARCH_NOT_CONFIGURED"

def test_capabilities_name_pnelly_as_canonical_and_keep_legacy_aliases(monkeypatch):
    monkeypatch.setenv("XARI_API_TOKEN", "xari-test-token-at-least-thirty-two-bytes")
    data = client.get("/capabilities").json()
    assert data["canonical_name"] == "PNELLY"
    assert data["legacy_names"] == ["Xari", "Tari", "Xyra"]
    assert data["dermalsight"]["parent_capability"] == "PNELLY"
    assert data["dermalsight"]["execution_enabled"] is False


def test_look_it_requires_authentication(monkeypatch):
    monkeypatch.setenv("PNELLY_API_TOKEN", TOKEN)
    response = client.post(
        "/v1/marketplace/search/image",
        data={"subject_id": "subject-123", "consent_id": "consent-1234",
              "consent_image_processing": "true", "consent_look_it": "true"},
        files={"image": ("reference.png", b"image-bytes", "image/png")},
    )
    assert response.status_code == 401


def test_look_it_verifies_distinct_consent_before_visual_search(monkeypatch):
    monkeypatch.setenv("PNELLY_API_TOKEN", TOKEN)
    called = {"consent": False, "search": False}

    async def verify(subject_id, consent_id):
        called["consent"] = True
        assert subject_id == "subject-123"
        assert consent_id == "consent-1234"

    async def search(**kwargs):
        assert called["consent"] is True
        called["search"] = True
        assert kwargs["data"] == b"image-bytes"
        return {
            "status": "complete",
            "results": [{"variant_id": "variant-1", "match_score": 0.4}],
            "catalog_truncated": False,
            "outfit_decomposition": {"status": "unavailable", "components": []},
        }

    monkeypatch.setattr(main, "_verify_look_it_consent", verify)
    monkeypatch.setattr(main, "_execute_marketplace_image_search", search)
    response = client.post(
        "/v1/marketplace/search/image",
        headers=auth(),
        data={"subject_id": "subject-123", "consent_id": "consent-1234",
              "consent_image_processing": "true", "consent_look_it": "true"},
        files={"image": ("reference.png", b"image-bytes", "image/png")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert called == {"consent": True, "search": True}
    assert body["search_mode"] == "pnelly_look_it_image_to_catalog_text_similarity"
    assert body["display_authorized"] is False
    assert body["decision_status"] == "PENDING_CAL"
    assert body["scores_are_probabilities"] is False
    assert body["outfit_decomposition"]["status"] == "unavailable"
    assert body["merchant_comparison"]["status"] == "unavailable"


def test_look_it_fails_closed_without_server_side_consent_provider(monkeypatch):
    monkeypatch.setenv("PNELLY_API_TOKEN", TOKEN)
    monkeypatch.delenv("CONSENT_API_URL", raising=False)
    monkeypatch.delenv("CONSENT_API_TOKEN", raising=False)
    response = client.post(
        "/v1/marketplace/search/image",
        headers=auth(),
        data={"subject_id": "subject-123", "consent_id": "consent-1234",
              "consent_image_processing": "true", "consent_look_it": "true"},
        files={"image": ("reference.png", b"image-bytes", "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "LOOK_IT_CONSENT_PROVIDER_NOT_CONFIGURED"
