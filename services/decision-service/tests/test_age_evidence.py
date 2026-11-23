from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "identity-intelligence"))

from age_evidence.core import (
    AgeEvidenceError,
    CONTRACT_VERSION,
    build_threshold_attestation,
    sign_threshold_attestation,
    verify_threshold_attestation,
)
from age_evidence.yoti import YotiAVSClient, YotiProviderError

SECRET = "test-age-evidence-signing-key-with-at-least-32-bytes"
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


def payload(**overrides):
    value = {
        "contract_version": CONTRACT_VERSION,
        "jti": "123e4567-e89b-42d3-a456-426614174000",
        "issuer": "cirvanna-age-evidence-service",
        "provider": "yoti",
        "subject_id": "subject-opaque-1",
        "request_id": "request-opaque-1",
        "purpose": "age_dependent_eligibility",
        "policy_id": "marketplace-adult",
        "policy_version": "v3",
        "threshold": 18,
        "threshold_met": True,
        "provider_session_id": "session-opaque-1",
        "provider_evidence_id": "evidence-opaque-1",
        "issued_at": (NOW - timedelta(seconds=10)).isoformat(),
        "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
    }
    value.update(overrides)
    return value


class AgeEvidenceContractTests(unittest.TestCase):
    def test_signed_threshold_attestation_is_bound_to_subject_request_and_policy(self):
        attestation = payload()
        signature = sign_threshold_attestation(attestation, SECRET)
        self.assertTrue(verify_threshold_attestation(
            attestation, signature, SECRET,
            subject_id="subject-opaque-1",
            request_id="request-opaque-1",
            purpose="age_dependent_eligibility",
            policy_id="marketplace-adult",
            policy_version="v3",
            threshold=18,
            now=NOW,
        ))

    def test_boolean_threshold_binding_is_rejected(self):
        attestation = payload()
        signature = sign_threshold_attestation(attestation, SECRET)
        with self.assertRaises(AgeEvidenceError):
            verify_threshold_attestation(
                attestation, signature, SECRET,
                subject_id="subject-opaque-1",
                request_id="request-opaque-1",
                purpose="age_dependent_eligibility",
                policy_id="marketplace-adult",
                policy_version="v3",
                threshold=True,
                now=NOW,
            )

    def test_wrong_subject_or_policy_cannot_reuse_attestation(self):
        attestation = payload()
        signature = sign_threshold_attestation(attestation, SECRET)
        self.assertFalse(verify_threshold_attestation(
            attestation, signature, SECRET,
            subject_id="another-subject",
            request_id="request-opaque-1",
            purpose="age_dependent_eligibility",
            policy_id="marketplace-adult",
            policy_version="v3",
            threshold=18,
            now=NOW,
        ))
        self.assertFalse(verify_threshold_attestation(
            attestation, signature, SECRET,
            subject_id="subject-opaque-1",
            request_id="request-opaque-1",
            purpose="age_dependent_eligibility",
            policy_id="marketplace-adult",
            policy_version="v4",
            threshold=18,
            now=NOW,
        ))

    def test_expired_or_future_attestation_is_rejected(self):
        expired = payload(expires_at=(NOW - timedelta(seconds=1)).isoformat())
        signature = sign_threshold_attestation(expired, SECRET)
        self.assertFalse(verify_threshold_attestation(
            expired, signature, SECRET,
            subject_id="subject-opaque-1", request_id="request-opaque-1",
            purpose="age_dependent_eligibility", policy_id="marketplace-adult",
            policy_version="v3", threshold=18, now=NOW,
        ))
        future = payload(issued_at=(NOW + timedelta(minutes=1)).isoformat())
        signature = sign_threshold_attestation(future, SECRET)
        self.assertFalse(verify_threshold_attestation(
            future, signature, SECRET,
            subject_id="subject-opaque-1", request_id="request-opaque-1",
            purpose="age_dependent_eligibility", policy_id="marketplace-adult",
            policy_version="v3", threshold=18, now=NOW,
        ))

    def test_unapproved_attestation_provider_is_rejected(self):
        with self.assertRaises(AgeEvidenceError):
            sign_threshold_attestation(payload(provider="unapproved-provider"), SECRET)

    def test_raw_age_or_identity_fields_are_rejected(self):
        with self.assertRaises(AgeEvidenceError):
            sign_threshold_attestation(payload(age_years=21), SECRET)
        with self.assertRaises(AgeEvidenceError):
            sign_threshold_attestation(payload(date_of_birth="2000-01-01"), SECRET)

    def test_pending_provider_result_cannot_become_an_attestation(self):
        with self.assertRaises(AgeEvidenceError):
            build_threshold_attestation(
                subject_id="subject-opaque-1", request_id="request-opaque-1",
                purpose="age_dependent_eligibility", policy_id="marketplace-adult",
                policy_version="v3", threshold=18, threshold_met=None,
                provider_session_id="session-opaque-1", provider_evidence_id="evidence-opaque-1",
                issued_at=NOW, expires_at=NOW + timedelta(minutes=5),
            )

    def test_attestation_builder_contains_no_raw_age(self):
        attestation = build_threshold_attestation(
            subject_id="subject-opaque-1", request_id="request-opaque-1",
            purpose="age_dependent_eligibility", policy_id="marketplace-adult",
            policy_version="v3", threshold=18, threshold_met=True,
            provider_session_id="session-opaque-1", provider_evidence_id="evidence-opaque-1",
            issued_at=NOW, expires_at=NOW + timedelta(minutes=5),
        )
        self.assertNotIn("age_years", attestation)
        self.assertNotIn("date_of_birth", attestation)
        self.assertTrue(verify_threshold_attestation(
            attestation, sign_threshold_attestation(attestation, SECRET), SECRET,
            subject_id="subject-opaque-1", request_id="request-opaque-1",
            purpose="age_dependent_eligibility", policy_id="marketplace-adult",
            policy_version="v3", threshold=18, now=NOW,
        ))

    def test_signature_tampering_is_rejected(self):
        attestation = payload()
        signature = sign_threshold_attestation(attestation, SECRET)
        attestation["threshold_met"] = False
        self.assertFalse(verify_threshold_attestation(
            attestation, signature, SECRET,
            subject_id="subject-opaque-1", request_id="request-opaque-1",
            purpose="age_dependent_eligibility", policy_id="marketplace-adult",
            policy_version="v3", threshold=18, now=NOW,
        ))


