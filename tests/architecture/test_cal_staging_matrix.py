from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "tools" / "cal_staging_matrix" / "run.py"
SPEC = importlib.util.spec_from_file_location("cal_staging_matrix_runner", RUNNER_PATH)
runner = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def valid_manifest():
    surfaces = {
        name: {
            "url": f"https://{name}.staging.example.test/v1/test",
            "method": "POST",
            "token_env": f"{name.upper()}_TOKEN",
        }
        for name in runner.REQUIRED_SURFACES
    }
    scenarios = []
    for scenario_id in runner.REQUIRED_SCENARIOS:
        scenario = {
            "id": scenario_id,
            "fixture": {},
            "exercise_surfaces": sorted(runner.REQUIRED_SURFACES),
            "assertions": {name: {"status": [200, 403, 503]} for name in runner.REQUIRED_SURFACES},
        }
        if scenario_id in {"consent_session_revoked", "cache_after_revocation", "payment_revoked_race"}:
            scenario["revoke"] = {"url": "https://fixture.staging.example.test/revoke"}
            scenario["recheck_after_revoke"] = True
        if scenario_id == "consent_session_revoked":
            scenario["race"] = {
                "surfaces": ["pnelly", "wardrobe", "look_it"],
                "revoke": {"url": "https://fixture.staging.example.test/revoke", "token_env": "CAL_REVOKE_TOKEN"},
            }
        if scenario_id == "payment_revoked_race":
            scenario["race"] = {
                "surfaces": ["cart", "checkout"],
                "revoke": {"url": "https://fixture.staging.example.test/revoke", "token_env": "CAL_REVOKE_TOKEN"},
            }
        scenarios.append(scenario)
    return {
        "environment": "staging",
        "fixture_control": {
            "url": "https://fixture.staging.example.test",
            "token_env": "CAL_FIXTURE_TOKEN",
        },
        "surfaces": surfaces,
        "scenarios": scenarios,
    }


class CALStagingMatrixContractTests(unittest.TestCase):
    def test_complete_staging_manifest_is_accepted(self):
        runner.validate_manifest(valid_manifest())

    def test_public_click_it_probe_may_omit_service_token(self):
        config = valid_manifest()
        config["surfaces"]["click_it"].pop("token_env")
        runner.validate_manifest(config)

    def test_non_staging_environment_is_rejected(self):
        config = valid_manifest()
        config["environment"] = "production"
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_missing_shopper_surface_is_rejected(self):
        config = valid_manifest()
        del config["surfaces"]["checkout"]
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_missing_surface_assertion_is_rejected(self):
        config = valid_manifest()
        del config["scenarios"][0]["assertions"]["marketplace"]
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_revocation_scenario_must_recheck_every_surface(self):
        config = valid_manifest()
        scenario = next(item for item in config["scenarios"] if item["id"] == "cache_after_revocation")
        scenario["recheck_after_revoke"] = False
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_concurrent_revocation_scenario_requires_a_race(self):
        config = valid_manifest()
        scenario = next(item for item in config["scenarios"] if item["id"] == "payment_revoked_race")
        del scenario["race"]
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_wildcard_json_paths_find_leaked_product_fields(self):
        body = {
            "products": [
                {"id": "opaque-1", "name": "Example product"},
                {"id": "opaque-2"},
            ]
        }
        self.assertEqual(runner._json_path(body, "$.products[*].name"), ["Example product"])
        self.assertEqual(runner._json_path(body, "$.products[*].image_url"), [])

    def test_secret_fields_are_redacted(self):
        value = {"Authorization": "Bearer secret", "nested": {"api_key": "do-not-print"}}
        redacted = runner._redact(value)
        self.assertEqual(redacted["Authorization"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["api_key"], "[REDACTED]")


if __name__ == "__main__":
    unittest.main()
