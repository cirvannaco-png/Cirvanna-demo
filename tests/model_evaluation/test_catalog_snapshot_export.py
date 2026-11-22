import importlib.util
import json
import os
import stat
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "services" / "vision-intelligence" / "app" / "retrieval_snapshot_export.py"
)
SPEC = importlib.util.spec_from_file_location("retrieval_snapshot_export", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CatalogSnapshotExportTests(unittest.TestCase):
    def test_preserves_vision_offer_order_and_exports_only_two_fields(self):
        offers = [
            {"variant_id": "variant-z", "search_text": "exact Vision text Z", "image_urls": ["private-image"]},
            {"variant_id": "variant-a", "search_text": "exact Vision text A", "product": {"name": "Hidden"}},
        ]
        records = MODULE.snapshot_records(offers)
        self.assertEqual([row["variant_id"] for row in records], ["variant-z", "variant-a"])
        self.assertEqual(records[0]["search_text"], "exact Vision text Z")
        self.assertEqual(set(records[0]), {"variant_id", "search_text"})

    def test_rejects_duplicate_or_invalid_variant_ids(self):
        duplicate = [
            {"variant_id": "same", "search_text": "text one"},
            {"variant_id": "same", "search_text": "text two"},
        ]
        with self.assertRaisesRegex(ValueError, "duplicate variant_id"):
            MODULE.snapshot_records(duplicate)
        with self.assertRaisesRegex(ValueError, "invalid variant_id"):
            MODULE.snapshot_records([{"variant_id": " ", "search_text": "text"}])

    def test_rejects_empty_or_overlong_search_text_and_empty_snapshot(self):
        with self.assertRaisesRegex(ValueError, "invalid search_text"):
            MODULE.snapshot_records([{"variant_id": "v1", "search_text": " "}])
        with self.assertRaisesRegex(ValueError, "invalid search_text"):
            MODULE.snapshot_records([{"variant_id": "v1", "search_text": "x" * 2001}])
        with self.assertRaisesRegex(ValueError, "no eligible"):
            MODULE.snapshot_records([])

    def test_enforces_the_existing_one_thousand_offer_ceiling(self):
        offers = [{"variant_id": f"v{i}", "search_text": f"product {i}"} for i in range(1001)]
        with self.assertRaisesRegex(ValueError, "candidate bound"):
            MODULE.snapshot_records(offers)

    def test_writes_private_snapshot_and_manifest_with_matching_digest(self):
        records = MODULE.snapshot_records([
            {"variant_id": "v1", "search_text": "Vision exact offer text"},
        ])
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "catalog.jsonl"
            manifest = {"schema_version": "1.0", "truncated": False}
            written, sidecar, digest = MODULE.write_snapshot(output, records, manifest)
            self.assertEqual(written.read_bytes(), MODULE.jsonl_bytes(records))
            self.assertEqual(digest, MODULE.sha256_bytes(written.read_bytes()))
            self.assertEqual(json.loads(sidecar.read_text())["snapshot_file_sha256"], digest)
            self.assertEqual(stat.S_IMODE(written.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(sidecar.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                MODULE.write_snapshot(output, records, manifest)

    def test_snapshot_pair_is_immutable_and_overwrite_is_rejected(self):
        records = MODULE.snapshot_records([
            {"variant_id": "v1", "search_text": "Vision exact offer text"},
        ])
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "catalog.jsonl"
            _, sidecar, digest = MODULE.write_snapshot(output, records, {"schema_version": "1.0"})
            original_snapshot = output.read_bytes()
            original_manifest = sidecar.read_bytes()
            with self.assertRaisesRegex(ValueError, "immutable"):
                MODULE.write_snapshot(output, records, {"schema_version": "1.0"}, overwrite=True)
            self.assertEqual(output.read_bytes(), original_snapshot)
            self.assertEqual(sidecar.read_bytes(), original_manifest)
            self.assertEqual(MODULE.sha256_bytes(output.read_bytes()), digest)

    @unittest.skipUnless(os.name == "posix", "POSIX permission semantics required")
    def test_refuses_group_or_world_accessible_existing_directory(self):
        records = MODULE.snapshot_records([
            {"variant_id": "v1", "search_text": "Vision exact offer text"},
        ])
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp) / "shared"
            output_dir.mkdir(mode=0o755)
            output_dir.chmod(0o755)
            with self.assertRaisesRegex(PermissionError, "accessible by group or other"):
                MODULE.write_snapshot(output_dir / "catalog.jsonl", records, {"schema_version": "1.0"})

    def test_loads_only_a_valid_rights_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            evidence = root / "approval.txt"
            evidence.write_text("approved evidence", encoding="utf-8")
            manifest = root / "rights.json"
            value = {
                "schema_version": "1.0", "approval_status": "approved",
                "scope": "fashion_retrieval_evaluation", "reviewed_by": "reviewer",
                "reviewer_role": "data-rights-owner", "reviewed_at_utc": "2026-11-22T00:00:00Z",
                "source_provenance": "approved controlled query sources",
                "evidence_path": str(evidence),
                "evidence_sha256": MODULE.sha256_bytes(evidence.read_bytes()),
                "commercial_evaluation_permitted": True, "human_review_permitted": True,
                "retention_until": "2027-12-31", "contains_personal_images": False,
                "depicted_person_consent_status": "not_applicable",
            }
            manifest.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(MODULE.load_rights_manifest(manifest)["approval_status"], "approved")
            value["approval_status"] = "pending"
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be 'approved'"):
                MODULE.load_rights_manifest(manifest)

    def test_exporter_cli_does_not_offer_overwrite_for_immutable_snapshots(self):
        with patch("sys.argv", ["retrieval_snapshot_export.py", "--help"]):
            with self.assertRaises(SystemExit) as raised:
                MODULE.main()
            self.assertEqual(raised.exception.code, 0)

    def test_exporter_checks_rights_before_starting_live_service_read(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("sys.argv", ["retrieval_snapshot_export.py", "--output", str(Path(temp) / "snapshot.jsonl"),
                                    "--rights-manifest", str(Path(temp) / "missing-rights.json")]), \
                 patch.object(MODULE.asyncio, "run", side_effect=AssertionError("service access must not start")):
                self.assertEqual(MODULE.main(), 2)

    def test_snapshot_manifest_carries_rights_digest_without_reviewer_or_evidence_paths(self):
        rights = {
            "approval_status": "approved", "scope": "fashion_retrieval_evaluation",
            "manifest_sha256": "a" * 64, "evidence_sha256": "b" * 64,
            "retention_until": "2027-12-31", "reviewed_by": "private-reviewer",
            "evidence_path": "/restricted/private-approval.pdf",
        }
        summary = MODULE.rights_manifest_summary(rights)
        self.assertEqual(summary["manifest_sha256"], "a" * 64)
        self.assertEqual(summary["evidence_sha256"], "b" * 64)
        self.assertNotIn("reviewed_by", summary)
        self.assertNotIn("evidence_path", summary)

    def test_manifest_records_truncation_and_privacy_boundaries(self):
        records = MODULE.snapshot_records([
            {"variant_id": "v1", "search_text": "safe text"},
        ])
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "catalog.jsonl"
            _, sidecar, _ = MODULE.write_snapshot(
                output, records,
                {"commerce_offer_list_was_truncated_at_service_limit": True},
            )
            manifest = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertTrue(manifest["commerce_offer_list_was_truncated_at_service_limit"])
            self.assertFalse(manifest["product_image_urls_exported"])
            self.assertFalse(manifest["raw_offer_payloads_exported"])
            self.assertTrue(manifest["commerce_offer_order_preserved"])


if __name__ == "__main__":
    unittest.main()