class YotiAdapterTests(unittest.TestCase):
    def make_client(self, handler):
        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(transport=transport)
        return YotiAVSClient(
            "yoti-test-api-key-with-more-than-32-bytes",
            "12345678-1234-4234-8234-123456789012",
            client=http_client,
        )

    def test_client_rejects_untrusted_yoti_api_origins_and_timeouts(self):
        with self.assertRaises(ValueError):
            YotiAVSClient(
                "yoti-test-api-key-with-more-than-32-bytes",
                "12345678-1234-4234-8234-123456789012",
                base_url="https://attacker.example",
            )
        with self.assertRaises(ValueError):
            YotiAVSClient(
                "yoti-test-api-key-with-more-than-32-bytes",
                "12345678-1234-4234-8234-123456789012",
                base_url="http://age.yoti.com",
            )
        with self.assertRaises(ValueError):
            YotiAVSClient(
                "yoti-test-api-key-with-more-than-32-bytes",
                "12345678-1234-4234-8234-123456789012",
                timeout_seconds=0,
            )

    def test_session_uses_digital_id_only_and_disables_age_estimation(self):
        captured = {}
        def handler(request):
            captured["body"] = request.read().decode()
            self.assertEqual(request.headers["Yoti-Sdk-Id"], "12345678-1234-4234-8234-123456789012")
            self.assertTrue(request.headers["Authorization"].startswith("Bearer "))
            return httpx.Response(200, json={
                "id": "d1234567-1234-4234-8234-123456789012",
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
            })
        client = self.make_client(handler)
        session = client.create_over_session(
            threshold=18,
            reference_id="a" * 48,
            redirect_url="https://cirvanna.example/age/complete",
            cancel_url="https://cirvanna.example/age/cancel",
            privacy_policy_url="https://cirvanna.example/privacy",
            terms_url="https://cirvanna.example/terms",
        )
        self.assertEqual(session.session_id, "d1234567-1234-4234-8234-123456789012")
        self.assertNotIn("subject-opaque", session.reference_id)
        self.assertIn('"age_estimation_allowed":false', captured["body"])
        self.assertIn('"age_estimation":{"allowed":false}', captured["body"])
        self.assertIn('"doc_scan":{"allowed":false}', captured["body"])
        self.assertIn('"callback":{"url":"https://cirvanna.example/age/complete","auto":true}', captured["body"])
        self.assertNotIn('"notification_url"', captured["body"])
        client.close()

    def test_result_requires_exact_session_sdk_reference_and_threshold(self):
        body = {
            "id": "d1234567-1234-4234-8234-123456789012",
            "sdk_id": "12345678-1234-4234-8234-123456789012",
            "reference_id": "a" * 48,
            "type": "OVER",
            "digital_id": {"allowed": True, "threshold": 18, "age_estimation_allowed": False},
            "method": "DIGITAL_ID",
            "age": 18,
            "status": "COMPLETE",
            "evidence_id": "evidence-123",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
            "updated_at": "2026-11-23T12:01:00Z",
        }
        def handler(request):
            self.assertTrue(request.url.path.endswith("/result"))
            return httpx.Response(200, json=body)
        client = self.make_client(handler)
        result = client.get_threshold_result(
            session_id=body["id"], expected_reference_id="a" * 48, threshold=18,
        )
        self.assertEqual(result.state, "COMPLETE")
        self.assertIs(result.threshold_met, True)
        self.assertEqual(result.evidence_id, "evidence-123")
        client.close()

    def test_pending_yoti_session_without_method_remains_reviewable(self):
        body = {
            "id": "d1234567-1234-4234-8234-123456789012",
            "sdk_id": "12345678-1234-4234-8234-123456789012",
            "reference_id": "a" * 48,
            "type": "OVER",
            "digital_id": {"allowed": True, "threshold": 18},
            "status": "PENDING",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        }
        client = self.make_client(lambda request: httpx.Response(200, json=body))
        result = client.get_threshold_result(
            session_id=body["id"], expected_reference_id="a" * 48, threshold=18,
        )
        self.assertEqual(result.state, "PENDING")
        self.assertIsNone(result.threshold_met)
        client.close()

    def test_complete_result_from_non_digital_id_method_is_rejected(self):
        body = {
            "id": "d1234567-1234-4234-8234-123456789012",
            "sdk_id": "12345678-1234-4234-8234-123456789012",
            "reference_id": "a" * 48,
            "type": "OVER",
            "digital_id": {"allowed": True, "threshold": 18},
            "method": "AGE_ESTIMATION",
            "age": 18,
            "status": "COMPLETE",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        }
        client = self.make_client(lambda request: httpx.Response(200, json=body))
        with self.assertRaises(YotiProviderError):
            client.get_threshold_result(
                session_id=body["id"], expected_reference_id="a" * 48, threshold=18,
            )
        client.close()

    def test_under_threshold_digital_id_result_is_false_not_unknown(self):
        body = {
            "id": "d1234567-1234-4234-8234-123456789012",
            "sdk_id": "12345678-1234-4234-8234-123456789012",
            "reference_id": "a" * 48,
            "type": "OVER",
            "digital_id": {"allowed": True, "threshold": 18},
            "method": "DIGITAL_ID",
            "age": 18,
            "status": "FAIL",
            "evidence_id": "evidence-under-18",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        }
        client = self.make_client(lambda request: httpx.Response(200, json=body))
        result = client.get_threshold_result(
            session_id=body["id"], expected_reference_id="a" * 48, threshold=18,
        )
        self.assertEqual(result.state, "FAIL")
        self.assertIs(result.threshold_met, False)
        client.close()

    def test_terminal_result_with_wrong_threshold_value_is_rejected(self):
        body = {
            "id": "d1234567-1234-4234-8234-123456789012",
            "sdk_id": "12345678-1234-4234-8234-123456789012",
            "reference_id": "a" * 48,
            "type": "OVER",
            "digital_id": {"allowed": True, "threshold": 18},
            "method": "DIGITAL_ID",
            "age": 21,
            "status": "COMPLETE",
            "evidence_id": "evidence-123",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        }
        client = self.make_client(lambda request: httpx.Response(200, json=body))
        with self.assertRaises(YotiProviderError):
            client.get_threshold_result(
                session_id=body["id"], expected_reference_id="a" * 48, threshold=18,
            )
        client.close()

    def test_reference_mismatch_is_rejected(self):
        body = {
            "id": "d1234567-1234-4234-8234-123456789012",
            "sdk_id": "12345678-1234-4234-8234-123456789012",
            "reference_id": "b" * 48,
            "type": "OVER",
            "digital_id": {"allowed": True, "threshold": 18, "age_estimation_allowed": False},
            "method": "DIGITAL_ID",
            "status": "COMPLETE",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        }
        client = self.make_client(lambda request: httpx.Response(200, json=body))
        with self.assertRaises(YotiProviderError):
            client.get_threshold_result(
                session_id=body["id"], expected_reference_id="a" * 48, threshold=18,
            )
        client.close()

    def test_unknown_method_and_age_estimation_fallback_are_rejected(self):
        body = {
            "id": "d1234567-1234-4234-8234-123456789012",
            "sdk_id": "12345678-1234-4234-8234-123456789012",
            "reference_id": "a" * 48,
            "type": "OVER",
            "digital_id": {"allowed": True, "threshold": 18, "age_estimation_allowed": True},
            "method": "AGE_ESTIMATION",
            "status": "COMPLETE",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        }
        client = self.make_client(lambda request: httpx.Response(200, json=body))
        with self.assertRaises(YotiProviderError):
            client.get_threshold_result(
                session_id=body["id"], expected_reference_id="a" * 48, threshold=18,
            )
        client.close()


