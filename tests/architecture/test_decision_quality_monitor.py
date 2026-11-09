from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "identity-intelligence"))

from catacaci.core import DecisionVerdict  # noqa: E402
from catacaci.quality_monitor import DecisionQualityEvent, summarize_decision_quality  # noqa: E402


class DecisionQualityMonitorTests(unittest.TestCase):
    def test_non_show_display_is_critical(self):
        result = summarize_decision_quality([
            DecisionQualityEvent(
                decision_id="decision-1",
                verdict=DecisionVerdict.REVIEW,
                displayed=True,
                policy_version="policy-1",
            ),
        ])
        self.assertEqual(result.status, "critical")
        self.assertEqual(result.displayed_non_show_count, 1)

    def test_unknown_evidence_and_provider_failures_need_attention(self):
        result = summarize_decision_quality([
            DecisionQualityEvent(
                decision_id="decision-1",
                verdict=DecisionVerdict.REVIEW,
                displayed=False,
                policy_version="policy-1",
                missing_required_evidence=1,
                provider_failures=1,
            ),
        ])
        self.assertEqual(result.status, "attention_required")
        self.assertEqual(result.incomplete_evidence_rate, 1.0)
        self.assertEqual(result.provider_failure_rate, 1.0)

    def test_labeled_outcomes_produce_brier_and_high_confidence_failure_rate(self):
        observed_at = datetime(2026, 11, 5, tzinfo=timezone.utc)
        result = summarize_decision_quality([
            DecisionQualityEvent(
                decision_id="decision-1",
                verdict=DecisionVerdict.SHOW,
                displayed=True,
                policy_version="policy-1",
                fci_probability=0.9,
                observed_fit_success=True,
                outcome_observed_at=observed_at,
            ),
            DecisionQualityEvent(
                decision_id="decision-2",
                verdict=DecisionVerdict.SHOW,
                displayed=True,
                policy_version="policy-1",
                fci_probability=0.8,
                observed_fit_success=False,
                outcome_observed_at=observed_at,
            ),
        ])
        self.assertEqual(result.status, "collecting")
        self.assertEqual(result.labeled_fit_outcomes, 2)
        self.assertAlmostEqual(result.fci_brier_score, 0.325)
        self.assertEqual(result.high_confidence_failure_rate, 0.5)

    def test_no_observed_outcomes_are_not_scored_as_zero(self):
        result = summarize_decision_quality([
            DecisionQualityEvent(
                decision_id="decision-1",
                verdict=DecisionVerdict.REVIEW,
                displayed=False,
                policy_version="policy-1",
            ),
        ])
        self.assertIsNone(result.fci_brier_score)
        self.assertIsNone(result.fit_outcome_success_rate)

    def test_duplicate_decision_ids_are_rejected(self):
        event = DecisionQualityEvent(
            decision_id="decision-1",
            verdict=DecisionVerdict.SHOW,
            displayed=True,
            policy_version="policy-1",
        )
        with self.assertRaisesRegex(ValueError, "unique"):
            summarize_decision_quality([event, event])

    def test_fit_outcome_requires_original_prediction_and_timestamp(self):
        with self.assertRaisesRegex(ValueError, "requires its original FCI probability"):
            DecisionQualityEvent(
                decision_id="decision-1",
                verdict=DecisionVerdict.SHOW,
                displayed=True,
                policy_version="policy-1",
                observed_fit_success=True,
                outcome_observed_at=datetime(2026, 11, 5, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
