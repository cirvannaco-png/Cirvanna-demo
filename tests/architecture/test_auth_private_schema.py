from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "services" / "marketplace-bff" / "migrations" / "0001_auth_private_sessions.sql"
SERVICE = ROOT / "services" / "marketplace-bff" / "app" / "auth_sessions.py"


class AuthPrivateSchemaTests(unittest.TestCase):
    def test_auth_tables_are_private_and_client_roles_are_revoked(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("REVOKE ALL ON SCHEMA auth_private FROM PUBLIC, anon, authenticated", sql)
        self.assertIn("REVOKE ALL ON ALL TABLES IN SCHEMA auth_private FROM PUBLIC, anon, authenticated", sql)
        self.assertIn("GRANT SELECT, INSERT, UPDATE, DELETE ON auth_private.pending_auth, auth_private.sessions TO cirvanna_bff_auth", sql)

    def test_auth_tables_have_service_only_rls_policies(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("ALTER TABLE auth_private.pending_auth ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("ALTER TABLE auth_private.sessions ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("FOR ALL TO cirvanna_bff_auth USING (true) WITH CHECK (true)", sql)

    def test_session_runtime_uses_encrypted_opaque_cookie_and_server_side_tokens(self):
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn('COOKIE_NAME = "__Host-cirvanna_session"', source)
        self.assertIn("_encrypt(", source)
        self.assertIn("_hash(session_id)", source)
        self.assertIn("HttpOnly", source) if "HttpOnly" in source else self.assertIn("httponly=True", source)
        self.assertIn("algorithms=[\"ES256\", \"RS256\"]", source)

    def test_refresh_rotation_is_serialized_and_logout_revokes_local_session(self):
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn("FOR UPDATE", source)
        self.assertIn("UPDATE auth_private.sessions SET revoked_at=now()", source)


if __name__ == "__main__":
    unittest.main()
