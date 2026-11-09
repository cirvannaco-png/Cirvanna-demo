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
    monkeypatch.delenv("PNELLY_API_TOKEN", raising=False)
    monkeypatch.delenv("XARI_API_TOKEN", raising=False)
    monkeypatch.delenv("TARI_API_TOKEN", raising=False)
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
    monkeypatch.setenv("PNELLY_API_TOKEN", "pnelly-test-token-at-least-thirty-two-bytes")
    data = client.get("/capabilities").json()
    assert data["canonical_name"] == "PNELLY"
    assert data["legacy_names"] == ["Xari", "Tari", "Xyra"]
    assert data["contract_compatibility"] == {
        "xari_routes_preserved": True,
        "route_contract_version": "1.0.0",
    }



def test_pnelly_token_is_preferred_over_xari_and_tari(monkeypatch):
    pnelly_token = "pnelly-test-token-at-least-thirty-two-bytes"
    xari_token = "xari-test-token-at-least-thirty-two-bytes"
    tari_token = "tari-legacy-token-at-least-thirty-bytes"
    monkeypatch.setenv("PNELLY_API_TOKEN", pnelly_token)
    monkeypatch.setenv("XARI_API_TOKEN", xari_token)
    monkeypatch.setenv("TARI_API_TOKEN", tari_token)
    monkeypatch.delenv("VISION_INTELLIGENCE_API_URL", raising=False)
    monkeypatch.delenv("VISION_INTELLIGENCE_API_TOKEN", raising=False)

    legacy = client.post(
        "/v1/marketplace/search",
        headers={"Authorization": f"Bearer {xari_token}"},
        json=PAYLOAD,
    )
    canonical = client.post(
        "/v1/marketplace/search",
        headers={"Authorization": f"Bearer {pnelly_token}"},
        json=PAYLOAD,
    )
    assert legacy.status_code == 401
    assert canonical.status_code == 503
    assert canonical.json()["detail"]["code"] == "MARKETPLACE_SEARCH_NOT_CONFIGURED"

def test_look_it_requires_internal_authentication(monkeypatch):
    monkeypatch.setenv("PNELLY_API_TOKEN", TOKEN)
    response = client.post(
        "/v1/marketplace/search/image",
        data={
            "subject_id": "customer-123",
            "consent_id": "consent-look-it-0001",
            "resource_id": "look-it-request-0001",
            "consent_image_processing": "true",
            "consent_look_it": "true",
        },
        files={"image": ("outfit.png", b"image", "image/png")},
    )
    assert response.status_code == 401


def test_look_it_verifies_exact_resource_bound_consent_and_returns_no_product_details(monkeypatch):
    monkeypatch.setenv("PNELLY_API_TOKEN", TOKEN)
    verified = {}

    async def verify(subject_id, consent_id, resource_id):
        verified.update({"subject_id": subject_id, "consent_id": consent_id, "resource_id": resource_id})

    async def search(**kwargs):
        assert kwargs["data"] == b"reference-image"
        assert kwargs["content_type"] == "image/png"
        return {
            "status": "complete",
            "candidate_count": 3,
            "image_persisted": False,
            "outfit_decomposition": {
                "status": "complete",
                "components": [{
                    "component_id": "component-1",
                    "category": "upper_body",
                    "description": "dark tailored jacket",
                    "candidate_count": 2,
                }],
            },
            "merchant_comparison": {"status": "pending_cal"},
        }

    monkeypatch.setattr(main, "_verify_look_it_consent", verify)
    monkeypatch.setattr(main, "_execute_marketplace_image_search", search)
    response = client.post(
        "/v1/marketplace/search/image",
        headers=auth(),
        data={
            "subject_id": "customer-123",
            "consent_id": "consent-look-it-0001",
            "resource_id": "look-it-request-0001",
            "consent_image_processing": "true",
            "consent_look_it": "true",
            "category": "dress",
            "limit": "5",
        },
        files={"image": ("outfit.png", b"reference-image", "image/png")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert verified == {
        "subject_id": "customer-123",
        "consent_id": "consent-look-it-0001",
        "resource_id": "look-it-request-0001",
    }
    assert body["candidate_count"] == 3
    assert body["display_authorized"] is False
    assert body["decision_status"] == "PENDING_CAL"
    assert body["outfit_decomposition"]["components"][0]["description"] == "dark tailored jacket"
    assert body["merchant_comparison"]["status"] == "pending_cal"
    assert "variant_id" not in response.text
    assert "price_minor" not in response.text
    assert "private-image" not in response.text
    assert response.headers["cache-control"] == "no-store, private"


def test_look_it_rejects_request_when_consent_is_incomplete(monkeypatch):
    monkeypatch.setenv("PNELLY_API_TOKEN", TOKEN)

    async def forbidden(*_args, **_kwargs):
        pytest.fail("Look It must reject missing explicit consent before provider verification")

    monkeypatch.setattr(main, "_verify_look_it_consent", forbidden)
    response = client.post(
        "/v1/marketplace/search/image",
        headers=auth(),
        data={
            "subject_id": "customer-123",
            "consent_id": "consent-look-it-0001",
            "resource_id": "look-it-request-0001",
            "consent_image_processing": "true",
            "consent_look_it": "false",
        },
        files={"image": ("outfit.png", b"reference-image", "image/png")},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "EXPLICIT_LOOK_IT_CONSENT_REQUIRED"
