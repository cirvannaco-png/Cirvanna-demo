import hashlib
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from tools.model_evaluation.fashion_retrieval.data_rights import (
    load_and_validate_data_rights_manifest,
    validate_data_rights_manifest,
)


class DataRightsGateTests(unittest.TestCase):
    def _fixture(self, root):
        evidence = root / "approval.txt"
        evidence.write_text("signed approval evidence", encoding="utf-8")
        manifest = root / "rights.json"
        value = {
            "schema_version": "1.0", "approval_status": "approved",
            "scope": "fashion_retrieval_evaluation", "reviewed_by": "reviewer-1",
            "reviewer_role": "data-rights-owner", "reviewed_at_utc": "2026-11-21T12:00:00Z",
            "source_provenance": "source register record SRC-001",
            "evidence_path": str(evidence),
            "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            "commercial_evaluation_permitted": True, "human_review_permitted": True,
            "retention_until": (date.today() + timedelta(days=30)).isoformat(),
            "contains_personal_images": False, "depicted_person_consent_status": "not_applicable",
        }
        manifest.write_text(json.dumps(value), encoding="utf-8")
        return manifest, value

    def test_accepts_complete_approved_manifest_and_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            path, _ = self._fixture(Path(temp))
            self.assertEqual(load_and_validate_data_rights_manifest(path)["approval_status"], "approved")

    def test_fails_closed_for_missing_manifest_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            path, value = self._fixture(Path(temp))
            value.pop("commercial_evaluation_permitted")
            with self.assertRaisesRegex(ValueError, "missing required fields"):
                validate_data_rights_manifest(value, path)

    def test_rejects_unapproved_or_wrong_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            path, value = self._fixture(Path(temp))
            value["approval_status"] = "pending"
            with self.assertRaisesRegex(ValueError, "must be 'approved'"):
                validate_data_rights_manifest(value, path)
            value["approval_status"] = "approved"
            value["scope"] = "internal_only"
            with self.assertRaisesRegex(ValueError, "scope must be"):
                validate_data_rights_manifest(value, path)

    def test_accepts_capability_specific_rights_scope_only_when_requested(self):
        with tempfile.TemporaryDirectory() as temp:
            path, value = self._fixture(Path(temp))
            value["scope"] = "look_it_decomposition_evaluation"
            with self.assertRaisesRegex(ValueError, "scope must be fashion_retrieval_evaluation"):
                validate_data_rights_manifest(value, path)
            accepted = validate_data_rights_manifest(
                value, path, expected_scope="look_it_decomposition_evaluation"
            )
            self.assertEqual(accepted["scope"], "look_it_decomposition_evaluation")

    def test_rejects_missing_or_tampered_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            path, value = self._fixture(Path(temp))
            value["evidence_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                validate_data_rights_manifest(value, path)
            value["evidence_path"] = str(Path(temp) / "missing.txt")
            with self.assertRaisesRegex(ValueError, "evidence file is missing"):
                validate_data_rights_manifest(value, path)

    def test_rejects_expired_retention_and_unapproved_personal_image_consent(self):
        with tempfile.TemporaryDirectory() as temp:
            path, value = self._fixture(Path(temp))
            value["retention_until"] = "2000-01-01"
            with self.assertRaisesRegex(ValueError, "retention approval has expired"):
                validate_data_rights_manifest(value, path)
            value["retention_until"] = (date.today() + timedelta(days=10)).isoformat()
            value["contains_personal_images"] = True
            value["depicted_person_consent_status"] = "not_applicable"
            with self.assertRaisesRegex(ValueError, "verified depicted-person consent"):
                validate_data_rights_manifest(value, path)

    def test_rejects_missing_commercial_or_human_review_permission(self):
        with tempfile.TemporaryDirectory() as temp:
            path, value = self._fixture(Path(temp))
            value["commercial_evaluation_permitted"] = False
            with self.assertRaisesRegex(ValueError, "commercial evaluation permission"):
                validate_data_rights_manifest(value, path)
            value["commercial_evaluation_permitted"] = True
            value["human_review_permitted"] = False
            with self.assertRaisesRegex(ValueError, "human review permission"):
                validate_data_rights_manifest(value, path)


if __name__ == "__main__":
    unittest.main()
