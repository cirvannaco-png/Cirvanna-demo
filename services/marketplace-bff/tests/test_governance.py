import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app import governance


def run_governance(subject_id, candidates):
    return asyncio.run(governance.govern_candidates(subject_id, candidates))


class FakeResponse:
    def __init__(self, payload=None, status_code=200, invalid_json=False):
        self.payload = payload
        self.status_code = status_code
        self.invalid_json = invalid_json

    def json(self):
        if self.invalid_json:
            raise ValueError("invalid json")
        return self.payload


class GovernanceTransport:
    def __init__(self, decisions=None, evidence_mode=None, decision_status=None, decision_mode=None):
        self.decisions = decisions or {}
        self.evidence_mode = evidence_mode
        self.decision_status = decision_status or {}
        self.decision_mode = decision_mode or {}
        self.evidence_calls = []
        self.decision_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        if url.endswith("/v1/decision-evidence"):
            self.evidence_calls.append(json)
            if self.evidence_mode == "http_error":
                return FakeResponse({"detail": "unavailable"}, status_code=503)
            now = datetime.now(timezone.utc)
            issued_at = now
            expires_at = now + timedelta(seconds=30)
            if self.evidence_mode == "stale":
                issued_at = now - timedelta(seconds=90)
            subject_id = json["subject_id"]
            candidate_id = json["candidate_id"]
            request_id = json["request_id"]
            if self.evidence_mode == "foreign_subject":
                subject_id = "some-other-user"
            if self.evidence_mode == "foreign_candidate":
                candidate_id = "different-candidate"
            decision_request = {
                "request_id": request_id,
                "candidate_id": candidate_id,
                "policy_version": "decision-pipeline-1.0.0",
                "context": {
                    "user_id": subject_id,
                    "age_years": None,
                    "location": None,
                    "occasion": None,
                    "climate": None,
                },
                "eepl_policy": {
                    "policy_id": "marketplace-default",
                    "policy_version": "1.0.0",
                    "minimum_age": None,
                    "maximum_age": None,
                    "allowed_locations": [],
                    "allowed_occasions": [],
                    "allowed_climates": [],
                    "required_context": [],
                },
                "usi_profile": {
                    "profile_id": "profile-test",
                    "user_id": subject_id,
                    "version": "1",
                    "preferences": [{
                        "preference_id": "pref-test",
                        "user_id": subject_id,
                        "attribute": "linen",
                        "weight": 1.0,
                        "active": True,
                    }],
                },
                "candidate_attributes": ["linen"],
                "candidate_attributes_complete": True,
                "negative_preferences": [],
                "cultural_requirements": [],
                "cultural_evidence_signature": "c" * 64,
                "fit_estimate": {
                    "estimate_id": "fit-test",
                    "user_id": subject_id,
                    "candidate_id": candidate_id,
                    "model_version": "fit-test-v1",
                    "calibrated": False,
                    "confidence": None,
                    "lower_bound": None,
                    "upper_bound": None,
                    "calibration_version": None,
                    "evidence_ids": [],
                    "required_evidence_fields": [],
                    "observed_evidence_fields": [],
                    "interval_level": 0.95,
                },
                "fit_estimate_signature": "f" * 64,
                "npl_evidence_signature": "n" * 64,
                "upstream_signals": [],
                "minimum_fit_confidence": 0.70,
                "minimum_alignment_score": 0.60,
            }
            return FakeResponse({
                "request_id": request_id,
                "subject_id": subject_id,
                "candidate_id": candidate_id,
                "issued_at": issued_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "decision_request": decision_request,
            })
        if url.endswith("/v1/eligibility/evaluate"):
            self.decision_calls.append(json)
            candidate_id = json["candidate_id"]
            if self.decision_status.get(candidate_id) == "http_error":
                return FakeResponse({"detail": "unavailable"}, status_code=503)
            if self.decision_mode.get(candidate_id) == "invalid_json":
                return FakeResponse(invalid_json=True)
            result = self.decisions.get(candidate_id, ("SHOW", True))
            verdict, may_display = result
            response_candidate_id = candidate_id
            response_request_id = json["request_id"]
            if self.decision_mode.get(candidate_id) == "foreign_candidate":
                response_candidate_id = "different-candidate"
            if self.decision_mode.get(candidate_id) == "foreign_request":
                response_request_id = "different-request"
            return FakeResponse({
                "candidate_id": response_candidate_id,
                "decision": verdict,
                "may_display": may_display,
                "arbitration": {
                    "request_id": response_request_id,
                    "policy_version": "test-policy-1",
                },
            })
        raise AssertionError(f"Unexpected governance endpoint: {url}")


def configure_gateway(monkeypatch, transport):
    monkeypatch.setenv("GOVERNANCE_EVIDENCE_API_URL", "https://evidence.example.test")
    monkeypatch.setenv("GOVERNANCE_EVIDENCE_API_TOKEN", "evidence-service-token-at-least-thirty-two-bytes")
    monkeypatch.setenv("DECISION_SERVICE_API_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_SERVICE_TOKEN", "decision-service-token-at-least-thirty-two-bytes")
    monkeypatch.setattr(governance.httpx, "AsyncClient", lambda **kwargs: transport)


