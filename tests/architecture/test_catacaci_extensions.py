from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "identity-intelligence"))

from catacaci import (  # noqa: E402
    ArbitrationRequest, DecisionSignal, SignalKind, SignalState, arbitrate,
)
from catacaci.cam import record_counterfactual  # noqa: E402
from catacaci.cil import CohortObservation, aggregate_cohort  # noqa: E402
from catacaci.tal import TemporalEvent, TemporalState, append_event, latest_values  # noqa: E402
from catacaci.vsl import ValueChangeProposal, ValueDimension, ValueProfile, approve_change  # noqa: E402


class TALTests(unittest.TestCase):
    def event(self, event_id, value, at="2026-10-15T09:00:00Z", consent=True):
        return TemporalEvent(event_id, "u1", "style", value, at, "source-v1", consent)

    def test_append_is_idempotent_and_versions_state(self):
        state = append_event(TemporalState(), self.event("e1", "minimal"))
        self.assertEqual(state.version, 1)
        self.assertIs(append_event(state, self.event("e1", "minimal")), state)
        self.assertEqual(state.version, 1)

    def test_reused_event_id_with_changed_payload_is_rejected(self):
        state = append_event(TemporalState(), self.event("e1", "minimal"))
        with self.assertRaises(ValueError):
            append_event(state, self.event("e1", "maximalist"))

    def test_no_consent_means_no_recording(self):
        with self.assertRaises(PermissionError):
            append_event(TemporalState(), self.event("e1", "minimal", consent=False))

    def test_latest_value_is_temporal_and_user_scoped(self):
        state = append_event(TemporalState(), self.event("e1", "minimal", "2026-10-14T09:00:00Z"))
        state = append_event(state, self.event("e2", "classic", "2026-10-15T09:00:00Z"))
        other = TemporalEvent("e3", "u2", "style", "sporty", "2026-10-15T10:00:00Z", "source-v1", True)
        state = append_event(state, other)
        self.assertEqual(latest_values(state, "u1", "2026-10-15T11:00:00Z"), {"style": "classic"})


class CAMTests(unittest.TestCase):
    def result(self, request_id, candidate_id, state):
        signal = DecisionSignal("s1", SignalKind.SAFETY, state, "R1", "test", source_version="v1")
        signals = (signal,)
        req = ArbitrationRequest(request_id, candidate_id, signals, required_kinds=(SignalKind.SAFETY,))
        return arbitrate(req)

    def test_counterfactual_records_scenario_not_causality(self):
        actual = self.result("req1", "item1", SignalState.PASS)
        simulated = self.result("req1", "item1", SignalState.BLOCK)
        record = record_counterfactual("audit1", actual, simulated, ("s1",), "replay-v1", "2026-10-15T10:00:00Z")
        self.assertEqual(record.observed_verdict, "show")
        self.assertEqual(record.simulated_verdict, "block")
        self.assertEqual(record.interpretation, "counterfactual_scenario_not_observed_causality")

    def test_different_candidate_is_rejected(self):
        actual = self.result("req1", "item1", SignalState.PASS)
        simulated = self.result("req1", "item2", SignalState.BLOCK)
        with self.assertRaises(ValueError):
            record_counterfactual("audit1", actual, simulated, ("s1",), "replay-v1", "2026-10-15T10:00:00Z")


class CILTests(unittest.TestCase):
    def observations(self, count):
        return tuple(CohortObservation(f"e{i}", f"p{i}", "dress-fit", i % 2 == 0) for i in range(count))

    def test_small_cohort_is_suppressed(self):
        result = aggregate_cohort(self.observations(2), minimum_contributors=3)
        self.assertTrue(result.suppressed)
        self.assertIsNone(result.success_rate)

    def test_large_enough_cohort_returns_aggregate_only(self):
        result = aggregate_cohort(self.observations(4), minimum_contributors=3)
        self.assertFalse(result.suppressed)
        self.assertEqual(result.contributor_count, 4)
        self.assertEqual(result.success_rate, 0.5)

    def test_duplicate_contributor_cannot_be_double_counted(self):
        observations = (
            CohortObservation("e1", "p1", "dress-fit", True),
            CohortObservation("e2", "p1", "dress-fit", False),
        )
        with self.assertRaises(ValueError):
            aggregate_cohort(observations, minimum_contributors=2)


class VSLTests(unittest.TestCase):
    def order(self):
        return (
            ValueDimension.SAFETY,
            ValueDimension.LEGAL_ELIGIBILITY,
            ValueDimension.USER_HARD_CONSTRAINT,
            ValueDimension.NPL_HARD_NEGATIVE,
            ValueDimension.CULTURAL_REQUIREMENT,
            ValueDimension.CONTEXT_ELIGIBILITY,
            ValueDimension.IDENTITY_ALIGNMENT,
            ValueDimension.FIT_CONFIDENCE,
            ValueDimension.OTHER,
        )

    def test_approved_change_requires_separate_approver_and_version_match(self):
        current = ValueProfile("1.0", self.order())
        proposed_order = (
            ValueDimension.SAFETY,
            ValueDimension.LEGAL_ELIGIBILITY,
            ValueDimension.USER_HARD_CONSTRAINT,
            ValueDimension.NPL_HARD_NEGATIVE,
            ValueDimension.CULTURAL_REQUIREMENT,
            ValueDimension.IDENTITY_ALIGNMENT,
            ValueDimension.CONTEXT_ELIGIBILITY,
            ValueDimension.FIT_CONFIDENCE,
            ValueDimension.OTHER,
        )
        proposal = ValueChangeProposal("p1", "1.0", "1.1", proposed_order, "Improve explanation priority", "author")
        approved = approve_change(current, proposal, approver_id="reviewer", approval_event_id="approval-1")
        self.assertEqual(approved.version, "1.1")
        self.assertEqual(approved.approved_by, "reviewer")
        self.assertEqual(current.version, "1.0")

    def test_proposer_cannot_approve_own_change(self):
        current = ValueProfile("1.0", self.order())
        proposal = ValueChangeProposal("p1", "1.0", "1.1", self.order(), "Rationale", "author")
        with self.assertRaises(PermissionError):
            approve_change(current, proposal, approver_id="author", approval_event_id="approval-1")

    def test_safety_and_legal_precedence_are_invariant(self):
        bad_order = tuple(reversed(self.order()))
        with self.assertRaises(ValueError):
            ValueProfile("1.0", bad_order)


if __name__ == "__main__":
    unittest.main()
