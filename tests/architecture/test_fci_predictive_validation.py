from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "fit-intelligence"))

from fci.predictive_validation import (  # noqa: E402
    FitOutcomeObservation,
    PredictiveValidationPolicy,
    PredictiveValidationStatus,
    validate_predictive_release,
)


NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
MODEL_SHA = "a" * 64
DATA_SHA = "b" * 64


def policy(**overrides):
    values = {
        "policy_version": "fit-validation-policy-v1",
        "minimum_rows": 40,
        "minimum_subjects": 30,
        "minimum_high_confidence_rows": 20,
        "high_confidence_threshold": 0.8,
        "maximum_brier_score": 0.05,
        "maximum_expected_calibration_error": 0.11,
        "minimum_roc_auc": 0.9,
        "maximum_high_confidence_failure_rate": 0.05,
        "required_slices": ("market:KE", "category:tops"),
        "minimum_rows_per_slice": 40,
        "calibration_bins": 10,
    }
    values.update(overrides)
    return PredictiveValidationPolicy(**values)


def observations(*, high_confidence_failures: bool = False, count: int = 60):
    rows = []
    for index in range(count):
        subject = f"study-subject-{index // 2:03d}"
        success = index % 2 == 0
        probability = 0.9 if success else 0.1
        if high_confidence_failures:
            if index % 4 == 0:
                success = False
            elif index % 4 == 1:
                success = True
        rows.append(FitOutcomeObservation(
            subject_key=subject,
            candidate_key=f"candidate-{index:03d}",
            predicted_probability=probability,
            observed_fit_success=success,
            predicted_at=NOW + timedelta(days=1),
            outcome_observed_at=NOW + timedelta(days=10),
            slices=("market:KE", "category:tops"),
        ))
    return tuple(rows)


class FCIPredictiveValidationTests(unittest.TestCase):
    def test_candidate_pass_requires_subject_disjoint_out_of_time_observed_outcomes(self):
        report = validate_predictive_release(
            model_version="fci-candidate-1",
            model_sha256=MODEL_SHA,
            outcome_dataset_sha256=DATA_SHA,
            training_subject_keys=tuple(f"training-subject-{i}" for i in range(20)),
            training_cutoff=NOW,
            observations=observations(),
            policy=policy(),
        )
        self.assertEqual(report.status, PredictiveValidationStatus.CANDIDATE_PASS)
        self.assertEqual(report.sample_count, 60)
        self.assertEqual(report.subject_count, 30)
        self.assertGreaterEqual(report.metrics["roc_auc"], 0.9)
        self.assertIn("POLICY_THRESHOLDS_MET_NOT_PRODUCTION_APPROVAL", report.reasons)

    def test_training_and_evaluation_subject_overlap_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must be disjoint"):
            validate_predictive_release(
                model_version="fci-candidate-1",
                model_sha256=MODEL_SHA,
                outcome_dataset_sha256=DATA_SHA,
                training_subject_keys=("study-subject-000",),
                training_cutoff=NOW,
                observations=observations(),
                policy=policy(),
            )

    def test_insufficient_rows_are_inconclusive_not_a_pass(self):
        report = validate_predictive_release(
            model_version="fci-candidate-1",
            model_sha256=MODEL_SHA,
            outcome_dataset_sha256=DATA_SHA,
            training_subject_keys=("training-subject-1",),
            training_cutoff=NOW,
            observations=observations(count=10),
            policy=policy(),
        )
        self.assertEqual(report.status, PredictiveValidationStatus.INCONCLUSIVE)
        self.assertIn("INSUFFICIENT_EVALUATION_ROWS", report.reasons)

    def test_bad_high_confidence_predictions_reject_candidate(self):
        report = validate_predictive_release(
            model_version="fci-candidate-1",
            model_sha256=MODEL_SHA,
            outcome_dataset_sha256=DATA_SHA,
            training_subject_keys=("training-subject-1",),
            training_cutoff=NOW,
            observations=observations(high_confidence_failures=True),
            policy=policy(),
        )
        self.assertEqual(report.status, PredictiveValidationStatus.REJECTED)
        self.assertTrue(any(reason.startswith("THRESHOLD_FAILED") for reason in report.reasons))

    def test_prediction_must_be_after_training_cutoff(self):
        rows = list(observations())
        rows[0] = FitOutcomeObservation(
            subject_key=rows[0].subject_key,
            candidate_key=rows[0].candidate_key,
            predicted_probability=rows[0].predicted_probability,
            observed_fit_success=rows[0].observed_fit_success,
            predicted_at=NOW,
            outcome_observed_at=NOW + timedelta(days=10),
            slices=rows[0].slices,
        )
        with self.assertRaisesRegex(ValueError, "strictly after"):
            validate_predictive_release(
                model_version="fci-candidate-1",
                model_sha256=MODEL_SHA,
                outcome_dataset_sha256=DATA_SHA,
                training_subject_keys=("training-subject-1",),
                training_cutoff=NOW,
                observations=rows,
                policy=policy(),
            )

    def test_slice_coverage_is_mandatory_when_declared(self):
        rows = [
            FitOutcomeObservation(
                subject_key=item.subject_key,
                candidate_key=item.candidate_key,
                predicted_probability=item.predicted_probability,
                observed_fit_success=item.observed_fit_success,
                predicted_at=item.predicted_at,
                outcome_observed_at=item.outcome_observed_at,
                slices=("market:KE",),
            )
            for item in observations()
        ]
        report = validate_predictive_release(
            model_version="fci-candidate-1",
            model_sha256=MODEL_SHA,
            outcome_dataset_sha256=DATA_SHA,
            training_subject_keys=("training-subject-1",),
            training_cutoff=NOW,
            observations=rows,
            policy=policy(),
        )
        self.assertEqual(report.status, PredictiveValidationStatus.INCONCLUSIVE)
        self.assertIn("INSUFFICIENT_SLICE_ROWS:category:tops", report.reasons)

    def test_invalid_artifact_digest_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "model_sha256"):
            validate_predictive_release(
                model_version="fci-candidate-1",
                model_sha256="not-a-digest",
                outcome_dataset_sha256=DATA_SHA,
                training_subject_keys=("training-subject-1",),
                training_cutoff=NOW,
                observations=observations(),
                policy=policy(),
            )


if __name__ == "__main__":
    unittest.main()
