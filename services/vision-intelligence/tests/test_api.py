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


def test_click_it_fails_closed_before_decoding_or_loading_models(client, monkeypatch):
    monkeypatch.setattr(main, "_decode_image", lambda *_: pytest.fail("upload must not be decoded"))
    monkeypatch.setattr(main, "_image_embedding", lambda *_: pytest.fail("unmasked upload must not reach embedding"))
    monkeypatch.setattr(main, "_live_offers", lambda: pytest.fail("marketplace must not be queried"))
    response = client.post(
        "/v1/click-it/scan",
        headers=auth(),
        data={"consent_image_processing": "true", "consent_click_it": "true"},
        files={"image": ("product.png", image_bytes(), "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CLICK_IT_PRIVACY_PIPELINE_NOT_RELEASED"


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
        "image_urls": ["https://cdn.example.test/unmasked.jpg"],
        "product": {"image_urls": ["https://cdn.example.test/nested.jpg"]},
        "match_score": 0.25, "match_score_type": "cosine_similarity_not_probability",
    }][:limit])
    response = client.post("/v1/search/text", headers=auth(), json={"query": "linen wrap dress"})
    assert response.status_code == 200
    body = response.json()
    assert body["candidate_count"] == 1
    assert body["results"][0]["variant_id"] == "v1"
    assert body["results"][0]["image_urls"] == []
    assert body["results"][0]["product"]["image_urls"] == []
    assert body["scores_are_probabilities"] is False


def test_click_it_never_returns_success_while_masking_pipeline_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(main, "_decode_image", lambda *_: pytest.fail("upload must not be decoded"))
    monkeypatch.setattr(main, "_image_embedding", lambda *_: pytest.fail("unmasked upload must not reach embedding"))
    monkeypatch.setattr(main, "_live_offers", lambda: pytest.fail("marketplace must not be queried"))
    response = client.post(
        "/v1/click-it/scan",
        headers=auth(),
        data={"consent_image_processing": "true", "consent_click_it": "true"},
        files={"image": ("product.png", image_bytes(), "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CLICK_IT_PRIVACY_PIPELINE_NOT_RELEASED"


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
