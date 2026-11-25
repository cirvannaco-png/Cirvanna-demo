from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "services" / "identity-learning-service" / "migrations"
WORKFLOW = ROOT / ".github" / "workflows" / "identity-learning-service.yml"
SERVICE = ROOT / "services" / "identity-learning-service" / "app" / "main.py"


class IdentityAgeMigrationChainTests(unittest.TestCase):
    def test_age_migrations_follow_private_schema_and_role_migrations(self):
        expected = [
            "0009_foreign_key_indexes.sql",
            "0010_runtime_role_grants.sql",
            "0011_supabase_auth_app_role_hook.sql",
            "0012_age_evidence_lifecycle.sql",
            "0013_age_attestation_retry_delivery.sql",
            "0014_age_attestation_delivery_constraints.sql",
            "0015_age_session_terminal_state_constraint.sql",
            "0016_age_session_request_idempotency.sql",
        ]
        workflow = WORKFLOW.read_text(encoding="utf-8")
        offsets = [workflow.index(f"migrations/{name}") for name in expected]
        self.assertEqual(offsets, sorted(offsets))
        for name in expected:
            self.assertTrue((MIGRATIONS / name).is_file(), name)
        for name in expected[3:]:
            self.assertTrue((MIGRATIONS / name.replace(".sql", ".down.sql")).is_file(), name)

    def test_colliding_age_migration_names_are_absent(self):
        for name in (
            "0009_age_evidence_lifecycle.sql",
            "0010_age_attestation_retry_delivery.sql",
            "0011_age_attestation_delivery_constraints.sql",
            "0012_age_session_terminal_state_constraint.sql",
        ):
            self.assertFalse((MIGRATIONS / name).exists(), name)

    def test_runtime_engine_is_pinned_to_private_schema(self):
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn("-csearch_path=identity_private", source)

    def test_runtime_group_is_created_by_migration_not_ci_bootstrap(self):
        grants = (MIGRATIONS / "0010_runtime_role_grants.sql").read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("CREATE ROLE identity_learning_service NOLOGIN", grants)
        self.assertNotIn("CREATE ROLE identity_learning_service", workflow)

    def test_eepl_accepts_only_verified_threshold_evidence_fields(self):
        eepl = (ROOT / "packages" / "identity-intelligence" / "eepl" / "core.py").read_text(encoding="utf-8")
        self.assertIn("minimum_age_threshold", eepl)
        self.assertIn("minimum_age_threshold_met", eepl)

    def test_staging_idempotency_constraint_is_reconciled(self):
        migration = (MIGRATIONS / "0016_age_session_request_idempotency.sql").read_text(encoding="utf-8")
        self.assertIn("uq_identity_age_session_request_policy", migration)
        self.assertIn("pg_constraint", migration)
        self.assertIn("UNIQUE (subject_id, request_id, purpose, policy_id, policy_version)", migration)


if __name__ == "__main__":
    unittest.main()
