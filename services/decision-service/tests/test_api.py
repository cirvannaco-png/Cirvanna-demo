import hashlib
import hmac
import json
import os
import time

os.environ.setdefault("DECISION_SERVICE_TOKEN", "decision-service-test-token-32-bytes-min")
os.environ.setdefault("FCI_EVIDENCE_HMAC_SECRET", "fci-provider-test-key-minimum-32-bytes")
os.environ.setdefault("NPL_EVIDENCE_HMAC_SECRET", "npl-provider-test-key-minimum-32-bytes")
os.environ.setdefault("CULTURAL_IDENTITY_HMAC_SECRET", "culture-provider-test-key-minimum-32-bytes")

import pytest
from fastapi.testclient import TestClient
from app import main


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv("DECISION_SERVICE_TOKEN", "decision-service-test-token-32-bytes-min")
    monkeypatch.setenv("FCI_EVIDENCE_HMAC_SECRET", "fci-provider-test-key-minimum-32-bytes")
    monkeypatch.setenv("NPL_EVIDENCE_HMAC_SECRET", "npl-provider-test-key-minimum-32-bytes")
    monkeypatch.setenv("CULTURAL_IDENTITY_HMAC_SECRET", "culture-provider-test-key-minimum-32-bytes")


@pytest.fixture
def client():
    with TestClient(main.app) as value:
        yield value


def signed_fit(fit: dict) -> str:
    parsed = main.FitEvidenceIn.model_validate(fit)
    payload = main.canonical_fit_payload(parsed)
    return hmac.new(os.environ["FCI_EVIDENCE_HMAC_SECRET"].encode(), payload, hashlib.sha256).hexdigest()


def signed_npl(body: dict) -> str:
    from npl import canonical_npl_evidence_payload
    canonical = canonical_npl_evidence_payload(
        body["request_id"], body["context"]["user_id"], body["candidate_id"],
        body["candidate_attributes"], body["negative_preferences"],
    )
    return hmac.new(os.environ["NPL_EVIDENCE_HMAC_SECRET"].encode(), canonical, hashlib.sha256).hexdigest()


def signed_cultural(body: dict) -> str:
    from cultural_identity import canonical_cultural_evidence_payload
    canonical = canonical_cultural_evidence_payload(
        body["request_id"], body["context"]["user_id"], body["candidate_id"],
        body["candidate_attributes"], body["candidate_attributes_complete"],
        body.get("cultural_requirements", []),
    )
    return hmac.new(os.environ["CULTURAL_IDENTITY_HMAC_SECRET"].encode(), canonical, hashlib.sha256).hexdigest()


def request_body(**overrides):
    body = {
        "request_id": "req-eligibility-001",
        "candidate_id": "catalog-product-001",
        "policy_version": "marketplace-policy-1",
        "context": {
            "user_id": "user-001", "age_years": 21, "location": "Nairobi",
            "occasion": "everyday", "climate": "warm",
        },
        "eepl_policy": {
            "policy_id": "standard-marketplace", "policy_version": "1.0.0",
            "minimum_age": 18, "allowed_locations": ["Nairobi"],
            "allowed_occasions": ["everyday"], "allowed_climates": ["warm"],
        },
        "usi_profile": {
            "profile_id": "profile-001", "user_id": "user-001", "version": "usi-v1",
            "preferences": [
                {"preference_id": "style-001", "user_id": "user-001", "attribute": "minimal", "weight": 1.0},
                {"preference_id": "style-002", "user_id": "user-001", "attribute": "cotton", "weight": 0.5},
            ],
        },
        "candidate_attributes": ["minimal", "cotton", "blue"],
        "candidate_attributes_complete": True,
        "negative_preferences": [],
        "fit_estimate": {
            "estimate_id": "fit-001", "user_id": "user-001", "candidate_id": "catalog-product-001",
            "model_version": "fci-test-model", "calibrated": True, "confidence": 0.86,
            "lower_bound": 0.80, "upper_bound": 0.91, "calibration_version": "fci-calibration-test-1",
            "evidence_ids": ["body-measurement-record-001", "brand-size-chart-001"],
            "required_evidence_fields": ["body_measurements", "garment_size_chart", "garment_geometry"],
            "observed_evidence_fields": ["body_measurements", "garment_size_chart", "garment_geometry"],
            "interval_level": 0.95,
        },
        "upstream_signals": [
            {"signal_id": "safety-001", "kind": "safety", "state": "pass", "reason_code": "SAFE",
             "explanation": "Independent product safety review passed.", "source_version": "safety-v1"},
            {"signal_id": "legal-001", "kind": "legal_eligibility", "state": "pass", "reason_code": "LEGAL",
             "explanation": "Regional listing eligibility passed.", "source_version": "legal-v1"},
            {"signal_id": "hard-001", "kind": "user_hard_constraint", "state": "pass", "reason_code": "HARD",
             "explanation": "Declared hard constraints were checked.", "source_version": "constraints-v1"},
        ],
        "minimum_fit_confidence": 0.70,
        "minimum_alignment_score": 0.60,
    }
    body.update(overrides)
    body["fit_estimate_signature"] = signed_fit(body["fit_estimate"])
    body["npl_evidence_signature"] = signed_npl(body)
    body["cultural_evidence_signature"] = signed_cultural(body)
    return body