if __name__ == "__main__":
    unittest.main()

    def test_decision_service_uses_server_selected_eepl_policy_not_request_policy(self):
        import json
        import os
        from types import SimpleNamespace
        from unittest.mock import patch
        from app.main import PolicyIn, _server_policy

        registry = {
            "adult-market": {
                "policy_version": "adult-v4", "minimum_age": 18, "maximum_age": None,
                "allowed_locations": ["KE"], "allowed_occasions": ["everyday"],
                "allowed_climates": ["warm"], "required_context": ["location", "occasion", "climate"],
            },
            "less-restrictive-market": {
                "policy_version": "youth-v1", "minimum_age": 13, "maximum_age": None,
                "allowed_locations": [], "allowed_occasions": [],
                "allowed_climates": [], "required_context": [],
            },
        }
        request_selected = PolicyIn(
            policy_id="less-restrictive-market", policy_version="youth-v1",
            minimum_age=13, required_context=[],
        )
        with patch.dict(os.environ, {
            "EEPL_POLICY_ID": "adult-market",
            "EEPL_POLICY_REGISTRY_JSON": json.dumps(registry),
        }, clear=False):
            resolved = _server_policy(SimpleNamespace(eepl_policy=request_selected))
        self.assertEqual(resolved.policy_id, "adult-market")
        self.assertEqual(resolved.policy_version, "adult-v4")
        self.assertEqual(resolved.minimum_age, 18)
        self.assertEqual(resolved.allowed_locations, ["KE"])


