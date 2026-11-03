from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_source_boundaries import (
    is_quarantined_reference,
    scan_source_boundaries,
)


class SourceBoundaryTests(unittest.TestCase):
    def test_recognises_archived_and_candidate_import_segments(self):
        for target in (
            "../integration-staging/source-candidates/item.py",
            "integration_staging.source_candidates.item",
            "@/repo/packages/domain/candidates/v2",
            "./experimental/model",
            "source-intake.extracted.module",
        ):
            with self.subTest(target=target):
                self.assertTrue(is_quarantined_reference(target))

    def test_allows_normal_runtime_imports(self):
        for target in (
            "fastapi",
            "packages.identity_intelligence.catacaci",
            "../shared/contracts",
            "@cirvanna/shared-contracts",
            "./domain",
        ):
            with self.subTest(target=target):
                self.assertFalse(is_quarantined_reference(target))

    def test_detects_python_archive_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "services" / "gateway"
            source.mkdir(parents=True)
            (source / "handler.py").write_text(
                "from integration_staging.source_candidates.cfrp import Candidate\n",
                encoding="utf-8",
            )
            errors = scan_source_boundaries(root, ["services/gateway"])
            self.assertEqual(len(errors), 1)
            self.assertIn("handler.py:1", errors[0])

    def test_detects_relative_python_import_of_candidate_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "services" / "gateway"
            source.mkdir(parents=True)
            (source / "handler.py").write_text(
                "from . import candidates\\n", encoding="utf-8"
            )
            errors = scan_source_boundaries(root, ["services/gateway"])
            self.assertEqual(len(errors), 1)
            self.assertIn("candidates", errors[0])

    def test_detects_typescript_candidate_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "apps" / "web"
            source.mkdir(parents=True)
            (source / "screen.tsx").write_text(
                'import { model } from "../../packages/domain/candidates/model";\n',
                encoding="utf-8",
            )
            errors = scan_source_boundaries(root, ["apps/web"])
            self.assertEqual(len(errors), 1)
            self.assertIn("screen.tsx:1", errors[0])

    def test_missing_registered_root_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            errors = scan_source_boundaries(Path(directory), ["services/missing"])
            self.assertEqual(len(errors), 1)
            self.assertIn("registered canonical source root is missing", errors[0])

    def test_syntax_error_does_not_pass_as_verified_python(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "services" / "gateway"
            source.mkdir(parents=True)
            (source / "broken.py").write_text("def broken(:\n", encoding="utf-8")
            errors = scan_source_boundaries(root, ["services/gateway"])
            self.assertEqual(len(errors), 1)
            self.assertIn("unparseable Python source", errors[0])


if __name__ == "__main__":
    unittest.main()
