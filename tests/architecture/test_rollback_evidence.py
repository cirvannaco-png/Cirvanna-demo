from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_rollback_evidence import validate_rollback_evidence


class RollbackEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.template = json.loads(
            (ROOT / "docs" / "operations" / "rollback-evidence-template.json").read_text(encoding="utf-8")
        )

    def passed_record(self):
        record = copy.deepcopy(self.template)
        record["status"] = "passed"
        record["environment"]["id"] = "staging-rollback-drill-01"
        record["environment"]["region"] = "approved-test-region"
        record["deployment_scope"] = {
            "service_inventory_reference": "evidence://rollback/service-inventory",
            "expected_service_ids": ["api-gateway", "commerce-service"],
        }
        record["candidate_release"] = {
            "commit_sha": "a" * 40,
            "deployment_id": "deploy-candidate-01",
            "image_digests": {"api-gateway": "sha256:" + "1" * 64, "commerce-service": "sha256:" + "3" * 64},
        }
        record["rollback_target"] = {
            "commit_sha": "b" * 40,
            "deployment_id": "deploy-known-good-01",
            "image_digests": {"api-gateway": "sha256:" + "2" * 64, "commerce-service": "sha256:" + "4" * 64},
        }
        record["database_recovery"].update({
            "candidate_migration_revision": "20261119_0001",
            "rollback_target_compatibility": "backward_compatible",
            "strategy": "backward_compatible_application_rollback",
            "pre_release_backup_reference": "evidence://rollback/pre-release-backup",
            "schema_validation_reference": "evidence://rollback/schema-compatibility",
            "external_event_reconciliation_reference": "evidence://rollback/external-events",
            "measured_data_loss_seconds": 0,
            "approved_rpo_seconds": 300,
        })
        record["exercise"].update({
            "started_at": "2026-11-19T09:00:00Z",
            "completed_at": "2026-11-19T09:03:00Z",
            "trigger": "controlled staging rollback drill",
            "operator": "release-operator",
            "independent_approver": "release-approver",
            "measured_rollback_seconds": 180,
            "approved_rto_seconds": 300,
            "data_loss_observed": False,
            "reconciliation_gap_count": 0,
            "traffic_switch_reference": "evidence://rollback/traffic-switch",
            "pre_rollback_health_reference": "evidence://rollback/pre-health",
            "post_rollback_health_reference": "evidence://rollback/post-health",
            "database_compatibility_or_restore_reference": "evidence://rollback/database",
            "payment_and_order_reconciliation_reference": "evidence://rollback/payments",
            "consent_and_privacy_reconciliation_reference": "evidence://rollback/privacy",
            "monitoring_alert_reference": "evidence://rollback/alerts",
        })
        record["exercise"]["post_rollback_checks"] = {
            name: "passed" for name in record["exercise"]["post_rollback_checks"]
        }
        return record

    def test_unexecuted_template_is_valid_but_not_passed(self):
        self.assertEqual(validate_rollback_evidence(self.template), [])
        self.assertEqual(self.template["status"], "not_executed")

    def test_complete_evidence_record_passes(self):
        self.assertEqual(validate_rollback_evidence(self.passed_record()), [])

    def test_passed_record_requires_immutable_image_digests(self):
        record = self.passed_record()
        record["candidate_release"]["image_digests"]["api-gateway"] = "latest"
        self.assertTrue(any("immutable sha256 digests" in error
                            for error in validate_rollback_evidence(record)))

    def test_database_rollback_requires_proven_schema_compatibility(self):
        record = self.passed_record()
        record["database_recovery"]["rollback_target_compatibility"] = "incompatible"
        errors = validate_rollback_evidence(record)
        self.assertTrue(any("requires proven schema compatibility" in error for error in errors))

    def test_data_loss_must_fit_approved_rpo(self):
        record = self.passed_record()
        record["database_recovery"]["measured_data_loss_seconds"] = 301
        errors = validate_rollback_evidence(record)
        self.assertTrue(any("exceeds approved RPO" in error for error in errors))

    def test_candidate_and_rollback_must_cover_same_service_set(self):
        record = self.passed_record()
        record["rollback_target"]["image_digests"].pop("commerce-service")
        self.assertTrue(any("same service set" in error for error in validate_rollback_evidence(record)))

    def test_image_digest_maps_must_cover_every_expected_service(self):
        record = self.passed_record()
        record["candidate_release"]["image_digests"].pop("commerce-service")
        self.assertTrue(any("every expected deployment service" in error
                            for error in validate_rollback_evidence(record)))

    def test_operator_cannot_be_the_only_approver(self):
        record = self.passed_record()
        record["exercise"]["independent_approver"] = record["exercise"]["operator"]
        self.assertTrue(any("must be different" in error
                            for error in validate_rollback_evidence(record)))

    def test_rto_breach_blocks_pass(self):
        record = self.passed_record()
        record["exercise"]["measured_rollback_seconds"] = 301
        self.assertTrue(any("exceeds approved RTO" in error
                            for error in validate_rollback_evidence(record)))

    def test_data_loss_or_reconciliation_gap_blocks_pass(self):
        record = self.passed_record()
        record["exercise"]["data_loss_observed"] = True
        record["exercise"]["reconciliation_gap_count"] = 1
        errors = validate_rollback_evidence(record)
        self.assertTrue(any("data_loss_observed=false" in error for error in errors))
        self.assertTrue(any("reconciliation_gap_count=0" in error for error in errors))

    def test_every_critical_path_check_is_required(self):
        record = self.passed_record()
        record["exercise"]["post_rollback_checks"]["discovery_usi_npl_eepl_fci_cal"] = "not_run"
        self.assertTrue(any("discovery_usi_npl_eepl_fci_cal" in error
                            for error in validate_rollback_evidence(record)))

    def test_commit_shas_must_identify_distinct_releases(self):
        record = self.passed_record()
        record["rollback_target"]["commit_sha"] = record["candidate_release"]["commit_sha"]
        self.assertTrue(any("different release commit" in error
                            for error in validate_rollback_evidence(record)))


if __name__ == "__main__":
    unittest.main()
