from __future__ import annotations

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app import main

TOKEN = "vision-worker-test-token-longer-than-thirty-two-bytes"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("VISION_WORKER_TOKEN", TOKEN)
    with TestClient(main.app) as test_client:
        yield test_client


def image_bytes(pattern: bool = True) -> bytes:
    image = Image.new("RGB", (240, 320), "white")
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
