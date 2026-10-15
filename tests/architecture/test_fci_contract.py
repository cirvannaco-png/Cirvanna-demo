from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "fit-intelligence"))
sys.path.insert(0, str(ROOT / "packages" / "identity-intelligence"))

from catacaci import SignalKind, SignalState  # noqa: E402
from fci import FitConfidenceEstimate  # noqa: E402


class FCIContractTests(unittest.TestCase):
    def test_calibrated_estimate_maps_to_fit_signal_with_provenance(self):
        estimate = FitConfidenceEstimate(
            estimate_id="fit-1", user_id="user-1", candidate_id="item-1",
                model_version="fci-model-3",
            calibrated=True,
            confidence=0.82,
            lower_bound=0.75,
            upper_bound=0.88,
            calibration_version="cal-2026-10",
            evidence_ids=("body-measurement-1", "brand-chart-4"),
        )
        signal = estimate.to_cal_signal()
        self.assertEqual(signal.kind, SignalKind.FIT_CONFIDENCE)
        self.assertEqual(signal.state, SignalState.PASS)
        self.assertEqual(signal.confidence, 0.82)
        self.assertIn("cal-2026-10", signal.source_version)

    def test_uncalibrated_estimate_becomes_unknown_not_pass(self):
        estimate = FitConfidenceEstimate(
            estimate_id="fit-uncalibrated", user_id="user-1", candidate_id="item-1",
                model_version="experimental",
            calibrated=False,
            confidence=0.99,
        )
        signal = estimate.to_cal_signal()
        self.assertEqual(signal.state, SignalState.UNKNOWN)
        self.assertIsNone(signal.confidence)
        self.assertEqual(signal.reason_code, "FCI_UNCALIBRATED_ESTIMATE")

    def test_calibrated_estimate_requires_evidence_and_calibration_version(self):
        with self.assertRaises(ValueError):
            FitConfidenceEstimate(
                estimate_id="fit-1", user_id="user-1", candidate_id="item-1", model_version="m1", calibrated=True,
                confidence=0.8, lower_bound=0.7, upper_bound=0.9,
                calibration_version="cal-1",
            )

    def test_confidence_must_be_inside_interval(self):
        with self.assertRaises(ValueError):
            FitConfidenceEstimate(
                estimate_id="fit-1", user_id="user-1", candidate_id="item-1", model_version="m1", calibrated=True,
                confidence=0.95, lower_bound=0.7, upper_bound=0.9,
                calibration_version="cal-1", evidence_ids=("e1",),
            )

    def test_invalid_confidence_is_rejected(self):
        with self.assertRaises(ValueError):
            FitConfidenceEstimate(estimate_id="fit-1", user_id="user-1", candidate_id="item-1", model_version="m1", calibrated=False, confidence=1.2)

    def test_duplicate_evidence_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            FitConfidenceEstimate(
                estimate_id="fit-1", user_id="user-1", candidate_id="item-1", model_version="m1", calibrated=True,
                confidence=0.8, lower_bound=0.7, upper_bound=0.9,
                calibration_version="cal-1", evidence_ids=("e1", "e1"),
            )


if __name__ == "__main__":
    unittest.main()
