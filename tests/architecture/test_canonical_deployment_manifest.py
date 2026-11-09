from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_canonical_stack import validate_manifest  # noqa: E402


class CanonicalDeploymentManifestTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(
            (ROOT / "infrastructure" / "deployment" / "canonical-stack.json").read_text(encoding="utf-8")
        )

    def test_repository_inventory_is_structurally_valid_but_not_operational(self):
        self.assertEqual(validate_manifest(self.document), [])
        self.assertFalse(self.document["deployment"]["operationally_complete"])
        self.assertEqual(self.document["release_status"], "blocked")

    def test_unknown_service_dependency_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["services"][0]["depends_on_services"].append("ghost-service")
        self.assertTrue(any("unknown service dependency" in item for item in validate_manifest(document)))

    def test_public_ingress_cannot_be_duplicated(self):
        document = copy.deepcopy(self.document)
        document["services"][1]["exposure"] = "public_edge"
        self.assertTrue(any("sole public browser ingress" in item for item in validate_manifest(document)))

    def test_production_readiness_cannot_be_claimed_without_evidence(self):
        document = copy.deepcopy(self.document)
        document["deployment"]["operationally_complete"] = True
        self.assertTrue(any("must remain false" in item for item in validate_manifest(document)))

    def test_missing_container_build_context_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["services"][0]["build_context"] = "does-not-exist"
        self.assertTrue(any("build_context must exist" in item for item in validate_manifest(document)))


if __name__ == "__main__":
    unittest.main()
