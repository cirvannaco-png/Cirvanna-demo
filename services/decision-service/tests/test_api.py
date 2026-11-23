import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone

os.environ.setdefault("AGE_EVIDENCE_HMAC_SECRET", "age-evidence-provider-test-key-minimum-32-bytes")
os.environ.setdefault("DECISION_SERVICE_TOKEN", "decision-service-test-token-32-bytes-min")
os.environ.setdefault("FCI_EVIDENCE_HMAC_SECRET", "fci-provider-test-key-minimum-32-bytes")
os.environ.setdefault("NPL_EVIDENCE_HMAC_SECRET", "npl-provider-test-key-minimum-32-bytes")
os.environ.setdefault("CULTURAL_IDENTITY_HMAC_SECRET", "culture-provider-test-key-minimum-32-bytes")

import pytest
from fastapi.testclient import TestClient
from app import main


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv("AGE_EVIDENCE_HMAC_SECRET", "age-evidence-provider-test-key-minimum-32-bytes")
    monkeypatch.setenv("DECISION_SERVICE_TOKEN", "decision-service-test-token-32-bytes-min")
    monkeypatch.setenv("FCI_EVIDENCE_HMAC_SECRET", "fci-provider-test-key-minimum-32-bytes")
    monkeypatch.setenv("NPL_EVIDENCE_HMAC_SECRET", "npl-provider-test-key-minimum-32-bytes")
    monkeypatch.setenv("CULTURAL_IDENTITY_HMAC_SECRET", "culture-provider-test-key-minimum-32-bytes")
    monkeypatch.setenv("CAL_REVIEW_OPERATOR_TOKEN", "cal-review-operator-test-token-32-bytes")
    monkeypatch.setenv("CATACACI_POLICY_ID", "standard-marketplace")
    monkeypatch.setenv("EEPL_POLICY_ID", "standard-marketplace")
    monkeypatch.setenv("CATACACI_POLICY_REGISTRY_JSON", json.dumps({
        "standard-marketplace": {
            "policy_version": "marketplace-policy-1",
            "minimum_fit_confidence": 0.70,
            "maximum_fit_confidence_disagreement": 0.10,
            "minimum_alignment_score": 0.60,
        }
    }))
    monkeypatch.setattr(main, "_redeem_age_attestation", lambda payload, signature: None)
    monkeypatch.setattr(main, "check_receipt_store", lambda: True)
    monkeypatch.setattr(main, "persist_decision_receipt", lambda receipt: {
        "receipt_id": "123e4567-e89b-42d3-a456-426614174000",
        "receipt_sha256": "a" * 64,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    monkeypatch.setenv("EEPL_POLICY_REGISTRY_JSON", json.dumps({
        "standard-marketplace": {
            "policy_version": "1.0.0", "minimum_age": None, "maximum_age": None,
            "allowed_locations": ["Nairobi"], "allowed_occasions": ["everyday"],
            "allowed_climates": ["warm"], "required_context": [],
        }
    }))


@pytest.fixture
def client():
    with TestClient(main.app) as value:
        yield value


def configure_server_policy(monkeypatch, *, minimum_age=None, maximum_age=None):
    monkeypatch.setenv("EEPL_POLICY_REGISTRY_JSON", json.dumps({
        "standard-marketplace": {
            "policy_version": "1.0.0", "minimum_age": minimum_age,
            "maximum_age": maximum_age, "allowed_locations": ["Nairobi"],
            "allowed_occasions": ["everyday"], "allowed_climates": ["warm"],
            "required_context": [],
        }
    }))


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
        "catalog_version": 7,
        "context": {
            "user_id": "user-001", "age_years": 21, "location": "Nairobi",
            "occasion": "everyday", "climate": "warm",
        },
        "eepl_policy": {
            "policy_id": "standard-marketplace", "policy_version": "1.0.0",
            "minimum_age": None, "allowed_locations": ["Nairobi"],
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
    }
    body.update(overrides)
    body["fit_estimate_signature"] = signed_fit(body["fit_estimate"])
    body["npl_evidence_signature"] = signed_npl(body)
    body["cultural_evidence_signature"] = signed_cultural(body)
    return body



def attach_age_attestation(body: dict, *, threshold_met: bool = True) -> None:
    from age_evidence import build_threshold_attestation, sign_threshold_attestation

    now = datetime.now(timezone.utc)
    attestation = build_threshold_attestation(
        subject_id=body["context"]["user_id"],
        request_id=body["request_id"],
        purpose="shopper_eligibility",
        policy_id=body["eepl_policy"]["policy_id"],
        policy_version=body["eepl_policy"]["policy_version"],
        threshold=json.loads(os.environ["EEPL_POLICY_REGISTRY_JSON"])["standard-marketplace"]["minimum_age"],
        threshold_met=threshold_met,
        provider_session_id="yoti-session-123",
        provider_evidence_id="yoti-evidence-123",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    body["age_attestation"] = attestation
    body["age_attestation_signature"] = sign_threshold_attestation(
        attestation, os.environ["AGE_EVIDENCE_HMAC_SECRET"]
    )


def test_unverified_client_age_is_ignored_and_age_policy_routes_to_review(client, monkeypatch):
    body = request_body()
    configure_server_policy(monkeypatch, minimum_age=18)
    body["eepl_policy"]["minimum_age"] = None
    body["context"]["age_years"] = 17
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["decision"] == "REVIEW"
    assert result["may_display"] is False
    assert result["gates"]["eepl"]["verdict"] == "review"
    assert "EEPL_REQUIRED_CONTEXT_MISSING_AGE" in result["gates"]["eepl"]["reason_codes"]
    assert result["age_evidence"]["used_for_eligibility"] is False
    assert result["age_evidence"]["status"] == "unverified_client_value"


def test_verified_yoti_threshold_attestation_is_used_by_eepl(client, monkeypatch):
    body = request_body()
    configure_server_policy(monkeypatch, minimum_age=18)
    body["eepl_policy"]["minimum_age"] = None
    body["context"]["age_years"] = 16
    attach_age_attestation(body, threshold_met=True)
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["decision"] == "SHOW"
    assert result["age_evidence"] == {
        "contract_version": "age-threshold-attestation-v1",
        "status": "verified_threshold_met",
        "used_for_eligibility": True,
        "threshold": 18,
    }


def test_verified_under_threshold_attestation_blocks_eligibility(client, monkeypatch):
    body = request_body()
    configure_server_policy(monkeypatch, minimum_age=18)
    body["eepl_policy"]["minimum_age"] = None
    attach_age_attestation(body, threshold_met=False)
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "BLOCK"
    assert response.json()["age_evidence"]["status"] == "verified_threshold_not_met"


def test_age_attestation_subject_binding_mismatch_is_rejected(client, monkeypatch):
    body = request_body()
    configure_server_policy(monkeypatch, minimum_age=18)
    body["eepl_policy"]["minimum_age"] = None
    attach_age_attestation(body)
    body["context"]["user_id"] = "different-user"
    # Other signed evidence is re-created for the altered request identity.
    body["fit_estimate"]["user_id"] = "different-user"
    body["fit_estimate_signature"] = signed_fit(body["fit_estimate"])
    body["npl_evidence_signature"] = signed_npl(body)
    body["cultural_evidence_signature"] = signed_cultural(body)
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AGE_EVIDENCE_POLICY_BINDING_INVALID"


def test_threshold_attestation_cannot_satisfy_maximum_age_policy(client, monkeypatch):
    body = request_body()
    configure_server_policy(monkeypatch, minimum_age=18, maximum_age=65)
    body["eepl_policy"]["minimum_age"] = None
    body["eepl_policy"]["maximum_age"] = None
    attach_age_attestation(body)
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "AGE_EVIDENCE_POLICY_UNSUPPORTED"


def headers():
    return {"Authorization": "Bearer decision-service-test-token-32-bytes-min"}


def test_health_capabilities_and_readiness_are_factual(client):
    assert client.get("/health").json()["status"] == "alive"
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["fci_prediction_model_available"] is False
    assert ready.json()["catacaci_policy_registry_configured"] is True
    caps = client.get("/capabilities").json()
    assert caps["catacaci_cal_arbitration"] is True
    assert caps["catacaci_server_owned_policy"] is True
    assert caps["eepl_policy_evaluation"] is True
    assert caps["fci_prediction_model_available"] is False
    assert caps["virtual_twin_generation"] is False



def test_client_cannot_override_server_owned_cal_thresholds(client):
    body = request_body()
    body["minimum_fit_confidence"] = 0.0
    body["minimum_alignment_score"] = 0.0
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 422


@pytest.mark.parametrize(
    "caller_policy_field",
    [
        {"cal_policy_id": "unregistered-policy"},
        {"policy_version": "stale-policy-version"},
    ],
)
def test_client_cannot_select_cal_policy_or_version(client, caller_policy_field):
    body = request_body(**caller_policy_field)
    response = client.post("/v1/eligibility/evaluate", json=body, headers=headers())
    assert response.status_code == 422


def test_unregistered_server_cal_policy_fails_closed(client, monkeypatch):
    monkeypatch.setenv("CATACACI_POLICY_ID", "unregistered-policy")
    response = client.post(
        "/v1/eligibility/evaluate", json=request_body(), headers=headers()
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SERVER_CAL_POLICY_UNAVAILABLE"


def test_readiness_fails_when_server_cal_policy_registry_is_missing(client, monkeypatch):
    monkeypatch.delenv("CATACACI_POLICY_REGISTRY_JSON", raising=False)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["catacaci_policy_registry_configured"] is False


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
    assert result["policy"]["id"] == "standard-marketplace"
    assert result["policy"]["version"] == "marketplace-policy-1"
    assert result["policy"]["minimum_fit_confidence"] == 0.70
    assert result["policy"]["maximum_fit_confidence_disagreement"] == 0.10
    assert result["policy"]["minimum_alignment_score"] == 0.60
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
    assert response.json()["detail"]["code"] == "INVALID_CULTURAL_EVIDENCE"


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


def test_decision_service_bridges_cil_feedback_queue_and_final_cal_decision(client, monkeypatch):
    monkeypatch.setenv("CIL_SERVICE_URL", "https://cil.internal")
    monkeypatch.setenv("CIL_SERVICE_TOKEN", "cil-service-token-that-is-at-least-32-bytes")
    monkeypatch.setenv("CIL_CAL_SERVICE_TOKEN", "cil-cal-service-token-that-is-at-least-32-bytes")

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self.payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def get(self, url, headers):
            assert url == "https://cil.internal/cal/review-queue"
            assert headers["Authorization"].startswith("Bearer cil-service-token")
            return FakeResponse({"items": [{"review_id": "review-1", "status": "pending"}]})
        async def post(self, url, json, headers):
            assert url == "https://cil.internal/cal/review-queue/review-1/decision"
            assert headers["Authorization"].startswith("Bearer cil-cal-service-token")
            assert json["verdict"] == "BLOCK"
            return FakeResponse({"review_id": "review-1", "status": "decided", "verdict": "BLOCK"})

    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)
    headers = {"Authorization": "Bearer decision-service-test-token-32-bytes-min"}
    queue = client.get("/v1/cal/feedback-reviews", headers=headers)
    assert queue.status_code == 200
    assert queue.json()["items"][0]["review_id"] == "review-1"

    decision = client.post(
        "/v1/cal/feedback-reviews/review-1/decision",
        headers={"Authorization": "Bearer cal-review-operator-test-token-32-bytes"},
        json={"verdict": "BLOCK", "decision_reference": "CAL-DECISION-1",
              "rationale": "Human review confirmed the recommendation should be blocked."},
    )
    assert decision.status_code == 200
    assert decision.json()["verdict"] == "BLOCK"


def test_production_decision_service_cannot_disable_cil_feedback_review_enforcement(monkeypatch):
    monkeypatch.setenv("CIRVANNA_ENVIRONMENT", "production")
    monkeypatch.setenv("CIL_CAL_REVIEW_ENFORCEMENT_REQUIRED", "false")
    assert main._cil_cal_review_enforcement_required() is True


def test_development_decision_service_can_keep_cil_feedback_review_optional(monkeypatch):
    monkeypatch.setenv("CIRVANNA_ENVIRONMENT", "development")
    monkeypatch.setenv("CIL_CAL_REVIEW_ENFORCEMENT_REQUIRED", "false")
    assert main._cil_cal_review_enforcement_required() is False


def test_cil_feedback_review_block_is_enforced_by_live_eligibility_evaluation(client, monkeypatch):
    monkeypatch.setenv("CIL_CAL_REVIEW_ENFORCEMENT_REQUIRED", "true")
    monkeypatch.setenv("CIL_SERVICE_URL", "https://cil.internal")
    monkeypatch.setenv("CIL_SERVICE_TOKEN", "cil-service-token-that-is-at-least-32-bytes")
    monkeypatch.setenv("CIL_CAL_SERVICE_TOKEN", "cil-cal-service-token-that-is-at-least-32-bytes")

    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "context_key": "warm-everyday",
                "decisions": [{
                    "product_id": "catalog-product-001",
                    "context_key": "warm-everyday",
                    "review_id": "feedback-review-001",
                    "verdict": "BLOCK",
                    "decision_reference": "CAL-FEEDBACK-001",
                    "decided_at": "2026-11-12T10:00:00+00:00",
                }],
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def post(self, url, json, headers):
            assert url == "https://cil.internal/cal/feedback-decisions"
            assert json == {
                "product_ids": ["catalog-product-001"],
                "context_key": "warm-everyday",
            }
            assert headers["Authorization"].startswith("Bearer cil-cal-service-token")
            return FakeResponse()

    monkeypatch.setattr(main.httpx, "Client", FakeClient)
    response = client.post(
        "/v1/eligibility/evaluate",
        json=request_body(),
        headers=headers(),
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["decision"] == "BLOCK"
    assert result["may_display"] is False
    assert result["gates"]["cil_feedback_review"]["applied_as_veto"] is True
    assert result["gates"]["cil_feedback_review"]["decision_reference"] == "CAL-FEEDBACK-001"
    assert any(
        reason["code"] == "CIL_FEEDBACK_REVIEW_BLOCK"
        for reason in result["arbitration"]["reasons"]
    )


def test_cil_feedback_review_show_never_overrides_normal_cal_decision(client, monkeypatch):
    monkeypatch.setenv("CIL_CAL_REVIEW_ENFORCEMENT_REQUIRED", "true")
    monkeypatch.setenv("CIL_SERVICE_URL", "https://cil.internal")
    monkeypatch.setenv("CIL_SERVICE_TOKEN", "cil-service-token-that-is-at-least-32-bytes")
    monkeypatch.setenv("CIL_CAL_SERVICE_TOKEN", "cil-cal-service-token-that-is-at-least-32-bytes")

    class FakeResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "context_key": "warm-everyday",
                "decisions": [{
                    "product_id": "catalog-product-001",
                    "context_key": "warm-everyday",
                    "review_id": "feedback-review-002",
                    "verdict": "SHOW",
                    "decision_reference": "CAL-FEEDBACK-002",
                    "decided_at": "2026-11-12T10:15:00+00:00",
                }],
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def post(self, url, json, headers):
            return FakeResponse()

    monkeypatch.setattr(main.httpx, "Client", FakeClient)
    response = client.post(
        "/v1/eligibility/evaluate",
        json=request_body(),
        headers=headers(),
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["decision"] == "SHOW"
    assert result["may_display"] is True
    assert result["gates"]["cil_feedback_review"]["applied_as_veto"] is False


def test_required_cil_feedback_review_enforcement_fails_closed_when_service_unavailable(client, monkeypatch):
    import httpx

    monkeypatch.setenv("CIL_CAL_REVIEW_ENFORCEMENT_REQUIRED", "true")
    monkeypatch.setenv("CIL_SERVICE_URL", "https://cil.internal")
    monkeypatch.setenv("CIL_SERVICE_TOKEN", "cil-service-token-that-is-at-least-32-bytes")
    monkeypatch.setenv("CIL_CAL_SERVICE_TOKEN", "cil-cal-service-token-that-is-at-least-32-bytes")

    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("CIL unavailable")

    monkeypatch.setattr(main.httpx, "post", unavailable)
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def post(self, *args, **kwargs):
            raise httpx.ConnectError("CIL unavailable")
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    response = client.post(
        "/v1/eligibility/evaluate",
        json=request_body(),
        headers=headers(),
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CIL_CAL_FEEDBACK_DECISION_UNAVAILABLE"


def test_durable_receipt_requires_strict_positive_catalog_version(client):
    missing = request_body()
    missing.pop("catalog_version")
    assert client.post("/v1/eligibility/evaluate", json=missing, headers=headers()).status_code == 422
    coerced = request_body(catalog_version="7")
    assert client.post("/v1/eligibility/evaluate", json=coerced, headers=headers()).status_code == 422
    invalid = request_body(catalog_version=0)
    assert client.post("/v1/eligibility/evaluate", json=invalid, headers=headers()).status_code == 422
