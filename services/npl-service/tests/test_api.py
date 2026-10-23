from __future__ import annotations

import hashlib
import hmac
import pytest
from fastapi.testclient import TestClient
from app import main
from app.store import Base, engine_for_url

TOKEN = "npl-service-test-token-with-more-than-32-bytes"
SECRET = "npl-evidence-test-secret-with-more-than-32-bytes"

@pytest.fixture
def client(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'npl-test.sqlite'}"
    monkeypatch.setenv("NPL_DATABASE_URL", url)
    monkeypatch.setenv("NPL_SERVICE_TOKEN", TOKEN)
    monkeypatch.setenv("NPL_EVIDENCE_HMAC_SECRET", SECRET)
    engine_for_url.cache_clear()
    engine = engine_for_url(url)
    Base.metadata.create_all(engine)
    with TestClient(main.app) as test_client:
        yield test_client
    engine.dispose()
    engine_for_url.cache_clear()

def auth():
    return {"Authorization": f"Bearer {TOKEN}"}

def create_preference(client, *, user="user-1", preference="no-blue", source="learned_rejection"):
    response = client.post("/v1/preferences", headers=auth(), json={
        "user_id": user, "preference_id": preference, "target_type": "attribute",
        "target_value": "blue", "source": source, "rejection_threshold": 3,
    })
    assert response.status_code == 201, response.text
    return response.json()["preference"]

def rejection(client, preference, event, user="user-1"):
    return client.post(
        f"/v1/preferences/{preference}/rejections", headers=auth(),
        json={"user_id": user, "rejection_event_id": event},
    )

def test_readiness_requires_real_database_schema_and_secrets(client):
    response = client.get("/ready")
    assert response.status_code == 200, response.text
    assert response.json()["ready"] is True and response.json()["schema_ready"] is True

def test_internal_auth_is_required(client):
    assert client.get("/v1/preferences", params={"user_id": "user-1"}).status_code == 401

def test_rejection_events_are_durable_idempotent_and_thresholded(client):
    create_preference(client)
    assert rejection(client, "no-blue", "reject-1").json()["rejection_count"] == 1
    duplicate = rejection(client, "no-blue", "reject-1")
    assert duplicate.status_code == 200 and duplicate.json()["rejection_count"] == 1
    assert rejection(client, "no-blue", "reject-2").json()["hard_veto"] is False
    third = rejection(client, "no-blue", "reject-3")
    assert third.status_code == 200 and third.json()["hard_veto"] is True
    persisted = client.get("/v1/preferences", headers=auth(), params={"user_id": "user-1"})
    assert persisted.json()["preferences"][0]["rejection_event_ids"] == ["reject-1", "reject-2", "reject-3"]

def test_same_rejection_event_cannot_be_reused_for_another_preference(client):
    create_preference(client, preference="no-blue")
    create_preference(client, preference="no-red")
    assert rejection(client, "no-blue", "same-event").status_code == 200
    response = rejection(client, "no-red", "same-event")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "NPL_EVENT_OR_PREFERENCE_CONFLICT"

def test_preferences_are_scoped_by_user(client):
    create_preference(client, user="user-1")
    response = client.get("/v1/preferences", headers=auth(), params={"user_id": "user-2"})
    assert response.status_code == 200 and response.json()["preferences"] == []
    assert rejection(client, "no-blue", "foreign-event", user="user-2").status_code == 404

def test_retraction_is_explicit_auditable_and_idempotent(client):
    create_preference(client, source="user_declared")
    path = "/v1/preferences/no-blue/retract"
    first = client.post(path, headers=auth(), json={"user_id": "user-1", "correction_event_id": "correction-1"})
    assert first.status_code == 200 and first.json()["retracted"] is True
    second = client.post(path, headers=auth(), json={"user_id": "user-1", "correction_event_id": "correction-1"})
    assert second.status_code == 200 and second.json()["correction_event_id"] == "correction-1"
    conflict = client.post(path, headers=auth(), json={"user_id": "user-1", "correction_event_id": "correction-2"})
    assert conflict.status_code == 422

def test_evaluation_returns_signed_preferences_bound_to_request_and_candidate(client):
    create_preference(client, source="user_declared")
    request = {"request_id": "request-100", "user_id": "user-1", "candidate_id": "item-100", "candidate_attributes": ["blue", "cotton"]}
    response = client.post("/v1/evaluate", headers=auth(), json=request)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["blocked"] is True and data["hard_veto_preference_ids"] == ["no-blue"]
    from npl import canonical_npl_evidence_payload
    payload = canonical_npl_evidence_payload(request["request_id"], request["user_id"], request["candidate_id"], request["candidate_attributes"], data["negative_preferences"])
    expected = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(expected, data["npl_evidence_signature"])
    changed = canonical_npl_evidence_payload(request["request_id"], request["user_id"], "different-candidate", request["candidate_attributes"], data["negative_preferences"])
    assert not hmac.compare_digest(expected, hmac.new(SECRET.encode(), changed, hashlib.sha256).hexdigest())

def test_unconfigured_database_fails_readiness_closed(client, monkeypatch):
    monkeypatch.delenv("NPL_DATABASE_URL", raising=False)
    response = client.get("/ready")
    assert response.status_code == 503 and response.json()["detail"]["ready"] is False
