import pytest
from fastapi.testclient import TestClient

from app import main

TOKEN = "complementer-test-token-with-at-least-32-bytes"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("COMPLEMENTER_SERVICE_TOKEN", TOKEN)
    with TestClient(main.app) as test_client:
        yield test_client


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def request_body():
    return {
        "request_id": "req-api-1",
        "user_id": "user-1",
        "preferences": {
            "aesthetics": ["classic"], "favorite_colors": ["emerald"],
            "avoid_colors": [], "favorite_fragrance_families": ["woody"],
            "fragrance_sensitive": False, "fragrance_free": False,
            "fragrance_intensity": "moderate", "earrings_preference": "yes",
            "preferred_earring_shapes": [], "preferred_metals": ["silver"],
        },
        "look": {
            "outfit_colors": ["black"], "neckline": "crew",
            "hairstyle": "down", "climate": "temperate", "occasion": "work",
        },
    }


def test_readiness_requires_configured_internal_token(client):
    assert client.get("/ready").status_code == 200
    assert client.get("/ready").json()["ready"] is True


def test_recommendation_requires_internal_auth(client):
    assert client.post("/v1/complementer/recommend", json=request_body()).status_code == 401


def test_recommendation_uses_explicit_preferences(client):
    response = client.post("/v1/complementer/recommend", headers=auth(), json=request_body())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["palette"]["base_colors"] == ["black"]
    assert result["fragrance"]["families"] == ["woody"]
    assert result["earrings"]["metal"] == "silver"
    assert result["aesthetic"]["status"] == "ready"


def test_unknown_fields_are_rejected(client):
    body = request_body()
    body["image_base64"] = "must-not-be-accepted"
    assert client.post("/v1/complementer/recommend", headers=auth(), json=body).status_code == 422


def test_short_internal_token_fails_closed(monkeypatch):
    monkeypatch.setenv("COMPLEMENTER_SERVICE_TOKEN", "short")
    with TestClient(main.app) as client:
        response = client.post("/v1/complementer/recommend", json=request_body())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "COMPLEMENTER_SERVICE_TOKEN_NOT_CONFIGURED"


def test_unknown_fragrance_family_is_rejected(client):
    body = request_body()
    body["preferences"]["favorite_fragrance_families"] = ["magic"]
    assert client.post("/v1/complementer/recommend", headers=auth(), json=body).status_code == 422
