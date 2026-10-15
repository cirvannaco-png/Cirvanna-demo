from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for package_root in (
    ROOT / "packages" / "identity-intelligence",
    ROOT / "packages" / "preferences",
    ROOT / "services" / "api-gateway",
):
    sys.path.insert(0, str(package_root))

from catacaci import ArbitrationRequest, DecisionSignal, SignalKind, SignalState  # noqa: E402
from eepl import EEPLContext, EEPLPolicy, evaluate as evaluate_eepl  # noqa: E402
from npl import NegativePreference, PreferenceSource, TargetType, evaluate as evaluate_npl  # noqa: E402
from app import arbitrate_candidate  # noqa: E402


def signal(signal_id, kind, state=SignalState.PASS, confidence=None):
    return DecisionSignal(
        signal_id=signal_id,
        kind=kind,
        state=state,
        reason_code=f"TEST_{signal_id.upper()}",
        explanation=f"Test signal {signal_id}",
        required=True,
        confidence=confidence,
        source_version="test-1",
    )


def request(candidate_id="item-1"):
    required = (
        SignalKind.SAFETY,
        SignalKind.LEGAL_ELIGIBILITY,
        SignalKind.USER_HARD_CONSTRAINT,
        SignalKind.CULTURAL_REQUIREMENT,
        SignalKind.IDENTITY_ALIGNMENT,
    )
    signals = tuple(signal(f"gate-{kind.value}", kind) for kind in required) + (
        signal("fit", SignalKind.FIT_CONFIDENCE, confidence=0.95),
    )
    return ArbitrationRequest("req-1", candidate_id, signals)


def results(policy=None, context=None, preferences=(), candidate_id="item-1"):
    policy = policy or EEPLPolicy("open")
    context = context or EEPLContext("user-1")
    eepl = evaluate_eepl(policy, context, candidate_id)
    npl = evaluate_npl("user-1", candidate_id, ("red",), preferences)
    return eepl, npl


class DecisionPipelineTests(unittest.TestCase):
    def test_all_gates_pass_and_cal_authorizes_show(self):
        eepl, npl = results()
        result = arbitrate_candidate(request(), eepl, npl)
        self.assertEqual(result.cal_result.verdict.value, "show")
        self.assertTrue(result.may_display)

    def test_npl_hard_veto_beats_high_fit_confidence(self):
        preference = NegativePreference(
            "p1", "user-1", TargetType.ATTRIBUTE, "red", PreferenceSource.USER_DECLARED
        )
        eepl, npl = results(preferences=(preference,))
        result = arbitrate_candidate(request(), eepl, npl)
        self.assertEqual(result.cal_result.verdict.value, "block")
        self.assertFalse(result.may_display)

    def test_age_eligibility_block_maps_to_legal_veto(self):
        eepl, npl = results(
            policy=EEPLPolicy("adult", minimum_age=18),
            context=EEPLContext("user-1", age_years=16),
        )
        result = arbitrate_candidate(request(), eepl, npl)
        self.assertEqual(result.cal_result.verdict.value, "block")
        self.assertIn("EEPL_MINIMUM_AGE_NOT_MET", {reason.code for reason in result.cal_result.reasons})

    def test_missing_required_eepl_context_routes_to_review(self):
        eepl, npl = results(policy=EEPLPolicy("location", allowed_locations=("Nairobi",)))
        result = arbitrate_candidate(request(), eepl, npl)
        self.assertEqual(result.cal_result.verdict.value, "review")
        self.assertFalse(result.may_display)

    def test_candidate_mismatch_is_rejected(self):
        eepl, npl = results(candidate_id="other-item")
        with self.assertRaises(ValueError):
            arbitrate_candidate(request("item-1"), eepl, npl)

    def test_user_mismatch_is_rejected(self):
        eepl = evaluate_eepl(EEPLPolicy("open"), EEPLContext("user-1"), "item-1")
        npl = evaluate_npl("user-2", "item-1", (), ())
        with self.assertRaises(ValueError):
            arbitrate_candidate(request(), eepl, npl)


if __name__ == "__main__":
    unittest.main()
