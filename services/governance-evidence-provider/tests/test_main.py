from datetime import datetime, timezone
import hashlib
import hmac
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app import main


USER = "user-42"
CANDIDATE = "7f2d2c1a-2b3c-4d5e-8f90-123456789abc"
PRODUCT = "c62a8a6f-893e-4b99-a4e7-8a118341ed10"
TOKEN = "test-evidence-provider-token-which-is-long-enough"
POLICY_SECRET = "policy-evidence-test-secret-minimum-32-bytes"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("EVIDENCE_PROVIDER_TOKEN", TOKEN)
    monkeypatch.setenv("POLICY_EVIDENCE_HMAC_SECRET", POLICY_SECRET)
    with TestClient(main.app) as c:
        yield c


def request_payload():
    return {"request_id": str(uuid.uuid4()), "subject_id": USER, "candidate_id": CANDIDATE,
            "catalog_product_id": PRODUCT, "requested_at": datetime.now(timezone.utc).isoformat()}


def valid_source(source: str, payload: dict) -> dict:
    if source == "CATALOG_API_URL":
        return {"product_id": PRODUCT, "status": "active", "attributes_complete": True, "name": "Linen Shirt", "category": "tops", "brand": "Test Brand", "attributes": {"sleeve_length": "long", "material": "linen"}}
    if source == "NPL_SERVICE_URL":
        return {"request_id": payload["request_id"], "user_id": USER, "candidate_id": CANDIDATE,
                "negative_preferences": [], "npl_evidence_signature": "a" * 64, "blocked": False}
    if source == "CULTURAL_IDENTITY_SERVICE_URL":
        return {"request_id": payload["request_id"], "user_id": USER, "candidate_id": CANDIDATE,
                "cultural_requirements": [], "cultural_evidence_signature": "b" * 64, "verdict": "PASS"}
    if source == "USI_PROFILE_API_URL":
        return {"usi_profile": {"profile_id": "profile-1", "user_id": USER, "version": "1", "preferences": [{"preference_id": "p1", "user_id": USER, "attribute": "linen", "weight": 1.0, "active": True}]},
                "eepl_policy": {"policy_id": "test-policy", "policy_version": "1.0.0", "required_context": []}}
    if source == "USER_CONTEXT_API_URL":
        return {"user_id": USER, "context": {"user_id": USER, "age_years": 25, "location": "Nakuru", "occasion": "casual", "climate": "warm"}}
    if source == "FIT_EVIDENCE_API_URL":
        return {"generated_at": datetime.now(timezone.utc).isoformat(),
                "fit_estimate": {"estimate_id": "fit-1", "user_id": USER, "candidate_id": CANDIDATE, "model_version": "test-model", "calibrated": True, "confidence": 0.9, "lower_bound": 0.8, "upper_bound": 0.95, "calibration_version": "cal-1", "evidence_ids": ["e1"], "required_evidence_fields": ["body_measurements", "garment_measurements"], "observed_evidence_fields": ["body_measurements", "garment_measurements"], "interval_level": 0.95},
                "fit_estimate_signature": "c" * 64}
    if source == "POLICY_EVIDENCE_API_URL":
        signals = [
            {"signal_id": "safe-1", "kind": "safety", "state": "pass", "reason_code": "SAFE", "explanation": "Safety review passed", "required": True, "confidence": 1.0, "source_version": "policy-v1"},
            {"signal_id": "legal-1", "kind": "legal_eligibility", "state": "pass", "reason_code": "LEGAL", "explanation": "Legal eligibility passed", "required": True, "confidence": 1.0, "source_version": "policy-v1"},
            {"signal_id": "hard-1", "kind": "user_hard_constraint", "state": "pass", "reason_code": "HARD", "explanation": "Hard constraints checked", "required": True, "confidence": 1.0, "source_version": "policy-v1"},
        ]
        canonical = main._canonical_policy_evidence(payload["request_id"], USER, CANDIDATE, PRODUCT, payload["candidate_attributes"], signals)
        signature = hmac.new(os.environ["POLICY_EVIDENCE_HMAC_SECRET"].encode(), canonical, hashlib.sha256).hexdigest()
        return {"request_id": payload["request_id"], "user_id": USER, "candidate_id": CANDIDATE,
                "catalog_product_id": PRODUCT, "upstream_signals": signals, "policy_evidence_signature": signature}
    raise AssertionError(source)


def test_assembles_same_candidate_user_and_signed_evidence(client, monkeypatch):
    async def fake_request(_client, env_url, _env_token, _method, _path, payload=None):
        payload = payload or request_payload()
        return valid_source(env_url, payload)
    monkeypatch.setattr(main, "_request", fake_request)
    response = client.post("/v1/decision-evidence", headers={"Authorization": f"Bearer {TOKEN}"}, json=request_payload())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["subject_id"] == USER and data["candidate_id"] == CANDIDATE
    assert data["catalog_product_id"] == PRODUCT
    decision = data["decision_request"]
    assert decision["context"]["user_id"] == USER
    assert decision["usi_profile"]["user_id"] == USER
    assert decision["fit_estimate"]["user_id"] == USER
    assert decision["fit_estimate"]["candidate_id"] == CANDIDATE
    assert {signal["kind"] for signal in decision["upstream_signals"]} >= {"safety", "legal_eligibility", "user_hard_constraint"}
    assert len(decision["npl_evidence_signature"]) == 64
    assert len(decision["cultural_evidence_signature"]) == 64
    assert len(decision["fit_estimate_signature"]) == 64
    assert set(data["evidence_freshness"]) == {"npl_loaded_at", "cultural_requirements_loaded_at", "fit_estimate_generated_at", "candidate_attributes_loaded_at", "usi_profile_loaded_at", "user_context_loaded_at"}


