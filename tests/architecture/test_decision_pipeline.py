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
from cultural_identity import CulturalRequirement, RequirementKind, RequirementVerdict  # noqa: E402
from eepl import EEPLContext, EEPLPolicy  # noqa: E402
from fci import ConfidenceStatus, FitConfidenceEstimate  # noqa: E402
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
        "fit_required_evidence": ("body_measurements", "garment_size_chart", "garment_geometry"),
        "fit_observed_evidence": ("body_measurements", "garment_size_chart", "garment_geometry"),
        "upstream_signals": (
            gate("safety", SignalKind.SAFETY),
            gate("legal", SignalKind.LEGAL_ELIGIBILITY),
            gate("user-hard", SignalKind.USER_HARD_CONSTRAINT),
        ),
    }
    values.update(overrides)
    return values


class DecisionPipelineIntegrationTests(unittest.TestCase):
    def test_all_modules_connect_and_cal_alone_authorizes_display(self):
        result = evaluate_candidate(**inputs())
        self.assertEqual(result.eepl.verdict.value, "pass")
        self.assertFalse(result.npl.blocked)
        self.assertEqual(result.cultural_identity.verdict, RequirementVerdict.PASS)
        self.assertEqual(result.confidence_assessment.status, ConfidenceStatus.READY)
        self.assertEqual(result.confidence_assessment.coverage_ratio, 1.0)
        self.assertEqual(result.usi.verdict.value, "pass")
        self.assertEqual(result.arbitration.verdict, DecisionVerdict.SHOW)
        self.assertTrue(result.may_display)
        prefixes = {sid.split(":")[0] for sid in result.arbitration.evaluated_signal_ids if ":" in sid}
        self.assertTrue({"eepl", "npl", "cultural", "usi", "fci"}.issubset(prefixes))


    def test_explicit_cultural_requirement_blocks_candidate(self):
        requirement = CulturalRequirement(
            requirement_id="no-sleeveless",
            declaration_id="decl-1",
            user_id="user-1",
            attribute="sleeveless",
            kind=RequirementKind.FORBIDDEN_ATTRIBUTE,
            hard=True,
        )
        result = evaluate_candidate(**inputs(
            candidate_attributes=("minimal", "sleeveless", "blue"),
            cultural_requirements=(requirement,),
        ))
        self.assertEqual(result.cultural_identity.verdict, RequirementVerdict.BLOCK)
        self.assertEqual(result.arbitration.verdict, DecisionVerdict.BLOCK)
        self.assertFalse(result.may_display)

    def test_incomplete_cultural_candidate_metadata_requires_review(self):
        requirement = CulturalRequirement(
            requirement_id="long-sleeve",
            declaration_id="decl-2",
            user_id="user-1",
            attribute="long-sleeve",
            kind=RequirementKind.REQUIRED_ATTRIBUTE,
            hard=True,
        )
        result = evaluate_candidate(**inputs(
            candidate_attributes=("minimal", "cotton"),
            candidate_attributes_complete=False,
            cultural_requirements=(requirement,),
        ))
        self.assertEqual(result.cultural_identity.verdict, RequirementVerdict.REVIEW)
        self.assertEqual(result.arbitration.verdict, DecisionVerdict.REVIEW)
        self.assertFalse(result.may_display)

    def test_foreign_user_cultural_requirement_is_rejected(self):
        requirement = CulturalRequirement(
            requirement_id="foreign-rule",
            declaration_id="decl-foreign",
            user_id="other-user",
            attribute="long-sleeve",
            kind=RequirementKind.REQUIRED_ATTRIBUTE,
        )
        with self.assertRaises(ValueError):
            evaluate_candidate(**inputs(cultural_requirements=(requirement,)))

    def test_callers_cannot_inject_cultural_approval_signal(self):
        with self.assertRaises(ValueError):
            evaluate_candidate(**inputs(upstream_signals=(
                gate("safety", SignalKind.SAFETY),
                gate("legal", SignalKind.LEGAL_ELIGIBILITY),
                gate("user-hard", SignalKind.USER_HARD_CONSTRAINT),
                gate("spoofed-culture", SignalKind.CULTURAL_REQUIREMENT),
            )))


    def test_missing_required_fit_evidence_forces_review(self):
        result = evaluate_candidate(**inputs(fit_observed_evidence=("body_measurements",)))
        self.assertEqual(result.confidence_assessment.status, ConfidenceStatus.INSUFFICIENT_EVIDENCE)
        self.assertIn("garment_size_chart", result.confidence_assessment.missing_fields)
        self.assertEqual(result.arbitration.verdict, DecisionVerdict.REVIEW)
        self.assertFalse(result.may_display)

    def test_no_declared_fit_evidence_requirements_forces_review(self):
        result = evaluate_candidate(**inputs(fit_required_evidence=(), fit_observed_evidence=()))
        self.assertEqual(result.confidence_assessment.status, ConfidenceStatus.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.arbitration.verdict, DecisionVerdict.REVIEW)

    def test_spoofed_cultural_signal_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_candidate(**inputs(upstream_signals=(
                gate("safety", SignalKind.SAFETY),
                gate("legal", SignalKind.LEGAL_ELIGIBILITY),
                gate("user-hard", SignalKind.USER_HARD_CONSTRAINT),
                gate("spoofed-culture", SignalKind.CULTURAL_REQUIREMENT),
            )))

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