class ServerOwnedEEPLPolicyTests(unittest.TestCase):
    def test_active_policy_is_resolved_from_server_registry(self):
        import json
        import os
        from unittest.mock import patch
        from age_evidence.policy import resolve_active_policy

        registry = {
            "adult-market": {
                "policy_version": "adult-v4", "minimum_age": 18, "maximum_age": None,
                "allowed_locations": ["KE"], "allowed_occasions": ["everyday"],
                "allowed_climates": ["warm"], "required_context": ["location", "occasion", "climate"],
            },
            "youth-market": {
                "policy_version": "youth-v1", "minimum_age": 13, "maximum_age": None,
                "allowed_locations": [], "allowed_occasions": [],
                "allowed_climates": [], "required_context": [],
            },
        }
        with patch.dict(os.environ, {
            "EEPL_POLICY_ID": "adult-market",
            "EEPL_POLICY_REGISTRY_JSON": json.dumps(registry),
        }, clear=False):
            active = resolve_active_policy()
        self.assertEqual(active["policy_id"], "adult-market")
        self.assertEqual(active["minimum_age"], 18)

    def test_duplicate_registry_keys_are_rejected(self):
        import os
        from unittest.mock import patch
        from age_evidence.policy import PolicyRegistryError, resolve_active_policy

        raw = '{"adult":{"policy_version":"v1","minimum_age":18,"maximum_age":null,"allowed_locations":[],"allowed_occasions":[],"allowed_climates":[],"required_context":[]},"adult":{"policy_version":"v2","minimum_age":13,"maximum_age":null,"allowed_locations":[],"allowed_occasions":[],"allowed_climates":[],"required_context":[]}}'
        with patch.dict(os.environ, {"EEPL_POLICY_ID": "adult", "EEPL_POLICY_REGISTRY_JSON": raw}, clear=False):
            with self.assertRaises(PolicyRegistryError):
                resolve_active_policy()

    def test_invalid_context_fields_and_duplicate_allowlist_entries_are_rejected(self):
        import json
        import os
        from unittest.mock import patch
        from age_evidence.policy import PolicyRegistryError, resolve_active_policy

        entry = {
            "policy_version": "v1", "minimum_age": 18, "maximum_age": None,
            "allowed_locations": ["KE", "KE"], "allowed_occasions": [],
            "allowed_climates": [], "required_context": ["location", "untrusted"],
        }
        with patch.dict(os.environ, {
            "EEPL_POLICY_ID": "adult", "EEPL_POLICY_REGISTRY_JSON": json.dumps({"adult": entry}),
        }, clear=False):
            with self.assertRaises(PolicyRegistryError):
                resolve_active_policy()


