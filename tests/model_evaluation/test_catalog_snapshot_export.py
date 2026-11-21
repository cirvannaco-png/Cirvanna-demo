import importlib.util
import json
import os
import stat
import tempfile
import unittest
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
