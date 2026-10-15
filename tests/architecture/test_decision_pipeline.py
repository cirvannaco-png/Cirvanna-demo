from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for package_root in (
    ROOT / "packages" / "identity-intelligence",
    ROOT / "packages" / "preferences",
    ROOT / "packages" / "fit-intelligence",
    ROOT / "services" / "api-gateway",
):
    sys.path.insert(0, str(package_root))

from catacaci import ArbitrationRequest, DecisionSignal, SignalKind, SignalState  # noqa: E402
from eepl import EEPLContext, EEPLPolicy, evaluate as evaluate_eepl  # noqa: E402
from npl import NegativePreference, PreferenceSource, TargetType, evaluate as evaluate_npl  # noqa: E402
from cultural_identity import (  # noqa: E402
    CulturalIdentityResult,
    CulturalRequirement,
    RequirementKind,
    RequirementVerdict,
    evaluate as evaluate_cultural,
)
from usi import StylePreference, USIProfile, evaluate as evaluate_usi  # noqa: E402
from fci import FitConfidenceEstimate  # noqa: E402
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


def request(candidate_id="item-1", include_fit=True):
    required = (
        SignalKind.SAFETY,
        SignalKind.LEGAL_ELIGIBILITY,
        SignalKind.USER_HARD_CONSTRAINT,
        SignalKind.CULTURAL_REQUIREMENT,
        SignalKind.IDENTITY_ALIGNMENT,
    )
    signals = tuple(signal(f"gate-{kind.value}", kind) for kind in required)
    if include_fit:
        signals += (signal("fit", SignalKind.FIT_CONFIDENCE, confidence=0.95),)
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

    def test_explicit_cultural_conflict_blocks(self):
        eepl, npl = results()
        cultural = evaluate_cultural(
            "user-1", "item-1", ("sleeveless",),
            (CulturalRequirement("r1", "decl-r1", "user-1", "sleeveless", RequirementKind.FORBIDDEN_ATTRIBUTE),),
            candidate_attributes_complete=True,
        )
        result = arbitrate_candidate(request(), eepl, npl, cultural_result=cultural)
        self.assertEqual(result.cal_result.verdict.value, "block")
        self.assertIn("CULTURAL_FORBIDDEN_ATTRIBUTE_PRESENT", {reason.code for reason in result.cal_result.reasons})

    def test_incomplete_cultural_metadata_routes_to_review(self):
        eepl, npl = results()
        cultural = evaluate_cultural(
            "user-1", "item-1", ("cotton",),
            (CulturalRequirement("r1", "decl-r1", "user-1", "long-sleeve", RequirementKind.REQUIRED_ATTRIBUTE),),
            candidate_attributes_complete=False,
        )
        result = arbitrate_candidate(request(), eepl, npl, cultural_result=cultural)
        self.assertEqual(result.cal_result.verdict.value, "review")
        self.assertFalse(result.may_display)

    def test_unknown_cultural_policy_code_fails_closed_to_review(self):
        eepl, npl = results()
        cultural = CulturalIdentityResult(
            contract_version="1.0.0",
            user_id="user-1",
            candidate_id="item-1",
            verdict=RequirementVerdict.PASS,
            reason_codes=("CULTURAL_FUTURE_UNKNOWN_CODE",),
            explanations=("Unrecognized policy result.",),
            hard_conflict_ids=(),
            soft_conflict_ids=(),
        )
        result = arbitrate_candidate(request(), eepl, npl, cultural_result=cultural)
        self.assertEqual(result.cal_result.verdict.value, "review")
        self.assertFalse(result.may_display)
        self.assertIn(
            "CULTURAL_FUTURE_UNKNOWN_CODE",
            {reason.code for reason in result.cal_result.reasons},
        )

    def test_usi_low_alignment_routes_to_review_not_hard_block(self):
        eepl, npl = results()
        profile = USIProfile("profile-1", "user-1", "usi-v1", (StylePreference("p1", "user-1", "minimal"),))
        usi = evaluate_usi(profile, "item-1", ("maximalist",), candidate_attributes_complete=True)
        result = arbitrate_candidate(request(), eepl, npl, usi_result=usi)
        self.assertEqual(usi.reason_code, "USI_ALIGNMENT_BELOW_THRESHOLD")
        self.assertEqual(result.cal_result.verdict.value, "review")
        self.assertFalse(result.may_display)
        self.assertIn("NON_VETO_SIGNAL_BLOCKED", {reason.code for reason in result.cal_result.reasons})

    def test_calibrated_fci_signal_can_satisfy_fit_gate_but_not_other_gates(self):
        eepl, npl = results()
        estimate = FitConfidenceEstimate(
            estimate_id="fci-1", user_id="user-1", candidate_id="item-1",
            model_version="fci-model-1", calibrated=True, confidence=0.95,
            lower_bound=0.90, upper_bound=0.98, calibration_version="cal-1",
            evidence_ids=("body-1", "brand-chart-1"),
        )
        result = arbitrate_candidate(request(include_fit=False), eepl, npl, fci_estimate=estimate)
        self.assertEqual(result.cal_result.verdict.value, "show")

    def test_uncalibrated_fci_estimate_routes_to_review(self):
        eepl, npl = results()
        estimate = FitConfidenceEstimate(
            estimate_id="fci-uncalibrated", user_id="user-1", candidate_id="item-1",
            model_version="experimental", calibrated=False, confidence=0.99,
        )
        result = arbitrate_candidate(request(include_fit=False), eepl, npl, fci_estimate=estimate)
        self.assertEqual(estimate.to_cal_signal().reason_code, "FCI_UNCALIBRATED_ESTIMATE")
        self.assertEqual(result.cal_result.verdict.value, "review")
        self.assertFalse(result.may_display)

    def test_fci_candidate_mismatch_is_rejected(self):
        eepl, npl = results()
        estimate = FitConfidenceEstimate(
            estimate_id="fci-1", user_id="user-1", candidate_id="other-item",
            model_version="fci-model-1", calibrated=False,
        )
        with self.assertRaises(ValueError):
            arbitrate_candidate(request(), eepl, npl, fci_estimate=estimate)

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
