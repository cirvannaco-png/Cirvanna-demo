import uuid

import pytest
from fastapi.testclient import TestClient

from app import main

TOKEN = "gateway-test-token-with-at-least-32-bytes"
PRODUCT_ID = "2e4c0b5a-d9b4-4b96-87f0-5c92f120d14f"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", TOKEN)
    monkeypatch.setenv("CIRVANNA_AUDIT_DB", str(tmp_path / "audit.sqlite3"))
    monkeypatch.setenv("CIRVANNA_REQUIRE_VERIFIED_IDENTITY", "true")
    return TestClient(main.app)


def body(user_id="subject-verified-1"):
    return {
        "user_id": user_id,
        "product_ids": [PRODUCT_ID],
        "context": {"age_years": 25, "location": "Nairobi", "occasion": "everyday", "climate": "warm"},
        "style_preferences": [{"attribute": "client-controlled-style", "weight": 1.0}],
        "negative_preferences": [],
        "cultural_requirements": [],
        "hard_constraints": [],
    }


def headers():
    return {
        "Authorization": f"Bearer {TOKEN}",
        "X-End-User-Authorization": "Bearer signed-end-user-token",
    }


def test_decision_rejects_caller_subject_that_differs_from_verified_identity(client, monkeypatch):
    monkeypatch.setattr(main, "_resolve_verified_subject", lambda _token: "subject-verified-1")
    monkeypatch.setattr(main, "fetch_product", lambda _pid: pytest.fail("must reject before product retrieval"))
    response = client.post("/v1/decisions", headers=headers(), json=body(user_id="attacker-chosen-id"))
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "REQUEST_SUBJECT_MISMATCH"


def test_decision_uses_persisted_usi_profile_after_verified_subject_resolution(client, monkeypatch):
    from usi import StylePreference, USIProfile

    monkeypatch.setattr(main, "_resolve_verified_subject", lambda token: "subject-verified-1")
    profile = USIProfile(
        profile_id="profile-1", user_id="subject-verified-1", version="7",
        preferences=(StylePreference(
            preference_id="saved-style-1", user_id="subject-verified-1",
            attribute="minimal", weight=0.75,
        ),),
    )
    loaded = []
    monkeypatch.setattr(main, "_load_verified_usi_profile", lambda subject: loaded.append(subject) or profile)
    monkeypatch.setattr(main, "fetch_product", lambda _pid: {
        "product_id": PRODUCT_ID, "sku": "SKU-1", "name": "Candidate", "category": "shirt",
        "brand": None, "price_minor": 1000, "currency": "KES",
        "attributes": {"style": "minimal", "material": "cotton", "color": "blue"},
        "image_urls": [], "status": "active", "catalog_version": 1,
    })
    monkeypatch.setattr(main, "_record_audit", lambda **_kwargs: None)
    response = client.post("/v1/decisions", headers=headers(), json=body())
    assert response.status_code == 200, response.text
    assert loaded == ["subject-verified-1"]
    assert response.json()["candidates"][0]["may_display"] is False


def test_identity_required_rejects_missing_end_user_bearer(client):
    response = client.post(
        "/v1/decisions",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json=body(),
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "END_USER_BEARER_REQUIRED"


def test_usi_profile_provider_rejects_subject_scope_mismatch(monkeypatch):
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.internal")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-provider-token-with-at-least-32-bytes")

    class FakeResponse:
        status_code = 200
        def json(self):
            return {"subject_id": "different-user", "profile_version": 2, "preferences": []}

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def get(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr(main.httpx, "Client", FakeClient)
    with pytest.raises(main.HTTPException) as error:
        main._load_verified_usi_profile("subject-verified-1")
    assert error.value.status_code == 502
    assert error.value.detail["code"] == "USI_PROFILE_SCOPE_OR_SCHEMA_MISMATCH"


def test_commerce_subject_rejects_path_like_identifiers(monkeypatch):
    monkeypatch.setenv("COMMERCE_API_URL", "https://commerce.internal")

    class FakeResponse:
        status_code = 200
        def json(self):
            return {"user_id": "../../another-user"}

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def get(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr(main.httpx, "Client", FakeClient)
    with pytest.raises(main.HTTPException) as error:
        main._resolve_verified_subject("Bearer commerce-user-token")
    assert error.value.status_code == 502
    assert error.value.detail["code"] == "COMMERCE_IDENTITY_SUBJECT_INVALID"


def test_usi_profile_rejects_non_boolean_active_values(monkeypatch):
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.internal")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-provider-token-with-at-least-32-bytes")

    class FakeResponse:
        status_code = 200
        def json(self):
            return {
                "subject_id": "subject-verified-1",
                "profile_version": 1,
                "preferences": [{
                    "preference_id": "p1",
                    "attribute": "classic",
                    "weight": 0.8,
                    "active": "false",
                }],
            }

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def get(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr(main.httpx, "Client", FakeClient)
    with pytest.raises(main.HTTPException) as error:
        main._load_verified_usi_profile("subject-verified-1")
    assert error.value.status_code == 502
    assert error.value.detail["code"] == "USI_PROFILE_SCHEMA_INVALID"


def test_usi_profile_provider_maps_persisted_preferences(monkeypatch):
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.internal")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-provider-token-with-at-least-32-bytes")

    class FakeResponse:
        status_code = 200
        def json(self):
            return {
                "subject_id": "subject-verified-1", "profile_version": 9,
                "preferences": [{"preference_id": "p1", "attribute": "classic", "weight": 0.6, "active": True}],
            }

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def get(self, url, headers):
            assert url.endswith("/v1/profiles/subject-verified-1")
            assert headers["Authorization"].startswith("Bearer ")
            return FakeResponse()

    monkeypatch.setattr(main.httpx, "Client", FakeClient)
    profile = main._load_verified_usi_profile("subject-verified-1")
    assert profile.version == "9"
    assert profile.preferences[0].attribute == "classic"
    assert profile.preferences[0].weight == 0.6
