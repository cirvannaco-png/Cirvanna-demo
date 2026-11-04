from __future__ import annotations

import io
import asyncio

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFilter

from app import main

TOKEN = "vision-worker-test-token-longer-than-thirty-two-bytes"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("VISION_WORKER_TOKEN", TOKEN)
    with TestClient(main.app) as test_client:
        yield test_client


def image_bytes(pattern: bool = True) -> bytes:
    image = Image.new("RGB", (240, 320), (120, 120, 120))
    if pattern:
        draw = ImageDraw.Draw(image)
        for y in range(0, 320, 16):
            draw.line((0, y, 239, y), fill=(20, 35, 55), width=4)
        for x in range(0, 240, 16):
            draw.line((x, 0, x, 319), fill=(170, 30, 60), width=4)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_health_is_liveness_only(client):
    assert client.get("/health").json()["status"] == "alive"


def test_readiness_does_not_claim_models_or_marketplace_are_configured(client, monkeypatch):
    for name in (
        "CLIP_MODEL_REVISION", "POSE_LANDMARKER_MODEL_PATH", "POSE_LANDMARKER_MODEL_SHA256",
        "COMMERCE_API_URL", "CATALOG_API_URL", "CATALOG_API_TOKEN", "CATALOG_READ_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["ready"] is False


def test_internal_routes_require_auth(client):
    response = client.post(
        "/v1/search/text",
        json={"query": "red satin blouse", "limit": 5},
    )
    assert response.status_code == 401


def test_image_quality_check_reports_blur_and_exposure():
    blank = Image.new("RGB", (240, 320), (0, 0, 0))
    quality = main.evaluate_image_quality(blank)
    assert quality["passed"] is False
    assert "image_too_dark" in quality["failure_codes"]
    assert "low_contrast" in quality["failure_codes"]


def test_click_it_requires_both_consents(client):
    response = client.post(
        "/v1/click-it/scan",
        headers=auth(),
        data={"consent_image_processing": "true", "consent_click_it": "false"},
        files={"image": ("product.png", image_bytes(), "image/png")},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "EXPLICIT_CLICK_IT_CONSENT_REQUIRED"


def test_click_it_rejects_low_quality_before_loading_model(client, monkeypatch):
    monkeypatch.setattr(main, "_image_embedding", lambda _image: pytest.fail("model must not run"))
    dark = Image.new("RGB", (240, 320), (0, 0, 0))
    stream = io.BytesIO()
    dark.save(stream, format="PNG")
    response = client.post(
        "/v1/click-it/scan",
        headers=auth(),
        data={"consent_image_processing": "true", "consent_click_it": "true"},
        files={"image": ("dark.png", stream.getvalue(), "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "IMAGE_QUALITY_REJECTED"


def test_description_search_uses_live_offers_and_never_fabricates_results(client, monkeypatch):
    async def offers():
        return ([{
            "variant_id": "v1",
            "product_name": "linen wrap dress",
            "category": "dress",
            "product": {"product_id": "p1", "description": "Breathable linen with a wrap waist", "brand": "Maker"},
            "search_text": "linen wrap dress breathable linen",
        }], False)

    monkeypatch.setattr(main, "_live_offers", offers)
    monkeypatch.setattr(main, "_text_embedding", lambda _text: [1.0, 0.0])
    monkeypatch.setattr(main, "_rank_offers", lambda _query, _offers, limit: [{
        "variant_id": "v1", "product_name": "linen wrap dress",
        "match_score": 0.25, "match_score_type": "cosine_similarity_not_probability",
    }][:limit])
    response = client.post("/v1/search/text", headers=auth(), json={"query": "linen wrap dress"})
    assert response.status_code == 200
    body = response.json()
    assert body["candidate_count"] == 1
    assert body["results"][0]["variant_id"] == "v1"
    assert body["scores_are_probabilities"] is False


def test_click_it_returns_ranked_live_marketplace_results_without_persisting_image(client, monkeypatch):
    async def offers():
        return ([{
            "variant_id": "v1",
            "product_name": "red woven top",
            "category": "upper_body",
            "product": {"product_id": "p1", "description": "Red woven cotton top"},
            "search_text": "red woven cotton top",
        }], False)

    monkeypatch.setattr(main, "_live_offers", offers)
    monkeypatch.setattr(main, "_image_embedding", lambda _image: [0.25, 0.75])
    monkeypatch.setattr(main, "_rank_offers", lambda _query, _offers, limit: [{
        "variant_id": "v1", "product_name": "red woven top",
        "match_score": 0.31, "match_score_type": "cosine_similarity_not_probability",
    }][:limit])
    response = client.post(
        "/v1/click-it/scan",
        headers=auth(),
        data={"consent_image_processing": "true", "consent_click_it": "true"},
        files={"image": ("product.png", image_bytes(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["search_mode"] == "image_to_catalog_text_similarity"
    assert body["image_persisted"] is False
    assert body["results"][0]["variant_id"] == "v1"


def test_ranker_orders_scores_descending(monkeypatch):
    monkeypatch.setattr(main, "_CLIP_MODEL", object())
    monkeypatch.setattr(main, "_CLIP_PROCESSOR", object())
    monkeypatch.setattr(main, "_TEXT_VECTOR_CACHE", {
        "a": [1.0, 0.0], "b": [0.0, 1.0],
    })
    import hashlib
    offers = [
        {"variant_id": "a", "search_text": "first", "product_name": "first"},
        {"variant_id": "b", "search_text": "second", "product_name": "second"},
    ]
    # The vector cache key is a sha256 of normalized offer text.
    monkeypatch.setattr(main, "_TEXT_VECTOR_CACHE", {
        hashlib.sha256(b"first").hexdigest(): [1.0, 0.0],
        hashlib.sha256(b"second").hexdigest(): [0.0, 1.0],
    })
    result = main._rank_offers([1.0, 0.0], offers, 2)
    assert [item["variant_id"] for item in result] == ["a", "b"]


def test_image_quality_rejects_blurry_capture_with_laplacian_variance():
    sharp = Image.new("RGB", (320, 320), (120, 120, 120))
    draw = ImageDraw.Draw(sharp)
    for x in range(0, 320, 8):
        draw.line((x, 0, x, 319), fill=(0, 0, 0), width=2)
    blurred = sharp.filter(ImageFilter.GaussianBlur(radius=8))
    quality = main.evaluate_image_quality(blurred)
    assert quality["sharpness_proxy"] < 20.0
    assert quality["passed"] is False
    assert "image_may_be_blurry" in quality["failure_codes"]


def test_image_quality_accepts_well_lit_detailed_capture():
    quality = main.evaluate_image_quality(Image.open(io.BytesIO(image_bytes())))
    assert quality["passed"] is True
    assert quality["sharpness_proxy"] >= 20.0
    assert quality["interpretation"] == "capture_quality_only_not_model_or_fit_confidence"


def test_image_quality_rejects_blurred_low_contrast_and_clipped_captures():
    blurred = Image.new("RGB", (240, 320), (120, 120, 120))
    quality = main.evaluate_image_quality(blurred)
    assert quality["passed"] is False
    assert "low_contrast" in quality["failure_codes"]
    assert "image_may_be_blurry" in quality["failure_codes"]
    clipped = Image.new("RGB", (240, 320), (255, 255, 255))
    clipped_quality = main.evaluate_image_quality(clipped)
    assert "image_too_bright" in clipped_quality["failure_codes"]
    assert "excessive_clipping" in clipped_quality["failure_codes"]


def test_live_offer_join_matches_actual_commerce_and_catalog_contracts(monkeypatch):
    monkeypatch.setattr(main, "_trusted_base", lambda name, **kwargs: {
        "COMMERCE_API_URL": "https://commerce.example.test",
        "CATALOG_API_URL": "https://catalog.example.test",
    }[name])
    monkeypatch.setenv("CATALOG_READ_TOKEN", "read-only-test-token")
    calls = []

    async def fake_get_json(client, url, *, params=None, headers=None):
        calls.append((url, params, headers))
        if url.endswith("/marketplace/offers"):
            return {
                "items": [{
                    "variant_id": "variant-1",
                    "catalog_product_id": "00000000-0000-0000-0000-000000000001",
                    "product_name": "Indigo linen top",
                    "category": "tops",
                    "available_stock": 2,
                    "price_minor": 1200,
                    "currency": "KES",
                    "options": {"size": "M"},
                }],
                "total": 1,
                "offset": 0,
                "limit": 100,
            }
        assert url.endswith("/products/batch")
        assert params == [("ids", "00000000-0000-0000-0000-000000000001")]
        assert headers["Authorization"] == "Bearer read-only-test-token"
        return {
            "items": [{
                "product_id": "00000000-0000-0000-0000-000000000001",
                "name": "Indigo linen top",
                "description": "Breathable linen top with relaxed fit",
                "category": "tops",
                "brand": "Maker",
                "attributes": {"fabric": "linen"},
                "image_urls": ["https://cdn.example.test/top.jpg"],
                "status": "active",
            }]
        }

    monkeypatch.setattr(main, "_get_json", fake_get_json)
    offers, truncated = asyncio.run(main._live_offers())
    assert truncated is False
    assert len(offers) == 1
    assert offers[0]["variant_id"] == "variant-1"
    assert offers[0]["product"]["product_id"] == "00000000-0000-0000-0000-000000000001"
    assert "Breathable linen top with relaxed fit" in offers[0]["search_text"]
    assert len(calls) == 2


def test_live_offer_join_excludes_missing_or_archived_catalog_products(monkeypatch):
    monkeypatch.setattr(main, "_trusted_base", lambda name, **kwargs: {
        "COMMERCE_API_URL": "https://commerce.example.test",
        "CATALOG_API_URL": "https://catalog.example.test",
    }[name])
    monkeypatch.setenv("CATALOG_API_TOKEN", "read-only-test-token")

    async def fake_get_json(client, url, *, params=None, headers=None):
        if url.endswith("/marketplace/offers"):
            return {
                "items": [{
                    "variant_id": "variant-archived",
                    "catalog_product_id": "00000000-0000-0000-0000-000000000002",
                    "product_name": "Archived item",
                    "category": "tops",
                }],
                "total": 1,
            }
        return {"items": [{
            "product_id": "00000000-0000-0000-0000-000000000002",
            "name": "Archived item",
            "status": "archived",
        }]}

    monkeypatch.setattr(main, "_get_json", fake_get_json)
    offers, _ = asyncio.run(main._live_offers())
    assert offers == []



def test_look_it_has_a_distinct_visual_search_route_and_response_contract(client, monkeypatch):
    async def offers():
        return ([{
            "variant_id": "v-look-1",
            "product_name": "blue patterned dress",
            "category": "dress",
            "product": {"product_id": "p-look-1", "description": "Blue patterned dress"},
            "search_text": "blue patterned dress",
        }], False)

    monkeypatch.setattr(main, "_live_offers", offers)
    monkeypatch.setattr(main, "_image_embedding", lambda _image: [0.4, 0.6])
    monkeypatch.setattr(main, "_rank_offers", lambda _query, _offers, limit: [{
        "variant_id": "v-look-1",
        "product_name": "blue patterned dress",
        "match_score": 0.41,
        "match_score_type": "cosine_similarity_not_probability",
    }][:limit])
    response = client.post(
        "/v1/search/image",
        headers=auth(),
        data={"consent_image_processing": "true", "consent_look_it": "true"},
        files={"image": ("inspiration.png", image_bytes(), "image/png")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["search_mode"] == "look_it_image_to_catalog_text_similarity"
    assert body["results"][0]["variant_id"] == "v-look-1"
    assert body["image_persisted"] is False
    assert body["scores_are_probabilities"] is False
    assert body["outfit_decomposition"]["status"] == "unavailable"
    assert body["merchant_comparison"]["status"] == "unavailable"


def test_look_it_requires_look_it_specific_consent(client):
    response = client.post(
        "/v1/search/image",
        headers=auth(),
        data={"consent_image_processing": "true", "consent_look_it": "false"},
        files={"image": ("inspiration.png", image_bytes(), "image/png")},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "EXPLICIT_LOOK_IT_CONSENT_REQUIRED"


def test_look_it_and_click_it_routes_are_distinct(client):
    routes = {route.path for route in main.app.routes}
    assert "/v1/search/image" in routes
    assert "/v1/click-it/scan" in routes
    assert "/v1/search/image" != "/v1/click-it/scan"



def test_outfit_decomposition_fails_closed_without_a_validated_provider(monkeypatch):
    monkeypatch.delenv("OUTFIT_DECOMPOSITION_API_URL", raising=False)
    monkeypatch.delenv("OUTFIT_DECOMPOSITION_API_TOKEN", raising=False)
    monkeypatch.delenv("OUTFIT_DECOMPOSITION_MODEL_ID", raising=False)
    monkeypatch.delenv("OUTFIT_DECOMPOSITION_MODEL_REVISION", raising=False)
    monkeypatch.delenv("OUTFIT_DECOMPOSITION_VALIDATION_REPORT_SHA256", raising=False)
    result = asyncio.run(main._decompose_outfit(Image.new("RGB", (256, 256), "white")))
    assert result["status"] == "unavailable"
    assert result["reason"] == "VALIDATED_OUTFIT_DECOMPOSITION_PROVIDER_NOT_CONFIGURED"
    assert result["components"] == []



def test_outfit_decomposition_requires_exact_approved_model_id_revision_and_report(monkeypatch):
    model_id = "cirvanna/outfit-decomposer"
    revision = "b" * 40
    report_hash = "a" * 64
    monkeypatch.setenv("OUTFIT_DECOMPOSITION_API_URL", "https://decomposition.example.test")
    monkeypatch.setenv("OUTFIT_DECOMPOSITION_API_TOKEN", "decomposition-token-that-is-at-least-thirty-two-bytes")
    monkeypatch.setenv("OUTFIT_DECOMPOSITION_MODEL_ID", model_id)
    monkeypatch.setenv("OUTFIT_DECOMPOSITION_MODEL_REVISION", revision)
    monkeypatch.setenv("OUTFIT_DECOMPOSITION_VALIDATION_REPORT_SHA256", report_hash)
    monkeypatch.setattr(main, "_trusted_base", lambda _name, required=False: "https://decomposition.example.test")

    class FakeResponse:
        status_code = 200
        def json(self):
            return {
                "status": "complete",
                "model": {"id": model_id, "revision": revision},
                "validation_report_sha256": report_hash,
                "components": [{
                    "component_id": "upper-1",
                    "category": "upper_body",
                    "description": "Blue linen shirt with a relaxed collar",
                }],
            }

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return False
        async def post(self, url, *, headers, files):
            assert url == "https://decomposition.example.test/v1/decompose"
            assert headers["Authorization"].startswith("Bearer ")
            assert files["image"][2] == "image/jpeg"
            return FakeResponse()

    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    result = asyncio.run(main._decompose_outfit(Image.new("RGB", (256, 256), "white")))
    assert result["status"] == "complete"
    assert result["model"] == {"id": model_id, "revision": revision}
    assert result["components"][0]["category"] == "upper_body"


def test_outfit_decomposition_rejects_valid_but_unapproved_provider_revision(monkeypatch):
    model_id = "cirvanna/outfit-decomposer"
    approved_revision = "b" * 40
    report_hash = "a" * 64
    monkeypatch.setenv("OUTFIT_DECOMPOSITION_API_URL", "https://decomposition.example.test")
    monkeypatch.setenv("OUTFIT_DECOMPOSITION_API_TOKEN", "decomposition-token-that-is-at-least-thirty-two-bytes")
    monkeypatch.setenv("OUTFIT_DECOMPOSITION_MODEL_ID", model_id)
    monkeypatch.setenv("OUTFIT_DECOMPOSITION_MODEL_REVISION", approved_revision)
    monkeypatch.setenv("OUTFIT_DECOMPOSITION_VALIDATION_REPORT_SHA256", report_hash)
    monkeypatch.setattr(main, "_trusted_base", lambda _name, required=False: "https://decomposition.example.test")

    class FakeResponse:
        status_code = 200
        def json(self):
            return {
                "status": "complete",
                "model": {"id": model_id, "revision": "c" * 40},
                "validation_report_sha256": report_hash,
                "components": [{
                    "component_id": "upper-1",
                    "category": "upper_body",
                    "description": "Blue linen shirt with a relaxed collar",
                }],
            }

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return False
        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    result = asyncio.run(main._decompose_outfit(Image.new("RGB", (256, 256), "white")))
    assert result["status"] == "unavailable"
    assert result["reason"] == "OUTFIT_DECOMPOSITION_VALIDATION_OR_SCHEMA_FAILED"
    assert result["components"] == []


def test_merchant_comparison_requires_canonical_variant_and_observation_time():
    current_payload = [{
        "variant_id": "merchant-local-variant-1",
        "merchant_id": "merchant-1",
        "merchant_name": "Merchant One",
        "price_minor": 1000,
        "currency": "KES",
        "available_stock": 3,
    }]
    blocked = main._merchant_comparison_snapshot(current_payload)
    assert blocked["status"] == "unavailable"
    assert blocked["reason"] == "CANONICAL_VARIANT_ID_AND_OFFER_OBSERVATION_TIMESTAMP_REQUIRED"


def test_merchant_comparison_groups_only_same_canonical_variant_and_currency():
    offers = [
        {
            "canonical_variant_id": "canonical-variant-a",
            "offer_observed_at": "2026-11-04T10:00:00Z",
            "merchant_id": "merchant-1",
            "merchant_name": "Merchant One",
            "price_minor": 1200,
            "currency": "KES",
            "available_stock": 2,
        },
        {
            "canonical_variant_id": "canonical-variant-a",
            "offer_observed_at": "2026-11-04T10:00:05Z",
            "merchant_id": "merchant-2",
            "merchant_name": "Merchant Two",
            "price_minor": 1000,
            "currency": "KES",
            "available_stock": 4,
        },
        {
            "canonical_variant_id": "canonical-variant-a",
            "offer_observed_at": "2026-11-04T10:00:05Z",
            "merchant_id": "merchant-3",
            "merchant_name": "Merchant Three",
            "price_minor": 900,
            "currency": "USD",
            "available_stock": 1,
        },
    ]
    result = main._merchant_comparison_snapshot(offers)
    assert result["status"] == "complete"
    assert len(result["groups"]) == 1
    assert result["groups"][0]["currency"] == "KES"
    assert [item["price_minor"] for item in result["groups"][0]["offers"]] == [1000, 1200]
    assert result["landed_cost_included"] is False


def test_look_it_wires_decomposition_and_comparison_gates(client, monkeypatch):
    async def offers():
        return ([{
            "variant_id": "v-look-1",
            "product_name": "blue patterned dress",
            "category": "dress",
            "product": {"product_id": "p-look-1", "description": "Blue patterned dress"},
            "search_text": "blue patterned dress",
        }], False)

    monkeypatch.setattr(main, "_live_offers", offers)
    monkeypatch.setattr(main, "_image_embedding", lambda _image: [0.4, 0.6])
    monkeypatch.setattr(main, "_rank_offers", lambda _query, _offers, limit: [{"variant_id": "v-look-1"}][:limit])
    async def decomposition(_image):
        return {"status": "complete", "model": {"id": "outfit-model", "revision": "a" * 40},
                "validation_report_sha256": "b" * 64,
                "components": [{"component_id": "component-1", "category": "dress", "description": "blue patterned dress"}]}
    async def component_matches(value, _offers, _limit):
        value["components"][0]["candidates"] = [{"variant_id": "v-look-1"}]
        return value
    monkeypatch.setattr(main, "_decompose_outfit", decomposition)
    monkeypatch.setattr(main, "_match_decomposed_components", component_matches)
    monkeypatch.setattr(main, "_merchant_comparison_snapshot", lambda _offers: {"status": "unavailable", "reason": "CANONICAL_VARIANT_ID_AND_OFFER_OBSERVATION_TIMESTAMP_REQUIRED"})
    response = client.post(
        "/v1/search/image",
        headers=auth(),
        data={"consent_image_processing": "true", "consent_look_it": "true"},
        files={"image": ("inspiration.png", image_bytes(), "image/png")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outfit_decomposition"]["status"] == "complete"
    assert body["outfit_decomposition"]["components"][0]["candidates"][0]["variant_id"] == "v-look-1"
    assert body["merchant_comparison"]["status"] == "unavailable"
