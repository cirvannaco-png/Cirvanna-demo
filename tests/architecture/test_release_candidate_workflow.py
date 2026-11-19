from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "release-candidate-readiness.yml"


class ReleaseCandidateWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.content = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_is_manual_and_read_only(self):
        self.assertIn("workflow_dispatch:", self.content)
        self.assertIn("contents: read", self.content)
        self.assertNotIn("deploy", self.content.lower())

    def test_candidate_commit_is_pinned_and_validated(self):
        self.assertIn("ref: ${{ inputs.candidate_sha }}", self.content)
        self.assertIn("^[0-9a-f]{40}$", self.content)
        self.assertIn('test "$actual_sha" = "$CANDIDATE_SHA"', self.content)

    def test_strict_source_lineage_and_release_gates_are_required(self):
        self.assertIn("python scripts/audit_source_lineage.py", self.content)
        self.assertNotIn("--allow-unreconciled", self.content)
        self.assertIn("python scripts/validate_release_gates.py --require-all-passed", self.content)

    def test_real_rollback_evidence_is_required(self):
        self.assertIn("python scripts/validate_rollback_evidence.py --require-passed", self.content)


if __name__ == "__main__":
    unittest.main()
