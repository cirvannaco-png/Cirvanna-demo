import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.validate_architecture import validate_inventory  # noqa: E402


class ModuleInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(
            (ROOT / "docs" / "migration" / "module-inventory.json").read_text(encoding="utf-8")
        )

    def test_inventory_is_consistent(self):
        self.assertEqual(validate_inventory(self.manifest, ROOT), [])

    def test_all_31_source_snapshots_are_tracked(self):
        self.assertEqual(self.manifest["intakeArtifact"]["sourceSnapshotCount"], 31)
        self.assertEqual(len(self.manifest["sourceSnapshots"]), 31)

    def test_runtime_source_is_not_claimed_as_promoted(self):
        self.assertFalse(self.manifest["intakeArtifact"]["runtimeSourcePromoted"])

    def test_crfp_has_distinct_marketplace_and_system_wide_scopes(self):
        modules = {item["id"]: item for item in self.manifest["modules"]}
        self.assertIn("crfp-marketplace", modules)
        self.assertIn("crfp-system", modules)
        self.assertEqual(
            modules["crfp-marketplace"]["target"],
            "packages/fit-intelligence/crfp/marketplace",
        )
        self.assertEqual(
            modules["crfp-system"]["target"],
            "packages/fit-intelligence/crfp/system",
        )
        self.assertNotIn("cfrp", modules)

    def test_crfp_scopes_are_documentation_only_not_runtime_promotions(self):
        registry = json.loads(
            (ROOT / "docs" / "architecture" / "runtime-source-registry.json").read_text(encoding="utf-8")
        )
        root = next(item for item in registry["canonical_roots"] if item["path"] == "packages/fit-intelligence/crfp")
        self.assertEqual(root["status"], "scope-documentation-only")
        legacy = next(item for item in registry["quarantined_roots"] if item["path"] == "packages/fit-intelligence/cfrp")
        self.assertEqual(legacy["status"], "historical-typo-marker")
        self.assertFalse(self.manifest["intakeArtifact"]["runtimeSourcePromoted"])
        self.assertTrue((ROOT / "packages/fit-intelligence/crfp/marketplace/README.md").is_file())
        self.assertTrue((ROOT / "packages/fit-intelligence/crfp/system/README.md").is_file())


if __name__ == "__main__":
    unittest.main()
