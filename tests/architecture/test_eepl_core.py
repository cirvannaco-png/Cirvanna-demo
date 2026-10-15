from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "identity-intelligence"))

from eepl import ContextField, EEPLContext, EEPLPolicy, GateVerdict, evaluate  # noqa: E402


class EEPLPolicyTests(unittest.TestCase):
    def test_all_explicit_constraints_pass(self):
        policy = EEPLPolicy(
            policy_id="summer-outdoor",
            minimum_age=18,
            allowed_locations=("Nairobi",),
            allowed_occasions=("outdoor",),
            allowed_climates=("warm",),
        )
        result = evaluate(policy, EEPLContext("u1", 21, "Nairobi", "outdoor", "warm"), "item1")
        self.assertEqual(result.verdict, GateVerdict.PASS)
        self.assertEqual(result.reason_codes, ("EEPL_POLICY_PASSED",))

    def test_age_violation_blocks(self):
        result = evaluate(EEPLPolicy("adult", minimum_age=18), EEPLContext("u1", 17), "item1")
        self.assertEqual(result.verdict, GateVerdict.BLOCK)
        self.assertIn("EEPL_MINIMUM_AGE_NOT_MET", result.reason_codes)

    def test_location_allowlist_is_case_insensitive(self):
        result = evaluate(EEPLPolicy("loc", allowed_locations=("Nairobi",)), EEPLContext("u1", location="nAiRoBi"), "item1")
        self.assertEqual(result.verdict, GateVerdict.PASS)

    def test_missing_required_context_routes_to_review(self):
        result = evaluate(EEPLPolicy("loc", allowed_locations=("Nairobi",)), EEPLContext("u1"), "item1")
        self.assertEqual(result.verdict, GateVerdict.REVIEW)
        self.assertIn("EEPL_REQUIRED_CONTEXT_MISSING_LOCATION", result.reason_codes)

    def test_block_dominates_missing_context_review(self):
        policy = EEPLPolicy("mixed", minimum_age=18, allowed_locations=("Nairobi",))
        result = evaluate(policy, EEPLContext("u1", 16), "item1")
        self.assertEqual(result.verdict, GateVerdict.BLOCK)
        self.assertIn("EEPL_MINIMUM_AGE_NOT_MET", result.reason_codes)
        self.assertIn("EEPL_REQUIRED_CONTEXT_MISSING_LOCATION", result.reason_codes)

    def test_occasion_and_climate_constraints_block(self):
        policy = EEPLPolicy("summer", allowed_occasions=("formal",), allowed_climates=("warm",))
        result = evaluate(policy, EEPLContext("u1", occasion="gym", climate="cold"), "item1")
        self.assertEqual(result.verdict, GateVerdict.BLOCK)
        self.assertIn("EEPL_OCCASION_NOT_ALLOWED", result.reason_codes)
        self.assertIn("EEPL_CLIMATE_NOT_ALLOWED", result.reason_codes)

    def test_explicit_required_context_is_not_guessed(self):
        policy = EEPLPolicy("declared", required_context=(ContextField.CLIMATE,))
        result = evaluate(policy, EEPLContext("u1"), "item1")
        self.assertEqual(result.verdict, GateVerdict.REVIEW)

    def test_invalid_age_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            EEPLPolicy("invalid", minimum_age=21, maximum_age=18)

    def test_invalid_context_age_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(EEPLPolicy("valid"), EEPLContext("u1", -1), "item1")
