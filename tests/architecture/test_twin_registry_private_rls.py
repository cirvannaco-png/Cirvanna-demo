from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "services" / "twin-registry" / "migrations" / "0005_private_service_rls.sql"
WORKFLOW = ROOT / ".github" / "workflows" / "twin-registry.yml"


class TwinRegistryPrivateRlsTests(unittest.TestCase):
    def test_private_twin_tables_have_service_only_rls(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("ALTER TABLE twin_private.twin_registry_twins ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("ALTER TABLE twin_private.twin_registry_deletion_outbox ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("FOR ALL TO twin_registry_service USING (true) WITH CHECK (true)", sql)
        self.assertIn("REVOKE ALL ON SCHEMA twin_private FROM PUBLIC, anon, authenticated", sql)

    def test_twin_workflow_applies_and_reapplies_rls_migration(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("0005_private_service_rls.sql", workflow)
        self.assertIn("0005_private_service_rls.down.sql", workflow)
        self.assertIn("Twin private RLS is not enabled", workflow)


if __name__ == "__main__":
    unittest.main()
