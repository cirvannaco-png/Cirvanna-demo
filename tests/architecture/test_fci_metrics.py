from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "fit-intelligence"))

from fci import compute_calibration_metrics  # noqa: E402


class FCIMetricsTests(unittest.TestCase):
    def test_metrics_are_computed_from_observed_binary_outcomes(self):
        metrics = compute_calibration_metrics(
            [0.9, 0.8, 0.2, 0.1],
            [True, False, True, False],
            interval_widths=[0.2, 0.2, 0.4, 0.4],
            bins=5,
        )
        self.assertEqual(metrics.sample_count, 4)
        self.assertAlmostEqual(metrics.brier_score, (0.01 + 0.64 + 0.64 + 0.01) / 4)
        self.assertAlmostEqual(metrics.fit_success_rate, 0.5)
        self.assertAlmostEqual(metrics.mean_interval_width, 0.3)
        self.assertAlmostEqual(metrics.high_confidence_failure_rate, 0.5)
        self.assertGreaterEqual(metrics.expected_calibration_error, 0.0)
        self.assertLessEqual(metrics.expected_calibration_error, 1.0)

    def test_probability_one_is_included_in_last_bin(self):
        metrics = compute_calibration_metrics([1.0], [True], bins=10)
        self.assertEqual(metrics.brier_score, 0.0)
        self.assertEqual(metrics.expected_calibration_error, 0.0)
        self.assertEqual(metrics.high_confidence_failure_rate, 0.0)

    def test_no_high_confidence_predictions_returns_none_not_zero(self):
        metrics = compute_calibration_metrics([0.2, 0.4], [True, False])
        self.assertIsNone(metrics.high_confidence_failure_rate)

    def test_empty_cohort_is_rejected(self):
        with self.assertRaises(ValueError):
            compute_calibration_metrics([], [])

    def test_mismatched_lengths_are_rejected(self):
        with self.assertRaises(ValueError):
            compute_calibration_metrics([0.5], [True, False])

    def test_non_finite_or_out_of_range_probabilities_are_rejected(self):
        for value in (-0.01, 1.01, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compute_calibration_metrics([value], [True])

    def test_non_boolean_outcomes_are_rejected(self):
        with self.assertRaises(ValueError):
            compute_calibration_metrics([0.5], [1])  # type: ignore[list-item]

    def test_invalid_interval_widths_are_rejected(self):
        with self.assertRaises(ValueError):
            compute_calibration_metrics([0.5], [True], interval_widths=[1.1])

    def test_invalid_bin_count_and_threshold_are_rejected(self):
        with self.assertRaises(ValueError):
            compute_calibration_metrics([0.5], [True], bins=0)
        with self.assertRaises(ValueError):
            compute_calibration_metrics([0.5], [True], high_confidence_threshold=math.nan)


if __name__ == "__main__":
    unittest.main()
