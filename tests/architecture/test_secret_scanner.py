from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.scan_source_secrets import is_historical_local_default_uri_fixture, scan_file


class SecretScannerRegressionTests(unittest.TestCase):
    def scan_text(self, text: str) -> list[tuple[int, str]]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.txt"
            path.write_text(text, encoding="utf-8")
            return scan_file(path)

    def test_detects_credentialed_database_uri(self) -> None:
        uri = "postgresql://app:" + "nonPlaceholderSecret" + "@db.internal/app"
        findings = self.scan_text(f'DATABASE_URL = "{uri}"\n')
        self.assertIn((1, "database-uri-credentials"), findings)

    def test_detects_driver_qualified_database_uri_credentials(self) -> None:
        for scheme in ("postgresql+asyncpg", "postgresql+psycopg", "mysql+pymysql"):
            with self.subTest(scheme=scheme):
                uri = f"{scheme}://app:" + "nonPlaceholderSecret" + "@db.internal/app"
                findings = self.scan_text(f'DATABASE_URL = "{uri}"\n')
                self.assertIn((1, "database-uri-credentials"), findings)

    def test_ignores_redacted_database_uri(self) -> None:
        findings = self.scan_text(
            'DATABASE_URL = "postgresql://app:REDACTED@db.internal/app"\n'
        )
        self.assertNotIn((1, "database-uri-credentials"), findings)

    def test_detects_credentialed_broker_uris(self) -> None:
        for scheme in ("amqp", "amqps", "nats", "nats+tls", "mqtt", "mqtts", "kafka"):
            with self.subTest(scheme=scheme):
                uri = f"{scheme}://worker:" + "nonPlaceholderSecret" + "@broker.internal/vhost"
                findings = self.scan_text(f'BROKER_URL = "{uri}"\n')
                self.assertIn((1, "database-uri-credentials"), findings)

    def test_detects_tls_redis_uri_credentials(self) -> None:
        uri = "rediss://cache:" + "nonPlaceholderSecret" + "@cache.internal/0"
        findings = self.scan_text(f'CACHE_URL = "{uri}"\n')
        self.assertIn((1, "database-uri-credentials"), findings)

    def test_ignores_redacted_broker_uri(self) -> None:
        findings = self.scan_text('BROKER_URL = "amqps://worker:REDACTED@broker.internal/vhost"\n')
        self.assertNotIn((1, "database-uri-credentials"), findings)

    def test_default_broker_credentials_are_not_ignored_outside_historical_fixture(self) -> None:
        uri = "amqp://guest:" + "guest" + "@broker.internal/vhost"
        findings = self.scan_text(f'BROKER_URL = "{uri}"\\n')
        self.assertIn((1, "database-uri-credentials"), findings)

    def test_historical_default_exception_is_exactly_scoped(self) -> None:
        path = "integration-staging/source-intake/original/cirvanna-source.txt"
        self.assertTrue(is_historical_local_default_uri_fixture(
            path, 50498, "amqp", "guest", "guest", "rabbitmq:5672"
        ))
        self.assertFalse(is_historical_local_default_uri_fixture(
            path, 50499, "amqp", "guest", "guest", "rabbitmq:5672"
        ))
        self.assertFalse(is_historical_local_default_uri_fixture(
            path, 50498, "amqp", "guest", "guest", "external.example:5672"
        ))

    def test_historical_local_database_default_exception_is_exactly_scoped(self) -> None:
        candidate = "integration-staging/source-candidates/31-wardrobe-part-1.txt/docker-compose.yml"
        self.assertTrue(is_historical_local_default_uri_fixture(
            candidate, 4, "postgresql+asyncpg", "cirvanna", "cirvanna", "postgres:5432"
        ))
        self.assertTrue(is_historical_local_default_uri_fixture(
            "integration-staging/source-intake/original/cirvanna-source.txt",
            50884, "postgresql+asyncpg", "cirvanna", "cirvanna", "localhost:5432"
        ))
        self.assertFalse(is_historical_local_default_uri_fixture(
            candidate, 5, "postgresql+asyncpg", "cirvanna", "cirvanna", "postgres:5432"
        ))
        self.assertFalse(is_historical_local_default_uri_fixture(
            candidate, 4, "postgresql+asyncpg", "cirvanna", "cirvanna", "external.example:5432"
        ))

    def test_detects_short_quoted_password_assignment(self) -> None:
        assignment = "password = " + '"' + "abc123" + '"' + "\n"
        findings = self.scan_text(assignment)
        self.assertIn((1, "hardcoded-password-assignment"), findings)

    def test_ignores_redacted_password_assignment(self) -> None:
        findings = self.scan_text('password = "REDACTED"\n')
        self.assertNotIn((1, "hardcoded-password-assignment"), findings)

    def test_detects_unquoted_password_default(self) -> None:
        findings = self.scan_text("password: admin\n")
        self.assertIn((1, "bare-password-assignment"), findings)

    def test_ignores_environment_password_reference(self) -> None:
        findings = self.scan_text("password: process.env.DB_PASSWORD\n")
        self.assertNotIn((1, "bare-password-assignment"), findings)


if __name__ == "__main__":
    unittest.main()