class DecisionReceiptStoreContractTests(unittest.TestCase):
    def test_receipt_store_fails_closed_when_postgres_is_not_configured(self):
        import os
        from unittest.mock import patch
        from catacaci.receipts import DecisionReceiptStoreError, persist_decision_receipt

        receipt = {
            "request_id": "receipt-test-request", "candidate_id": "candidate-1",
            "verdict": "REVIEW", "may_display": False,
            "eepl_policy_id": "adult-market", "eepl_policy_version": "v2",
            "cal_policy_id": "standard", "cal_policy_version": "cal-v1",
            "minimum_fit_confidence": 0.7, "maximum_fit_confidence_disagreement": 0.1,
            "arbitration_contract_version": "1.1.0", "pipeline_contract_version": "1.0.0",
            "candidate_snapshot_sha256": "a" * 64, "catalog_version": None,
            "evaluated_signals": [{
                "signal_id": "safety:1", "kind": "safety", "state": "unknown",
                "required": True, "confidence": None, "reason_code": "PROVIDER_MISSING",
                "source_version": "unavailable",
            }],
            "reasons": [{"code": "REQUIRED_SIGNAL_UNKNOWN", "signal_id": "safety:1"}],
        }
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(DecisionReceiptStoreError):
                persist_decision_receipt(receipt)

    def test_receipt_store_rejects_inconsistent_show_authorization(self):
        from catacaci.receipts import DecisionReceiptStoreError, persist_decision_receipt

        receipt = {
            "request_id": "receipt-test-request", "candidate_id": "candidate-1",
            "verdict": "REVIEW", "may_display": True,
            "eepl_policy_id": "adult-market", "eepl_policy_version": "v2",
            "cal_policy_id": "standard", "cal_policy_version": "cal-v1",
            "arbitration_contract_version": "1.1.0", "pipeline_contract_version": "1.0.0",
            "candidate_snapshot_sha256": "a" * 64, "catalog_version": None,
            "evaluated_signals": [], "reasons": [],
        }
        with self.assertRaises(DecisionReceiptStoreError):
            persist_decision_receipt(receipt)


