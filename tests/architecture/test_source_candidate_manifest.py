from __future__ import annotations

import csv
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "integration-staging"
CURRENT_ARCHIVE = STAGING / "source-intake" / "original" / "cirvanna-source.txt"
EXPECTED_CURRENT_ARCHIVE_BLOB_SHA = "eef9faf82e6bc18d338181d8739efda06c5d0874"
EXPECTED_INITIAL_INTAKE_BYTES = 1780970


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


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

    def test_all_31_extracted_snapshots_are_present(self):
        audit_path = STAGING / "source-intake" / "manifests" / "source-audit.csv"
        with audit_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 31)
        for record in rows:
            path = STAGING / "source-intake" / "extracted" / record["extracted_filename"]
            self.assertTrue(path.is_file(), f"source snapshot missing: {path.name}")

    def test_current_redacted_archive_is_pinned_and_size_metadata_is_consistent(self):
        data = CURRENT_ARCHIVE.read_bytes()
        self.assertTrue(self.manifest["source_archive_redacted"])
        self.assertEqual(git_blob_sha1(data), EXPECTED_CURRENT_ARCHIVE_BLOB_SHA)
        self.assertEqual(len(data), self.manifest["source_bytes"])
        self.assertEqual(self.manifest["source_bytes_at_initial_intake"], EXPECTED_INITIAL_INTAKE_BYTES)


if __name__ == "__main__":
    unittest.main()