def headers():
    return {"Authorization": "Bearer decision-service-test-token-32-bytes-min"}


def test_health_capabilities_and_readiness_are_factual(client):
    assert client.get("/health").json()["status"] == "alive"
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["fci_prediction_model_available"] is False
    caps = client.get("/capabilities").json()
    assert caps["catacaci_cal_arbitration"] is True
    assert caps["eepl_policy_evaluation"] is True
    assert caps["fci_prediction_model_available"] is False
    assert caps["virtual_twin_generation"] is False


def test_decision_endpoint_requires_internal_authentication(client):
    assert client.post("/v1/eligibility/evaluate", json=request_body()).status_code == 401


def test_missing_internal_token_configuration_fails_closed(client, monkeypatch):
    monkeypatch.delenv("DECISION_SERVICE_TOKEN", raising=False)
    assert client.get("/ready").status_code == 503
    assert client.post("/v1/eligibility/evaluate", json=request_body(), headers=headers()).status_code == 503


def test_full_eligibility_pipeline_calls_real_cal_and_only_show_authorizes_display(client):
    response = client.post("/v1/eligibility/evaluate", json=request_body(), headers=headers())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["decision"] == "SHOW"
    assert result["may_display"] is True
    assert result["gates"]["eepl"]["verdict"] == "pass"
    assert result["gates"]["npl"]["blocked"] is False
    assert result["gates"]["usi"]["verdict"] == "pass"
    assert result["gates"]["cultural_identity"]["verdict"] == "pass"
    assert result["gates"]["confidence"]["status"] == "ready"
    assert result["gates"]["confidence"]["coverage_ratio"] == 1.0
    assert result["gates"]["fci"]["calibrated"] is True
    assert result["policy"]["minimum_fit_confidence"] == 0.70
    assert any(signal.startswith("eepl:") for signal in result["arbitration"]["evaluated_signal_ids"])



def test_cultural_requirement_is_evaluated_by_canonical_pipeline(client):
    body = request_body()
    body["cultural_requirements"] = [{
        "requirement_id": "no-sleeveless",
        "declaration_id": "decl-001",
        "user_id": "user-001",
        "attribute": "sleeveless",
        "kind": "forbidden_attribute",
        "hard": True,
        "active": True,
    }]
    body["candidate_attributes"].append("sleeveless")
    body["npl_evidence_signature"] = signed_npl(body)
    body["cultural_evidence_signature"] = signed_cultural(body)
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["decision"] == "BLOCK"
    assert data["gates"]["cultural_identity"]["verdict"] == "block"
    assert data["may_display"] is False


def test_foreign_user_cultural_declaration_is_rejected(client):
    body = request_body()
    body["cultural_requirements"] = [{
        "requirement_id": "foreign-req",
        "declaration_id": "decl-foreign",
        "user_id": "another-user",
        "attribute": "long-sleeve",
        "kind": "required_attribute",
    }]
    body["cultural_evidence_signature"] = "0" * 64
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_DECISION_EVIDENCE"


