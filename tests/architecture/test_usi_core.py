from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "identity-intelligence"))

from catacaci import SignalKind, SignalState  # noqa: E402
from usi import StylePreference, USIProfile, USIVerdict, evaluate  # noqa: E402


class USIExplicitAlignmentTests(unittest.TestCase):
    def profile(self, preferences):
        return USIProfile("profile-1", "u1", "usi-v1", tuple(preferences))

    def test_matching_explicit_preferences_pass(self):
        profile = self.profile((
            StylePreference("p1", "u1", "minimal", 1.0),
            StylePreference("p2", "u1", "cotton", 0.5),
        ))
        result = evaluate(profile, "item-1", ("minimal", "cotton"), candidate_attributes_complete=True)
        self.assertEqual(result.verdict, USIVerdict.PASS)
        self.assertEqual(result.alignment_score, 1.0)
        signal = result.to_cal_signal()
        self.assertEqual(signal.kind, SignalKind.IDENTITY_ALIGNMENT)
        self.assertEqual(signal.state, SignalState.PASS)

    def test_below_threshold_is_reviewable_not_hard_veto(self):
        profile = self.profile((StylePreference("p1", "u1", "minimal"),))
        result = evaluate(profile, "item-1", ("maximalist",), candidate_attributes_complete=True)
        self.assertEqual(result.verdict, USIVerdict.BELOW_THRESHOLD)
        self.assertEqual(result.to_cal_signal().state, SignalState.BLOCK)
        self.assertEqual(result.reason_code, "USI_ALIGNMENT_BELOW_THRESHOLD")

    def test_missing_profile_routes_to_review(self):
        result = evaluate(self.profile(()), "item-1", (), candidate_attributes_complete=True)
        self.assertEqual(result.verdict, USIVerdict.REVIEW)
        self.assertEqual(result.to_cal_signal().state, SignalState.UNKNOWN)

    def test_incomplete_candidate_metadata_routes_to_review(self):
        profile = self.profile((StylePreference("p1", "u1", "minimal"),))
        result = evaluate(profile, "item-1", (), candidate_attributes_complete=False)
        self.assertEqual(result.verdict, USIVerdict.REVIEW)

    def test_cross_user_preferences_are_rejected(self):
        with self.assertRaises(ValueError):
            self.profile((StylePreference("p1", "u2", "minimal"),))

    def test_invalid_weight_is_rejected(self):
        with self.assertRaises(ValueError):
            StylePreference("p1", "u1", "minimal", 0.0)

    def test_invalid_threshold_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(self.profile((StylePreference("p1", "u1", "minimal"),)), "item-1", (), candidate_attributes_complete=True, minimum_alignment_score=1.2)


if __name__ == "__main__":
    unittest.main()
