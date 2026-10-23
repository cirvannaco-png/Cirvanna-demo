from __future__ import annotations
import hashlib,hmac
import pytest
from fastapi.testclient import TestClient
from app import main
from app.store import Base,engine_for_url
from cultural_identity import canonical_cultural_evidence_payload

TOKEN="cultural-identity-service-token-longer-than-32"
SECRET="cultural-identity-evidence-signing-secret-over-32"

@pytest.fixture
def client(monkeypatch,tmp_path):
    url=f"sqlite:///{tmp_path/'cultural.sqlite'}"
    monkeypatch.setenv("CULTURAL_IDENTITY_DATABASE_URL",url)
    monkeypatch.setenv("CULTURAL_IDENTITY_ALLOW_SQLITE_TESTS","1")
    monkeypatch.setenv("CULTURAL_IDENTITY_SERVICE_TOKEN",TOKEN)
    monkeypatch.setenv("CULTURAL_IDENTITY_HMAC_SECRET",SECRET)
    engine=engine_for_url(url)
    Base.metadata.create_all(engine)
    with TestClient(main.app) as c:
        yield c
    engine.dispose()

def auth():return {"Authorization":f"Bearer {TOKEN}"}

def declaration(client,**overrides):
    body={"user_id":"user-1","declaration_id":"decl-1","confirmation_version":"policy-2026-01","user_confirmation":True,"requirements":[
        {"requirement_id":"req-sleeves","attribute":"long-sleeve","kind":"required_attribute","hard":True},
        {"requirement_id":"req-no-sleeveless","attribute":"sleeveless","kind":"forbidden_attribute","hard":True},
    ]}
    body.update(overrides)
    response=client.post("/v1/declarations",headers=auth(),json=body)
    assert response.status_code==201,response.text
    return response.json()

def test_readiness_requires_auth_database_schema_and_signing(client):
    response=client.get("/ready")
    assert response.status_code==200,response.text
    assert response.json()["ready"] and response.json()["schema_ready"]

def test_internal_auth_required(client):
    assert client.get("/v1/declarations",params={"user_id":"user-1"}).status_code==401

def test_declaration_requires_explicit_confirmation(client):
    body={"user_id":"user-1","declaration_id":"decl-1","confirmation_version":"v1","user_confirmation":False,"requirements":[{"requirement_id":"r1","attribute":"long-sleeve","kind":"required_attribute"}]}
    response=client.post("/v1/declarations",headers=auth(),json=body)
    assert response.status_code==400
    assert response.json()["detail"]["code"]=="EXPLICIT_DECLARATION_CONFIRMATION_REQUIRED"

def test_duplicate_requirement_ids_are_rejected(client):
    body={"user_id":"user-1","declaration_id":"decl-1","confirmation_version":"v1","user_confirmation":True,"requirements":[{"requirement_id":"r1","attribute":"long-sleeve","kind":"required_attribute"},{"requirement_id":"r1","attribute":"sleeveless","kind":"forbidden_attribute"}]}
    response=client.post("/v1/declarations",headers=auth(),json=body)
    assert response.status_code==422

def test_evaluation_binds_user_request_candidate_attributes_and_declarations(client):
    declaration(client)
    body={"request_id":"req-1","user_id":"user-1","candidate_id":"product-1","candidate_attributes":["cotton"],"candidate_attributes_complete":True}
    response=client.post("/v1/evaluate",headers=auth(),json=body)
    assert response.status_code==200,response.text
    data=response.json()
    assert data["verdict"]=="block"
    canonical=canonical_cultural_evidence_payload(body["request_id"],body["user_id"],body["candidate_id"],body["candidate_attributes"],body["candidate_attributes_complete"],data["cultural_requirements"])
    expected=hmac.new(SECRET.encode(),canonical,hashlib.sha256).hexdigest()
    assert hmac.compare_digest(expected,data["cultural_evidence_signature"])
    modified=canonical_cultural_evidence_payload(body["request_id"],body["user_id"],"other-product",body["candidate_attributes"],body["candidate_attributes_complete"],data["cultural_requirements"])
    assert not hmac.compare_digest(expected,hmac.new(SECRET.encode(),modified,hashlib.sha256).hexdigest())

def test_incomplete_catalog_metadata_routes_to_review(client):
    declaration(client)
    response=client.post("/v1/evaluate",headers=auth(),json={"request_id":"req-2","user_id":"user-1","candidate_id":"product-2","candidate_attributes":["cotton"],"candidate_attributes_complete":False})
    assert response.status_code==200
    assert response.json()["verdict"]=="review"

def test_declaration_retraction_is_audited_idempotent_and_user_scoped(client):
    declaration(client)
    response=client.post("/v1/declarations/decl-1/retract",headers=auth(),json={"user_id":"user-1","correction_event_id":"correction-1","user_confirmation":True})
    assert response.status_code==200 and response.json()["status"]=="retracted"
    again=client.post("/v1/declarations/decl-1/retract",headers=auth(),json={"user_id":"user-1","correction_event_id":"correction-1","user_confirmation":True})
    assert again.status_code==200 and again.json()["idempotent"] is True
    foreign=client.post("/v1/declarations/decl-1/retract",headers=auth(),json={"user_id":"user-2","correction_event_id":"correction-2","user_confirmation":True})
    assert foreign.status_code==404

def test_retracted_requirements_no_longer_apply_or_sign_as_active(client):
    declaration(client)
    client.post("/v1/declarations/decl-1/retract",headers=auth(),json={"user_id":"user-1","correction_event_id":"correction-1","user_confirmation":True})
    data=client.post("/v1/evaluate",headers=auth(),json={"request_id":"req-3","user_id":"user-1","candidate_id":"product-3","candidate_attributes":[],"candidate_attributes_complete":True}).json()
    assert data["verdict"]=="pass"
    assert data["cultural_requirements"]==[]

def test_sqlite_is_rejected_without_test_opt_in(client,monkeypatch):
    monkeypatch.delenv("CULTURAL_IDENTITY_ALLOW_SQLITE_TESTS",raising=False)
    response=client.get("/ready")
    assert response.status_code==503
    assert response.json()["detail"]["ready"] is False