def test_incomplete_signed_fit_evidence_routes_to_review(client):
    body = request_body()
    body["fit_estimate"]["observed_evidence_fields"] = ["body_measurements"]
    body["fit_estimate_signature"] = signed_fit(body["fit_estimate"])
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["decision"] == "REVIEW"
    assert data["gates"]["confidence"]["status"] == "insufficient_evidence"
    assert set(data["gates"]["confidence"]["missing_fields"]) == {"garment_size_chart", "garment_geometry"}



def test_cultural_declaration_tampering_is_rejected(client):
    body = request_body()
    body["cultural_requirements"] = [{
        "requirement_id": "tampered", "declaration_id": "decl-1",
        "user_id": "user-001", "attribute": "long-sleeve",
        "kind": "required_attribute", "hard": True, "active": True,
    }]
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "UNTRUSTED_CULTURAL_EVIDENCE"

def test_npl_tampering_is_rejected_before_cal(client):
    body = request_body()
    body["negative_preferences"] = [{
        "preference_id": "tampered", "user_id": "user-001",
        "target_type": "attribute", "target_value": "blue",
        "source": "user_declared", "active": True,
    }]
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "UNTRUSTED_NPL_EVIDENCE"


def test_foreign_user_npl_evidence_is_rejected(client):
    body = request_body()
    body["negative_preferences"] = [{
        "preference_id": "foreign", "user_id": "another-user",
        "target_type": "attribute", "target_value": "blue",
        "source": "user_declared", "active": True,
    }]
    body["npl_evidence_signature"] = signed_npl(body) if False else "0" * 64
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_NPL_EVIDENCE"

def test_npl_hard_veto_beats_high_fit_confidence(client):
    body = request_body()
    body["negative_preferences"] = [{
        "preference_id": "no-blue", "user_id": "user-001", "target_type": "attribute",
        "target_value": "blue", "source": "user_declared", "active": True,
    }]
    body["fit_estimate_signature"] = signed_fit(body["fit_estimate"])
    body["npl_evidence_signature"] = signed_npl(body)
    result = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert result.status_code == 200
    assert result.json()["decision"] == "BLOCK"
    assert result.json()["may_display"] is False
    assert result.json()["gates"]["npl"]["blocked"] is True


def test_untrusted_fit_evidence_is_rejected_before_cal(client):
    body = request_body()
    body["fit_estimate_signature"] = "0" * 64
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "UNTRUSTED_FIT_EVIDENCE"


def test_signed_but_uncalibrated_fit_evidence_routes_to_review(client):
    body = request_body()
    body["fit_estimate"] = {
        "estimate_id": "fit-unverified", "user_id": "user-001", "candidate_id": "catalog-product-001",
        "model_version": "untrusted-candidate-model", "calibrated": False,
    }
    body["fit_estimate_signature"] = signed_fit(body["fit_estimate"])
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 200
    assert response.json()["decision"] == "REVIEW"
    assert response.json()["may_display"] is False
    assert response.json()["gates"]["fci"]["confidence"] is None


def test_missing_required_upstream_gate_routes_to_review(client):
    body = request_body()
    body["upstream_signals"] = [item for item in body["upstream_signals"] if item["kind"] != "safety"]
    body["fit_estimate_signature"] = signed_fit(body["fit_estimate"])
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 200
    assert response.json()["decision"] == "REVIEW"
    assert response.json()["may_display"] is False


def test_candidate_user_or_fit_identity_mismatch_is_rejected(client):
    body = request_body()
    body["fit_estimate"]["candidate_id"] = "other-product"
    body["fit_estimate_signature"] = signed_fit(body["fit_estimate"])
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 422


def test_client_cannot_inject_generated_cal_signal_kinds(client):
    body = request_body()
    body["upstream_signals"].append({
        "signal_id": "injected-npl", "kind": "npl_hard_negative", "state": "pass",
        "reason_code": "FAKE_PASS", "explanation": "Attempt to bypass NPL.",
    })
    body["fit_estimate_signature"] = signed_fit(body["fit_estimate"])
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 422
