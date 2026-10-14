import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "identity-intelligence"))

from catacaci import (  # noqa: E402
    ArbitrationRequest,
    DecisionSignal,
    DecisionVerdict,
    SignalKind,
    SignalState,
    arbitrate,
)


def signal(signal_id, kind, state=SignalState.PASS, confidence=None, required=True):
    return DecisionSignal(
        signal_id=signal_id,
        kind=kind,
        state=state,
        reason_code=f"TEST_{signal_id.upper()}",
        explanation=f"Test signal {signal_id}",
        required=required,
        confidence=confidence,
        source_version="test-1",
    )


def request(*signals, threshold=0.70):
    return ArbitrationRequest(
        request_id="request-1",
        candidate_id="candidate-1",
        signals=tuple(signals),
        minimum_fit_confidence=threshold,
    )


class CaTaCaCiCoreTests(unittest.TestCase):
    def test_show_requires_fit_confidence_and_all_required_gates(self):
        result = arbitrate(request(
            signal("safety", SignalKind.SAFETY),
            signal("npl", SignalKind.NPL_HARD_NEGATIVE),
            signal("fit", SignalKind.FIT_CONFIDENCE, confidence=0.82),
        ))
        self.assertEqual(result.verdict, DecisionVerdict.SHOW)
        self.assertTrue(result.may_display)

    def test_hard_npl_veto_beats_high_fit_confidence(self):
        result = arbitrate(request(
            signal("fit", SignalKind.FIT_CONFIDENCE, confidence=0.99),
            signal("npl", SignalKind.NPL_HARD_NEGATIVE, SignalState.BLOCK),
        ))
        self.assertEqual(result.verdict, DecisionVerdict.BLOCK)
        self.assertFalse(result.may_display)
        self.assertEqual(result.reasons[0].code, "TEST_NPL")

    def test_safety_block_beats_positive_signals(self):
        result = arbitrate(request(
            signal("fit", SignalKind.FIT_CONFIDENCE, confidence=1.0),
            signal("safety", SignalKind.SAFETY, SignalState.BLOCK),
        ))
        self.assertEqual(result.verdict, DecisionVerdict.BLOCK)

    def test_required_unknown_fails_to_review(self):
        result = arbitrate(request(
            signal("fit", SignalKind.FIT_CONFIDENCE, confidence=0.90),
            signal("identity", SignalKind.IDENTITY_ALIGNMENT, SignalState.UNKNOWN),
        ))
        self.assertEqual(result.verdict, DecisionVerdict.REVIEW)
        self.assertFalse(result.may_display)
        self.assertEqual(result.reasons[0].code, "REQUIRED_SIGNAL_UNKNOWN")

    def test_missing_fit_confidence_fails_to_review(self):
        result = arbitrate(request(signal("identity", SignalKind.IDENTITY_ALIGNMENT)))
        self.assertEqual(result.verdict, DecisionVerdict.REVIEW)
        self.assertEqual(result.reasons[0].code, "FIT_CONFIDENCE_MISSING")

    def test_fit_below_threshold_fails_to_review(self):
        result = arbitrate(request(
            signal("fit", SignalKind.FIT_CONFIDENCE, confidence=0.69),
        ))
        self.assertEqual(result.verdict, DecisionVerdict.REVIEW)

    def test_disagreeing_fit_signals_require_review_not_average(self):
        result = arbitrate(request(
            signal("fit-a", SignalKind.FIT_CONFIDENCE, confidence=0.95),
            signal("fit-b", SignalKind.FIT_CONFIDENCE, confidence=0.70),
        ))
        self.assertEqual(result.verdict, DecisionVerdict.REVIEW)
        self.assertEqual(result.reasons[0].code, "FIT_CONFIDENCE_DISAGREEMENT")

    def test_invalid_confidence_is_rejected(self):
        with self.assertRaises(ValueError):
            signal("fit", SignalKind.FIT_CONFIDENCE, confidence=1.01)

    def test_duplicate_signal_ids_are_rejected(self):
        s = signal("same", SignalKind.SAFETY)
        with self.assertRaises(ValueError):
            request(s, s)

    def test_result_is_deterministic_across_input_order(self):
        first = arbitrate(request(
            signal("fit", SignalKind.FIT_CONFIDENCE, confidence=0.90),
            signal("safety", SignalKind.SAFETY),
        ))
        second = arbitrate(request(
            signal("safety", SignalKind.SAFETY),
            signal("fit", SignalKind.FIT_CONFIDENCE, confidence=0.90),
        ))
        self.assertEqual(first, second)

    def test_soft_unknown_optional_signal_does_not_block(self):
        result = arbitrate(request(
            signal("fit", SignalKind.FIT_CONFIDENCE, confidence=0.90),
            signal("trend", SignalKind.OTHER, SignalState.UNKNOWN, required=False),
        ))
        self.assertEqual(result.verdict, DecisionVerdict.SHOW)


if __name__ == "__main__":
    unittest.main()
