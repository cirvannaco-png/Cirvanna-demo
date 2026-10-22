from __future__ import annotations

import asyncio
import sys
import unittest
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_ROOT = REPO_ROOT / "integration-staging" / "source-candidates" / "05-cfrp-v6.txt"
sys.path.insert(0, str(CANDIDATE_ROOT))

from src.actor.cfrp_actor import CFRPActor
from src.core.cfrp_instance import CFRPInstance
from src.core.epistemic_state import EpistemicState
from src.core.learning_prior import LearningPrior
from src.infrastructure.redis_client import RedisClient


class EpistemicStateTests(unittest.TestCase):
    def test_prior_path_imports_numpy_and_returns_a_new_state(self):
        original = EpistemicState(signal_id="purchase-fit")
        updated = original.reinforce(
            success=True,
            value=Decimal("0.5"),
            prior=LearningPrior(),
        )
        self.assertEqual(updated.signal_id, "purchase-fit")
        self.assertEqual(updated.reinforcement_count, 1)
        self.assertGreaterEqual(updated.confidence, Decimal("0.1"))
        self.assertIsNot(updated, original)

    def test_reinforcement_rejects_non_finite_or_out_of_range_values(self):
        state = EpistemicState(signal_id="purchase-fit")
        for invalid in (Decimal("-0.01"), Decimal("1.01"), Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(value=str(invalid)):
                with self.assertRaises(ValueError):
                    state.reinforce(True, invalid)

    def test_decay_respects_daily_cap_and_confidence_floor(self):
        state = EpistemicState(
            signal_id="purchase-fit",
            confidence=Decimal("0.8"),
            last_reinforced=1_000.0,
        )
        one_day = state.decay(1_000.0 + 86_400.0)
        self.assertLessEqual(state.confidence - one_day.confidence, Decimal("0.05") * state.confidence)
        very_old = state.decay(1_000.0 + 86_400.0 * 400)
        self.assertEqual(very_old.confidence, Decimal("0.1"))

    def test_metadata_is_not_shared_between_states(self):
        state = EpistemicState(
            signal_id="purchase-fit",
            learning_metadata={"nested": {"items": [1]}},
            context_features={"season": 0.5},
        )
        updated = state.reinforce(True, Decimal("0.5"))
        updated.learning_metadata["nested"]["items"].append(2)
        updated.context_features["season"] = 0.8
        self.assertEqual(state.learning_metadata["nested"]["items"], [1])
        self.assertEqual(state.context_features["season"], 0.5)


class CFRPActorTests(unittest.IsolatedAsyncioTestCase):
    async def test_message_errors_are_propagated_and_queue_accounting_recovers(self):
        actor = CFRPActor("actor-test")
        await actor.start()

        async def fail():
            raise ValueError("expected test failure")

        async def succeed():
            return "ok"

        print("stage 1: sending expected failure", flush=True)
        with self.assertRaisesRegex(ValueError, "expected test failure"):
            await asyncio.wait_for(actor.send(fail), timeout=2)
        print("stage 2: failure propagated", flush=True)
        self.assertEqual(await asyncio.wait_for(actor.send(succeed), timeout=2), "ok")
        print("stage 3: success propagated", flush=True)
        await asyncio.wait_for(actor.queue.join(), timeout=2)
        print("stage 4: queue joined", flush=True)
        await asyncio.wait_for(actor.stop(timeout_seconds=2), timeout=3)
        print("stage 5: actor stopped", flush=True)
        self.assertFalse(actor.running)

    async def test_stopped_actor_rejects_new_messages(self):
        actor = CFRPActor("actor-stop-test")
        await actor.start()
        await actor.stop()

        async def succeed():
            return True

        with self.assertRaisesRegex(RuntimeError, "not accepting"):
            await actor.send(succeed)


class CFRPInstanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        RedisClient._data.clear()

    async def test_shutdown_snapshot_is_restored_on_restart(self):
        first = CFRPInstance("snapshot-user")
        await first.start()
        await first.reinforce("purchase-fit", True, 0.5)
        await first.stop()

        second = CFRPInstance("snapshot-user")
        await second.start()
        restored = second.signal_states["purchase-fit"]
        self.assertEqual(restored.reinforcement_count, 1)
        self.assertEqual(restored.confidence, first.signal_states["purchase-fit"].confidence)
        await second.stop()

    async def test_invalid_reinforcement_does_not_mutate_state(self):
        instance = CFRPInstance("validation-user")
        await instance.start()
        with self.assertRaisesRegex(ValueError, "value must be a finite number"):
            await instance.reinforce("purchase-fit", True, float("nan"))
        self.assertNotIn("purchase-fit", instance.signal_states)
        await instance.stop()


if __name__ == "__main__":
    unittest.main()
