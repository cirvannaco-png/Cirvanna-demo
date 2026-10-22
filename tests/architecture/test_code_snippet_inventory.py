from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.build_code_snippet_inventory import build_inventory, render_inventory  # noqa: E402


class CodeSnippetInventoryTests(unittest.TestCase):
    def test_every_manifest_snippet_is_present_and_non_runtime(self):
        inventory = build_inventory(ROOT)
        self.assertEqual(inventory["summary"]["source_sections"], 31)
        self.assertEqual(inventory["summary"]["extracted_snippets"], 544)
        self.assertEqual(inventory["summary"]["present_in_main"], 544)
        self.assertEqual(inventory["summary"]["missing"], 0)
        self.assertEqual(inventory["summary"]["runtime_promoted_from_archive"], 0)
        self.assertTrue(all(item["status"] == "preserved_candidate_not_runtime" for item in inventory["snippets"]))

    def test_duplicate_groups_are_consistent(self):
        inventory = build_inventory(ROOT)
        groups = {group["git_blob_sha1"] for group in inventory["duplicate_groups"]}
        for snippet in inventory["snippets"]:
            if snippet["duplicate_group"] is not None:
                self.assertIn(snippet["duplicate_group"], groups)

    def test_committed_inventory_is_reproducible(self):
        expected = render_inventory(build_inventory(ROOT))
        actual = (ROOT / "docs" / "migration" / "code-snippet-inventory.json").read_text(encoding="utf-8")
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
