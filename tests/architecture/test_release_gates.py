from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_release_gates import validate_release_gates


class ReleaseGateValidationTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(
            (ROOT / "docs" / "release" / "release-gates.json").read_text(encoding="utf-8")
        )

    def test_repository_registry_is_structurally_valid(self):
        self.assertEqual(validate_release_gates(self.document), [])

    def test_passed_gate_requires_evidence_and_exact_commit(self):
        document = copy.deepcopy(self.document)
        document["gates"][0]["status"] = "passed"
        errors = validate_release_gates(document)
        self.assertTrue(any("evidence_refs" in error for error in errors))
        self.assertTrue(any("verified_commit" in error for error in errors))

    def test_passed_gate_accepts_evidence_and_full_sha(self):
        document = copy.deepcopy(self.document)
        document["gates"][0].update({
            "status": "passed",
            "evidence_refs": ["https://github.com/example/actions/runs/123"],
            "verified_commit": "a" * 40,
        })
        self.assertEqual(validate_release_gates(document), [])

    def test_ready_release_with_open_required_gate_is_invalid(self):
        document = copy.deepcopy(self.document)
        document["release_status"] = "ready"
        self.assertTrue(any("cannot be ready" in error for error in validate_release_gates(document)))

    def test_duplicate_gate_ids_are_rejected(self):
        document = copy.deepcopy(self.document)
        document["gates"][1]["id"] = document["gates"][0]["id"]
        self.assertTrue(any("must be unique" in error for error in validate_release_gates(document)))


if __name__ == "__main__":
    unittest.main()
