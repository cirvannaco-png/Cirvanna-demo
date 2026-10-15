from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.scan_source_secrets import scan_file


class SecretScannerRegressionTests(unittest.TestCase):
    def scan_text(self, text: str) -> list[tuple[int, str]]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.txt"
            path.write_text(text, encoding="utf-8")
            return scan_file(path)

    def test_detects_credentialed_database_uri(self) -> None:
        findings = self.scan_text(
            'DATABASE_URL = "postgresql://app:nonPlaceholderSecret@db.internal/app"\n'
        )
        self.assertIn((1, "database-uri-credentials"), findings)

    def test_ignores_redacted_database_uri(self) -> None:
        findings = self.scan_text(
            'DATABASE_URL = "postgresql://app:REDACTED@db.internal/app"\n'
        )
        self.assertNotIn((1, "database-uri-credentials"), findings)

    def test_detects_short_quoted_password_assignment(self) -> None:
        findings = self.scan_text('password = "abc123"\n')
        self.assertIn((1, "hardcoded-password-assignment"), findings)

    def test_ignores_redacted_password_assignment(self) -> None:
        findings = self.scan_text('password = "REDACTED"\n')
        self.assertNotIn((1, "hardcoded-password-assignment"), findings)


if __name__ == "__main__":
    unittest.main()