class CaTaCaCiGovernanceStoreBoundaryTests(unittest.TestCase):
    def test_cam_rejects_invalid_verdict_before_database_access(self):
        from catacaci.governance_store import GovernanceStoreError, append_cam_audit
        with self.assertRaises(GovernanceStoreError):
            append_cam_audit({
                "audit_id": "cam-audit-0001", "request_id": "request-0001",
                "candidate_id": "candidate-1", "observed_verdict": "allow",
                "simulated_verdict": "show", "changed_signal_ids": [],
                "policy_version": "cal-v1", "replay_version": "replay-v1",
                "evaluated_at": NOW.isoformat(),
                "interpretation": "counterfactual_scenario_not_observed_causality",
            })

    def test_cil_rejects_direct_identifiers_and_unallowlisted_cohorts(self):
        import os
        from unittest.mock import patch
        from catacaci.governance_store import GovernanceStoreError, record_cil_contribution
        with patch.dict(os.environ, {"CATACACI_CIL_ALLOWED_COHORT_KEYS": "market:ke|category:tops"}, clear=False):
            with self.assertRaises(GovernanceStoreError):
                record_cil_contribution(
                    event_id="cil-event-0001", contributor_token="raw-user-id",
                    cohort_key="market:ke|category:tops", outcome_success=True, observed_at=NOW,
                )
        with patch.dict(os.environ, {"CATACACI_CIL_ALLOWED_COHORT_KEYS": ""}, clear=False):
            with self.assertRaises(GovernanceStoreError):
                record_cil_contribution(
                    event_id="cil-event-0002", contributor_token="hmac-sha256:" + "a" * 64,
                    cohort_key="unbounded-user-specific-key", outcome_success=True, observed_at=NOW,
                )

    def test_cil_refuses_low_k_threshold_and_unallowlisted_release(self):
        import os
        from unittest.mock import patch
        from catacaci.governance_store import GovernanceStoreError, release_cil_aggregate
        with patch.dict(os.environ, {"CATACACI_CIL_ALLOWED_COHORT_KEYS": "market:ke|category:tops"}, clear=False):
            with self.assertRaises(GovernanceStoreError):
                release_cil_aggregate(
                    cohort_key="market:ke|category:tops", period_start="2026-11-01",
                    minimum_contributors=10,
                )
        with patch.dict(os.environ, {"CATACACI_CIL_ALLOWED_COHORT_KEYS": ""}, clear=False):
            with self.assertRaises(GovernanceStoreError):
                release_cil_aggregate(
                    cohort_key="unapproved", period_start="2026-11-01",
                )

    def test_vsl_still_requires_distinct_approver_and_invariant_priorities(self):
        from catacaci.vsl import (
            ValueChangeProposal, ValueDimension, ValueProfile, approve_change,
        )
        current = ValueProfile(
            version="v1",
            priority_order=(
                ValueDimension.SAFETY, ValueDimension.LEGAL_ELIGIBILITY,
                ValueDimension.USER_HARD_CONSTRAINT, ValueDimension.NPL_HARD_NEGATIVE,
                ValueDimension.CULTURAL_REQUIREMENT, ValueDimension.CONTEXT_ELIGIBILITY,
                ValueDimension.IDENTITY_ALIGNMENT, ValueDimension.FIT_CONFIDENCE,
                ValueDimension.OTHER,
            ),
        )
        proposal = ValueChangeProposal(
            proposal_id="proposal-0001", base_version="v1", proposed_version="v2",
            proposed_order=current.priority_order, rationale="Keep the approved order stable.",
            proposer_id="operator-a",
        )
        with self.assertRaises(PermissionError):
            approve_change(
                current, proposal, approver_id="operator-a", approval_event_id="approval-0001",
            )