def test_only_exact_cal_show_authorizes_display_and_overwrites_upstream_claims(monkeypatch):
    transport = GovernanceTransport(decisions={"variant-1": ("SHOW", True)})
    configure_gateway(monkeypatch, transport)

    result = run_governance("user-42", [{
        "variant_id": "variant-1",
        "product_name": "linen shirt",
        "display_authorized": False,
        "decision_status": "BLOCK",
        "may_display": False,
    }])

    assert result["candidate_count"] == 1
    candidate = result["candidates"][0]
    assert candidate["product_name"] == "linen shirt"
    assert candidate["display_authorized"] is True
    assert candidate["decision_status"] == "SHOW"
    assert candidate["cal_decision"]["verdict"] == "SHOW"
    assert candidate["cal_decision"]["may_display"] is True
    assert len(transport.evidence_calls) == 1
    assert len(transport.decision_calls) == 1
    assert transport.evidence_calls[0]["subject_id"] == "user-42"
    assert transport.decision_calls[0]["context"]["user_id"] == "user-42"


def test_block_review_and_candidate_without_stable_id_are_never_returned(monkeypatch):
    transport = GovernanceTransport(decisions={
        "block-1": ("BLOCK", False),
        "review-1": ("REVIEW", False),
    })
    configure_gateway(monkeypatch, transport)

    result = run_governance("user-42", [
        {"variant_id": "block-1", "product_name": "blocked product"},
        {"variant_id": "review-1", "product_name": "review product"},
        {"product_name": "no stable ID product"},
    ])

    assert result["candidates"] == []
    assert result["display_authorized"] is False
    assert result["decision_status"] == "NO_SHOW"
    assert len(transport.evidence_calls) == 2
    assert len(transport.decision_calls) == 2
    assert "blocked product" not in str(result)
    assert "review product" not in str(result)
    assert "no stable ID product" not in str(result)


def test_stale_evidence_is_rejected_before_cal_is_called(monkeypatch):
    transport = GovernanceTransport(evidence_mode="stale")
    configure_gateway(monkeypatch, transport)

    result = run_governance("user-42", [
        {"variant_id": "variant-1", "product_name": "stale product"},
    ])

    assert result["candidates"] == []
    assert result["display_authorized"] is False
    assert transport.decision_calls == []


@pytest.mark.parametrize("evidence_mode", ["foreign_subject", "foreign_candidate"])
def test_foreign_subject_or_candidate_evidence_is_rejected(monkeypatch, evidence_mode):
    transport = GovernanceTransport(evidence_mode=evidence_mode)
    configure_gateway(monkeypatch, transport)

    result = run_governance("user-42", [
        {"variant_id": "variant-1", "product_name": "foreign evidence product"},
    ])

    assert result["candidates"] == []
    assert transport.decision_calls == []


@pytest.mark.parametrize("decision_mode", ["foreign_candidate", "foreign_request", "invalid_json"])
def test_malformed_or_mismatched_cal_responses_fail_closed(monkeypatch, decision_mode):
    transport = GovernanceTransport(decision_mode={"variant-1": decision_mode})
    configure_gateway(monkeypatch, transport)

    result = run_governance("user-42", [
        {"variant_id": "variant-1", "product_name": "mismatched product"},
    ])

    assert result["candidates"] == []
    assert result["display_authorized"] is False


def test_upstream_failure_suppresses_only_that_candidate_and_never_trusts_retrieval_flags(monkeypatch):
    transport = GovernanceTransport(
        decisions={"show-1": ("SHOW", True)},
        decision_status={"down-1": "http_error"},
    )
    configure_gateway(monkeypatch, transport)

    result = run_governance("user-42", [
        {"variant_id": "show-1", "product_name": "approved product", "display_authorized": True},
        {"variant_id": "down-1", "product_name": "unavailable product", "display_authorized": True},
    ])

    assert [candidate["variant_id"] for candidate in result["candidates"]] == ["show-1"]
    assert result["candidates"][0]["cal_decision"]["verdict"] == "SHOW"
    assert "unavailable product" not in str(result)
    assert result["governance_status"] == "CAL_PARTIAL_FAIL_CLOSED"


def test_missing_service_configuration_suppresses_every_candidate(monkeypatch):
    for name in (
        "GOVERNANCE_EVIDENCE_API_URL",
        "GOVERNANCE_EVIDENCE_API_TOKEN",
        "DECISION_SERVICE_API_URL",
        "DECISION_SERVICE_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    result = run_governance("user-42", [
        {"variant_id": "variant-1", "product_name": "unconfigured product"},
    ])

    assert result["candidates"] == []
    assert result["display_authorized"] is False
    assert result["decision_status"] == "PENDING_CAL"
    assert result["governance_status"] == "CAL_GATE_NOT_CONNECTED"
