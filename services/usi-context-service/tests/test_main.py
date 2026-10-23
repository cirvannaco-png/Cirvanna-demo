import os
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("USI_DATABASE_URL", "sqlite:///./usi-import.db")
os.environ.setdefault("USI_ALLOW_SQLITE_TESTS", "1")
os.environ.setdefault("USI_AUTO_CREATE_SCHEMA", "true")

from app import main


TOKEN = "test-usi-context-service-token-at-least-32-bytes"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("USI_DATABASE_URL", f"sqlite:///{tmp_path / 'usi.db'}")
    monkeypatch.setenv("USI_ALLOW_SQLITE_TESTS", "1")
    monkeypatch.setenv("USI_AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("USI_SERVICE_TOKEN", TOKEN)
    main._engine.cache_clear()
    with TestClient(main.app) as c:
        yield c
    main._engine().dispose()
    main._engine.cache_clear()


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def profile_payload(user_id="user-1"):
    return {
        "user_id": user_id,
        "profile_id": "profile-" + user_id,
        "version": "1",
        "preferences": [{
            "preference_id": "pref-1", "user_id": user_id,
            "attribute": "linen", "weight": 1.0, "active": True,
        }],
        "eepl_policy": {
            "policy_id": "default-policy", "policy_version": "1.0.0",
            "minimum_age": 18, "maximum_age": None, "allowed_locations": [],
            "allowed_occasions": [], "allowed_climates": [], "required_context": [],
        },
        "user_confirmation": True,
    }


def test_profile_requires_auth_and_explicit_confirmation(client):
    assert client.get("/v1/profiles/user-1").status_code == 401
    denied = client.put("/v1/profiles/user-1", headers=auth(),
        json={**profile_payload(), "user_confirmation": False})
    assert denied.status_code == 400
    assert denied.json()["detail"]["code"] == "EXPLICIT_USER_CONFIRMATION_REQUIRED"


def test_profile_is_persistent_user_scoped_and_versioned(client):
    saved = client.put("/v1/profiles/user-1", headers=auth(), json=profile_payload())
    assert saved.status_code == 200, saved.text
    assert saved.json()["usi_profile"]["user_id"] == "user-1"
    assert saved.json()["eepl_policy"]["policy_id"] == "default-policy"
    loaded = client.get("/v1/profiles/user-1", headers=auth())
    assert loaded.status_code == 200
    assert loaded.json()["usi_profile"]["preferences"][0]["attribute"] == "linen"
    assert client.get("/v1/profiles/user-2", headers=auth()).status_code == 404

    updated = client.put("/v1/profiles/user-1", headers=auth(),
        json={**profile_payload(), "version": "2", "preferences": [{
            "preference_id": "pref-2", "user_id": "user-1",
            "attribute": "cotton", "weight": 0.8, "active": True,
        }]})
    assert updated.status_code == 200
    assert updated.json()["usi_profile"]["version"] == "2"
    db = main._session_factory()()
    try:
        events = db.query(main.USIChangeEvent).filter_by(user_id="user-1").all()
        assert [event.event_type for event in events] == ["profile_created", "profile_updated"]
    finally:
        db.close()


def test_profile_rejects_foreign_user_preference_and_path_mismatch(client):
    foreign = {**profile_payload(), "preferences": [{
        "preference_id": "pref-foreign", "user_id": "other-user",
        "attribute": "silk", "weight": 1.0, "active": True,
    }]}
    assert client.put("/v1/profiles/user-1", headers=auth(), json=foreign).status_code == 409
    assert client.put("/v1/profiles/user-2", headers=auth(), json=profile_payload("user-1")).status_code == 409


def test_context_requires_confirmation_and_is_user_bound(client):
    payload = {"user_id": "user-1", "age_years": 21, "location": "Nakuru",
        "occasion": "casual", "climate": "warm", "user_confirmation": True}
    assert client.get("/v1/context/user-1", headers=auth()).status_code == 404
    no_confirmation = client.put("/v1/context/user-1", headers=auth(), json={**payload, "user_confirmation": False})
    assert no_confirmation.status_code == 400
    saved = client.put("/v1/context/user-1", headers=auth(), json=payload)
    assert saved.status_code == 200
    assert saved.json()["context"]["location"] == "Nakuru"
    assert client.get("/v1/context/user-1", headers=auth()).json()["context"]["user_id"] == "user-1"
    mismatch = client.put("/v1/context/user-2", headers=auth(), json=payload)
    assert mismatch.status_code == 409
    db = main._session_factory()()
    try:
        assert db.query(main.USIChangeEvent).filter_by(user_id="user-1", event_type="context_updated").count() == 1
    finally:
        db.close()


def test_readiness_requires_database_token_and_schema(client):
    ready = client.get("/ready")
    assert ready.status_code == 200, ready.text
    assert ready.json()["ready"] is True
    assert ready.json()["durable_usi_profiles"] is True
    assert ready.json()["durable_user_context"] is True
