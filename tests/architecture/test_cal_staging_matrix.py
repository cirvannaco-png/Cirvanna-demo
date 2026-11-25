from __future__ import annotations

import importlib.util
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
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
            "assertions": {name: {"status": [200, 403, 503], "json_present": ["$.decision.verdict"]} for name in runner.REQUIRED_SURFACES},
        }
        if scenario_id in {"consent_session_revoked", "cache_after_revocation", "payment_revoked_race"}:
            scenario["revoke"] = {"url": "https://fixture.staging.example.test/revoke", "token_env": "CAL_REVOKE_TOKEN"}
            scenario["recheck_after_revoke"] = True
            scenario["post_revoke_assertions"] = {
                name: {"status": [401, 403], "json_equals": {"$.decision.verdict": "BLOCK"}}
                for name in runner.REQUIRED_SURFACES
            }
        if scenario_id == "consent_session_revoked":
            scenario["race"] = {
                "surfaces": ["pnelly", "wardrobe", "look_it"],
                "revoke": {"url": "https://fixture.staging.example.test/revoke", "token_env": "CAL_REVOKE_TOKEN"},
            }
            scenario["race_assertions"] = {
                name: {"status": [401, 403], "json_equals": {"$.decision.verdict": "BLOCK"}}
                for name in scenario["race"]["surfaces"]
            }
        if scenario_id == "payment_revoked_race":
            scenario["race"] = {
                "surfaces": ["cart", "checkout"],
                "revoke": {"url": "https://fixture.staging.example.test/revoke", "token_env": "CAL_REVOKE_TOKEN"},
            }
            scenario["race_assertions"] = {
                name: {"status": [401, 403], "json_equals": {"$.decision.verdict": "BLOCK"}}
                for name in scenario["race"]["surfaces"]
            }
        if scenario_id in {"consent_session_revoked", "cache_after_revocation", "payment_revoked_race"}:
            scenario["post_revoke_assertions"] = {
                name: {
                    "status": [401, 403, 410],
                    "require_no_store": True,
                    "json_absent": ["$.products[*].id", "$.items[*].product_id", "$.offers[*].id", "$.recommendations[*].id"],
                }
                for name in runner.REQUIRED_SURFACES
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
    def test_jsonpath_supports_nested_and_wildcard_paths(self):
        document = {"decision": {"verdict": "BLOCK"}, "products": [{"id": "p1"}, {"id": "p2"}]}
        self.assertEqual(runner._json_path(document, "$.decision.verdict"), "BLOCK")
        self.assertEqual(runner._json_path(document, "$.products[*].id"), ["p1", "p2"])
        self.assertIs(runner._json_path(document, "$.missing.value"), runner._MISSING)

    def test_http_client_does_not_follow_redirects(self):
        observed = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                observed.append(self.headers.get("Authorization"))
                self.send_response(302)
                self.send_header("Location", "/credential-capture")
                self.end_headers()
            def log_message(self, *_args):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        token_name = "CAL_REDIRECT_TEST_TOKEN"
        previous = os.environ.get(token_name)
        os.environ[token_name] = "x" * 40
        try:
            response = runner._http({
                "url": f"http://127.0.0.1:{server.server_port}/start",
                "method": "GET",
                "token_env": token_name,
            }, timeout=3)
            self.assertEqual(response.status, 302)
            self.assertEqual(observed, ["Bearer " + "x" * 40])
        finally:
            if previous is None:
                os.environ.pop(token_name, None)
            else:
                os.environ[token_name] = previous
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

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

    def test_extra_shopper_surface_is_rejected(self):
        config = valid_manifest()
        config["surfaces"]["unregistered_surface"] = {
            "url": "https://extra.staging.example.test",
            "method": "GET",
        }
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_duplicate_scenario_ids_are_rejected(self):
        config = valid_manifest()
        config["scenarios"][1]["id"] = config["scenarios"][0]["id"]
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

    def test_malformed_jsonpath_is_rejected_before_fixture_activation(self):
        config = valid_manifest()
        scenario = config["scenarios"][0]
        scenario["assertions"]["marketplace"] = {"json_present": ["$.missing.bad path"]}
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_post_revoke_assertions_require_cache_protection(self):
        config = valid_manifest()
        scenario = next(item for item in config["scenarios"] if item["id"] == "cache_after_revocation")
        scenario["post_revoke_assertions"]["marketplace"]["require_no_store"] = False
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_surface_assertions_cannot_be_status_only(self):
        config = valid_manifest()
        scenario = config["scenarios"][0]
        scenario["assertions"]["marketplace"] = {"status": [403]}
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_revocation_scenario_must_recheck_every_surface(self):
        config = valid_manifest()
        scenario = next(item for item in config["scenarios"] if item["id"] == "cache_after_revocation")
        scenario["recheck_after_revoke"] = False
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_revocation_replay_requires_explicit_safe_assertions_for_every_surface(self):
        config = valid_manifest()
        scenario = next(item for item in config["scenarios"] if item["id"] == "cache_after_revocation")
        del scenario["post_revoke_assertions"]["marketplace"]
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_revocation_replay_cannot_fall_back_to_pre_revocation_assertions(self):
        config = valid_manifest()
        scenario = next(item for item in config["scenarios"] if item["id"] == "cache_after_revocation")
        scenario["post_revoke_assertions"]["marketplace"] = {"status": [200], "require_no_store": True}
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_concurrent_revocation_scenario_requires_a_race(self):
        config = valid_manifest()
        scenario = next(item for item in config["scenarios"] if item["id"] == "payment_revoked_race")
        del scenario["race"]
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_race_and_post_race_revocation_must_target_same_operation(self):
        config = valid_manifest()
        scenario = next(item for item in config["scenarios"] if item["id"] == "consent_session_revoked")
        scenario["revoke"]["url"] = "https://other.staging.example.test/revoke"
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_revocation_race_requires_semantic_assertions(self):
        config = valid_manifest()
        scenario = next(item for item in config["scenarios"] if item["id"] == "payment_revoked_race")
        del scenario["race_assertions"]
        with self.assertRaises(runner.MatrixError):
            runner.validate_manifest(config)

    def test_post_revocation_cannot_fall_back_to_status_only(self):
        config = valid_manifest()
        scenario = next(item for item in config["scenarios"] if item["id"] == "cache_after_revocation")
        scenario["post_revoke_assertions"]["marketplace"] = {"status": [403]}
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
