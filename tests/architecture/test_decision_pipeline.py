from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for package_path in (
    ROOT / "packages" / "identity-intelligence",
    ROOT / "packages" / "preferences",
    ROOT / "packages" / "fit-intelligence",
):
    sys.path.insert(0, str(package_path))

from catacaci import DecisionSignal, DecisionVerdict, SignalKind, SignalState  # noqa: E402
from catacaci.pipeline import evaluate_candidate  # noqa: E402
from eepl import EEPLContext, EEPLPolicy  # noqa: E402
from fci import FitConfidenceEstimate  # noqa: E402
from npl import NegativePreference, PreferenceSource, TargetType  # noqa: E402
from usi import StylePreference, USIProfile  # noqa: E402


def gate(signal_id: str, kind: SignalKind, state: SignalState = SignalState.PASS):
    return DecisionSignal(
        signal_id=signal_id, kind=kind, state=state,
        reason_code=f"TEST_{signal_id.upper()}",
        explanation=f"Independent upstream gate: {signal_id}",
        source_version="test-1",
    )


def fit(*, calibrated=True, confidence=0.86):
    return FitConfidenceEstimate(
        estimate_id="fit-1", user_id="user-1", candidate_id="item-1",
        model_version="test-model", calibrated=calibrated,
        confidence=confidence if calibrated else 0.99,
        lower_bound=0.80 if calibrated else None,
        upper_bound=0.91 if calibrated else None,
        calibration_version="cal-test-1" if calibrated else None,
        evidence_ids=("body-measurement-test", "brand-size-chart-test") if calibrated else (),
    )


def inputs(**overrides):
    values = {
        "request_id": "req-1",
        "candidate_id": "item-1",
        "eepl_policy": EEPLPolicy(
            policy_id="standard-policy", minimum_age=18,
            allowed_locations=("Nairobi",), allowed_occasions=("everyday",),
            allowed_climates=("warm",),
        ),
        "context": EEPLContext("user-1", 21, "Nairobi", "everyday", "warm"),
        "usi_profile": USIProfile("profile-1", "user-1", "usi-v1", (
            StylePreference("style-1", "user-1", "minimal", 1.0),
            StylePreference("style-2", "user-1", "cotton", 0.5),
        )),
        "candidate_attributes": ("minimal", "cotton", "blue"),
        "candidate_attributes_complete": True,
        "negative_preferences": (),
        "fit_estimate": fit(),
        "upstream_signals": (
            gate("safety", SignalKind.SAFETY),
            gate("legal", SignalKind.LEGAL_ELIGIBILITY),
            gate("user-hard", SignalKind.USER_HARD_CONSTRAINT),
            gate("culture", SignalKind.CULTURAL_REQUIREMENT),
        ),
    }
    values.update(overrides)
    return values


class DecisionPipelineIntegrationTests(unittest.TestCase):
    def test_all_modules_connect_and_cal_alone_authorizes_display(self):
        result = evaluate_candidate(**inputs())
        self.assertEqual(result.eepl.verdict.value, "pass")
        self.assertFalse(result.npl.blocked)
        self.assertEqual(result.usi.verdict.value, "pass")
        self.assertEqual(result.arbitration.verdict, DecisionVerdict.SHOW)
        self.assertTrue(result.may_display)
        prefixes = {sid.split(":")[0] for sid in result.arbitration.evaluated_signal_ids if ":" in sid}
        self.assertTrue({"eepl", "npl", "usi", "fci"}.issubset(prefixes))

    def test_npl_veto_blocks_even_with_high_fit_confidence(self):
        veto = NegativePreference(
            preference_id="no-blue", user_id="user-1",
            target_type=TargetType.ATTRIBUTE, target_value="blue",
            source=PreferenceSource.USER_DECLARED,
        )
        result = evaluate_candidate(**inputs(negative_preferences=(veto,)))
        self.assertTrue(result.npl.blocked)
        self.assertEqual(result.arbitration.verdict, DecisionVerdict.BLOCK)
        self.assertFalse(result.may_display)

    def test_missing_external_required_gates_fail_closed(self):
        result = evaluate_candidate(**inputs(upstream_signals=()))
        self.assertEqual(result.arbitration.verdict, DecisionVerdict.REVIEW)
        self.assertFalse(result.may_display)

    def test_eepl_policy_violation_blocks(self):
        context = EEPLContext("user-1", 16, "Nairobi", "everyday", "warm")
        result = evaluate_candidate(**inputs(context=context))
        self.assertEqual(result.arbitration.verdict, DecisionVerdict.BLOCK)
        self.assertFalse(result.may_display)

    def test_missing_context_and_uncalibrated_fit_cannot_authorize_display(self):
        result = evaluate_candidate(**inputs(
            context=EEPLContext("user-1", 21, None, "everyday", "warm"),
            fit_estimate=fit(calibrated=False),
        ))
        self.assertEqual(result.arbitration.verdict, DecisionVerdict.REVIEW)
        self.assertFalse(result.may_display)

    def test_soft_style_mismatch_routes_to_review_not_hard_block(self):
        result = evaluate_candidate(**inputs(candidate_attributes=("formal",)))
        self.assertEqual(result.arbitration.verdict, DecisionVerdict.REVIEW)
        self.assertFalse(result.may_display)

    def test_identity_and_candidate_mismatches_are_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_candidate(**inputs(context=EEPLContext("other-user", 21, "Nairobi", "everyday", "warm")))
        with self.assertRaises(ValueError):
            evaluate_candidate(**inputs(fit_estimate=FitConfidenceEstimate(
                estimate_id="fit-foreign", user_id="user-1", candidate_id="other-item",
                model_version="test-model", calibrated=False,
            )))

    def test_duplicate_signal_ids_are_rejected_by_cal(self):
        repeated = gate("safety", SignalKind.SAFETY)
        with self.assertRaises(ValueError):
            evaluate_candidate(**inputs(upstream_signals=(
                repeated, repeated,
            )))


if __name__ == "__main__":
    unittest.main()
