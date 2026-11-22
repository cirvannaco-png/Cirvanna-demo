from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_source_lineage import _extract_archive_sections, _named_code_blocks, _normalise_path, git_blob_sha1, sha256

class SourceLineageUtilityTests(unittest.TestCase):
    def test_git_blob_hash_includes_object_header(self):
        self.assertEqual(git_blob_sha1(b"test"), "30d74d258442c7c65512eafab474568dd706c430")

    def test_archive_sections_preserve_order_and_bytes(self):
        archive = b"===== FILE: ./one.txt =====\nfirst\n===== FILE: ./two.txt =====\nsecond\n"
        self.assertEqual(_extract_archive_sections(archive), [("./one.txt", b"first\n"), ("./two.txt", b"second\n")])

    def test_code_block_extraction_preserves_body(self):
        tick = chr(96)
        snapshot = tick * 3 + "python\nsrc/example.py\ndef answer():\n    return 42\n" + tick * 3 + "\n"
        blocks = _named_code_blocks(snapshot)
        self.assertEqual(blocks["src/example.py"], ["def answer():\n    return 42\n"])

    def test_embedded_file_headers_split_multi_file_fence(self):
        tick = chr(96)
        snapshot = (
            tick * 3 + "python\n"
            "# File: src/first.py\n"
            "def first():\n    return 1\n\n"
            "# ======================================================================\n"
            "# File: src/second.py\n"
            "def second():\n    return 2\n"
            + tick * 3 + "\n"
        )
        blocks = _named_code_blocks(snapshot)
        self.assertEqual(blocks["src/first.py"], ["def first():\n    return 1\n"])
        self.assertEqual(blocks["src/second.py"], ["def second():\n    return 2\n"])

    def test_filename_preceding_fence_is_associated_with_code(self):
        tick = chr(96)
        snapshot = (
            "src/example.py\n\n"
            + tick * 3 + "python\n"
            "def answer():\n    return 42\n"
            + tick * 3 + "\n"
        )
        blocks = _named_code_blocks(snapshot)
        self.assertEqual(blocks["src/example.py"], ["def answer():\n    return 42\n"])

    def test_unclosed_final_fence_is_still_a_source_block(self):
        tick = chr(96)
        snapshot = (
            "src/final.py\n"
            + tick * 3 + "python\n"
            "def final():\n    return True\n"
        )
        blocks = _named_code_blocks(snapshot)
        self.assertEqual(blocks["src/final.py"], ["def final():\n    return True\n"])

    def test_standalone_filename_fence_precedes_code_fence(self):
        tick = chr(96)
        snapshot = (
            tick * 3 + "\n"
            "src/types/index.ts\n"
            + tick * 3 + "\n\n"
            + tick * 3 + "typescript\n"
            "export type DecisionIntent = string;\n"
            + tick * 3 + "\n"
        )
        blocks = _named_code_blocks(snapshot)
        self.assertEqual(
            blocks["src/types/index.ts"],
            ["export type DecisionIntent = string;\n"],
        )

    def test_markdown_source_keeps_nested_language_fences(self):
        tick = chr(96)
        snapshot = (
            tick * 3 + "markdown\n"
            "README.md\n"
            "# Guide\n"
            + tick * 3 + "bash\n"
            "echo hi\n"
            + tick * 3 + "\n"
            "Text after nested example\n"
            + tick * 3 + "\n"
        )
        blocks = _named_code_blocks(snapshot)
        self.assertEqual(
            blocks["README.md"],
            ["# Guide\n" + tick * 3 + "bash\necho hi\n" + tick * 3 + "\nText after nested example\n"],
        )

    def test_path_normalisation_supports_headers(self):
        self.assertEqual(_normalise_path("# File: src/example.py"), "src/example.py")
        self.assertEqual(_normalise_path("-- schema.sql"), "schema.sql")
        self.assertEqual(_normalise_path("src\\\\example.py"), "src/example.py")

    def test_sha256_is_stable(self):
        self.assertEqual(sha256(b"test"), "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08")

if __name__ == "__main__":
    unittest.main()
