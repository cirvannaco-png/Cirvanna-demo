from __future__ import annotations

import csv
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "integration-staging"


class SourceManifestCompletenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((STAGING / "source-manifest.json").read_text(encoding="utf-8"))

    def test_expected_candidate_count_and_unique_paths(self):
        files = self.manifest["files"]
        paths = [entry["staged_path"] for entry in files]
        self.assertEqual(len(files), 544)
        self.assertEqual(len(paths), len(set(paths)), "source manifest contains duplicate staged_path values")

    def test_every_manifest_candidate_is_present(self):
        missing = [
            entry["staged_path"] for entry in self.manifest["files"]
            if not (STAGING / entry["staged_path"]).is_file()
        ]
        self.assertEqual(missing, [], f"missing staged candidates: {missing}")

    def test_original_extracted_snapshots_match_recorded_sha256(self):
        audit_path = STAGING / "source-intake" / "manifests" / "source-audit.csv"
        with audit_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 31)
        for record in rows:
            path = STAGING / "source-intake" / "extracted" / record["extracted_filename"]
            self.assertTrue(path.is_file(), f"source snapshot missing: {path.name}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, record["sha256"], f"original source snapshot changed: {path.name}")


if __name__ == "__main__":
    unittest.main()