@pytest.mark.parametrize("source,field,value,code", [
    ("NPL_SERVICE_URL", "user_id", "somebody-else", "EVIDENCE_BINDING_MISMATCH"),
    ("CULTURAL_IDENTITY_SERVICE_URL", "candidate_id", "other-candidate", "EVIDENCE_BINDING_MISMATCH"),
    ("NPL_SERVICE_URL", "npl_evidence_signature", "", "NPL_EVIDENCE_UNSIGNED"),
    ("CULTURAL_IDENTITY_SERVICE_URL", "cultural_evidence_signature", "short", "CULTURAL_EVIDENCE_UNSIGNED"),
    ("FIT_EVIDENCE_API_URL", "generated_at", "2000-01-01T00:00:00+00:00", "FIT_EVIDENCE_STALE"),
    ("USI_PROFILE_API_URL", "usi_profile", None, "USI_PROFILE_MISSING_OR_MISMATCHED"),
    ("POLICY_EVIDENCE_API_URL", "candidate_id", "someone-else", "POLICY_EVIDENCE_BINDING_MISMATCH"),
    ("POLICY_EVIDENCE_API_URL", "policy_evidence_signature", "", "POLICY_EVIDENCE_UNSIGNED"),
    ("POLICY_EVIDENCE_API_URL", "upstream_signals", None, "POLICY_EVIDENCE_MISSING"),
])
def test_rejects_mismatched_unsigned_stale_or_missing_evidence(client, monkeypatch, source, field, value, code):
    async def fake_request(_client, env_url, _env_token, _method, _path, payload=None):
        result = valid_source(env_url, payload or request_payload())
        if env_url == source:
            if field == "usi_profile" and value is None:
                result[field] = None
            else:
                result[field] = value
        return result
    monkeypatch.setattr(main, "_request", fake_request)
    response = client.post("/v1/decision-evidence", headers={"Authorization": f"Bearer {TOKEN}"}, json=request_payload())
    assert response.status_code in {401, 409, 422, 503}, response.text
    assert response.json()["detail"]["code"] == code


def test_rejects_missing_auth_and_noncanonical_candidate(client):
    assert client.post("/v1/decision-evidence", json=request_payload()).status_code == 401
    payload = request_payload(); payload["candidate_id"] = "variant-7"
    response = client.post("/v1/decision-evidence", headers={"Authorization": f"Bearer {TOKEN}"}, json=payload)
    assert response.status_code == 422


def test_unavailable_source_fails_closed(client, monkeypatch):
    async def unavailable(*_args, **_kwargs):
        raise HTTPException(503, detail={"code": "EVIDENCE_SOURCE_UNAVAILABLE"})
    monkeypatch.setattr(main, "_request", unavailable)
    response = client.post("/v1/decision-evidence", headers={"Authorization": f"Bearer {TOKEN}"}, json=request_payload())
    assert response.status_code == 503


@pytest.mark.parametrize("fit_health,expected_ready", [
    ({"ready": True, "fci_prediction_model_available": False, "calibration_report_valid": False}, False),
    ({"ready": True, "fci_prediction_model_available": True, "calibration_report_valid": False}, False),
    ({"ready": True, "fci_prediction_model_available": True, "calibration_report_valid": True}, True),
])
def test_readiness_requires_live_dependencies_and_validated_fit_model(client, monkeypatch, fit_health, expected_ready):
    for key in ("NPL_SERVICE_TOKEN", "CULTURAL_IDENTITY_SERVICE_TOKEN", "CATALOG_API_TOKEN",
                "USI_PROFILE_API_TOKEN", "USER_CONTEXT_API_TOKEN", "FIT_EVIDENCE_API_TOKEN", "POLICY_EVIDENCE_API_TOKEN"):
        monkeypatch.setenv(key, "test-secret-with-at-least-thirty-two-bytes")
    for key in ("NPL_SERVICE_URL", "CULTURAL_IDENTITY_SERVICE_URL", "CATALOG_API_URL",
                "USI_PROFILE_API_URL", "USER_CONTEXT_API_URL", "FIT_EVIDENCE_API_URL", "POLICY_EVIDENCE_API_URL"):
        monkeypatch.setenv(key, "https://"+key.lower()+".example.test")
    async def fake_request(_client, url_key, _token_key, _method, path, payload=None):
        if path == "/ready" and url_key == "FIT_EVIDENCE_API_URL":
            return fit_health
        if path == "/ready":
            return {"ready": True}
        raise AssertionError((url_key, path))
    monkeypatch.setattr(main, "_request", fake_request)
    response = client.get("/ready")
    if expected_ready:
        assert response.status_code == 200, response.text
        assert response.json()["ready"] is True
        assert response.json()["fci_model_available"] is True
    else:
        assert response.status_code == 503
        detail = response.json()["detail"]
        assert detail["ready"] is False
        assert detail["upstream_ready"]["fit_evidence"] is False
