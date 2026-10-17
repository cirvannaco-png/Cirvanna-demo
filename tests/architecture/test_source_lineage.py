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

    def test_path_normalisation_supports_headers(self):
        self.assertEqual(_normalise_path("# File: src/example.py"), "src/example.py")
        self.assertEqual(_normalise_path("-- schema.sql"), "schema.sql")
        self.assertEqual(_normalise_path("src\\\\example.py"), "src/example.py")

    def test_sha256_is_stable(self):
        self.assertEqual(sha256(b"test"), "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08")

if __name__ == "__main__":
    unittest.main()
