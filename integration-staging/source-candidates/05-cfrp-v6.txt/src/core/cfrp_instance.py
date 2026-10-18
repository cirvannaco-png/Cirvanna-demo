"""
CFRPInstance – Single authoritative CFRP instance per user.

Persistence clients in this candidate are in-memory simulations. Snapshot
reconstruction is implemented for contract testing, but durable storage and
event replay remain unavailable until real adapters are integrated.
"""
import asyncio
import math
import time
from decimal import Decimal
from typing import Dict, List, Optional
import logging

from src.actor.cfrp_actor import CFRPActor
from src.core.epistemic_state import EpistemicState
from src.core.reinforcement_log import CFRPReinforcementLog
from src.infrastructure.redis_client import RedisClient


class CFRPInstance:
    def __init__(self, user_id: str):
        if not isinstance(user_id, str) or not user_id.strip() or len(user_id) > 128:
            raise ValueError("user_id must contain 1-128 non-whitespace characters")
        self.user_id = user_id.strip()
        self.actor = CFRPActor(self.user_id)
        self.signal_states: Dict[str, EpistemicState] = {}
        self.reinforcement_log = CFRPReinforcementLog(self.user_id)
        self.running = False
        self.maintenance_task: Optional[asyncio.Task] = None
        self.shutdown_event = asyncio.Event()
        self.redis = RedisClient.get_instance()

    async def start(self):
        if self.running:
            return
        self.shutdown_event.clear()
        await self.actor.start()
        try:
            await self._load_state()
        except Exception:
            await self.actor.stop()
            raise
        self.running = True
        self.maintenance_task = asyncio.create_task(
            self._maintenance_loop(), name=f"cfrp-maintenance-{self.user_id}"
        )

    async def stop(self):
        if not self.running and not self.actor.running:
            return
        self.running = False
        self.shutdown_event.set()
        if self.maintenance_task:
            await self.maintenance_task
            self.maintenance_task = None
        await self.actor.stop()
        # Always flush at shutdown; the snapshot interval is for periodic saves.
        await self._flush_state(force=True)

    async def _load_state(self):
        snapshot = await self.redis.get(f"snapshot:{self.user_id}")
        if snapshot is None:
            return
        if not isinstance(snapshot, dict) or snapshot.get("user_id") != self.user_id:
            raise ValueError("Snapshot is malformed or belongs to another user")
        raw_states = snapshot.get("signal_states")
        if not isinstance(raw_states, dict):
            raise ValueError("Snapshot is missing signal_states")
        restored: Dict[str, EpistemicState] = {}
        for signal_id, raw in raw_states.items():
            if not isinstance(signal_id, str) or not isinstance(raw, dict):
                raise ValueError("Snapshot contains a malformed signal state")
            try:
                restored[signal_id] = EpistemicState(
                    signal_id=signal_id,
                    confidence=Decimal(str(raw["confidence"])),
                    rolling_baseline=Decimal(str(raw["rolling_baseline"])),
                    last_reinforced=float(raw["last_reinforced"]),
                    reinforcement_count=int(raw["reinforcement_count"]),
                )
            except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
                raise ValueError(f"Snapshot state for {signal_id!r} is invalid") from exc
        self.signal_states = restored

    async def _flush_state(self, force: bool = False):
        if force or self.reinforcement_log.needs_snapshot():
            snapshot = self.reinforcement_log.create_snapshot(self.signal_states)
            await self.redis.set(f"snapshot:{self.user_id}", snapshot)

    async def _maintenance_loop(self):
        try:
            while not self.shutdown_event.is_set():
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=60)
                except asyncio.TimeoutError:
                    if not self.shutdown_event.is_set():
                        await self._perform_maintenance()
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("CFRP maintenance failed for user %s", self.user_id)
            # A background failure is observable in logs; it does not silently
            # spawn overlapping maintenance tasks.
            self.shutdown_event.set()

    async def _perform_maintenance(self):
        for signal_id in list(self.signal_states.keys()):
            await self.actor.send(lambda sid=signal_id: self._apply_decay(sid))
        await self._flush_state()

    async def _apply_decay(self, signal_id: str):
        if signal_id in self.signal_states:
            state = self.signal_states[signal_id]
            self.signal_states[signal_id] = state.decay(time.time())

    async def reinforce(self, signal_id: str, success: bool, value: float = 1.0) -> Dict:
        return await self.actor.send(lambda: self._reinforce_internal(signal_id, success, value))

    async def _reinforce_internal(self, signal_id: str, success: bool, value: float) -> Dict:
        if not isinstance(signal_id, str) or not signal_id.strip() or len(signal_id) > 128:
            raise ValueError("signal_id must contain 1-128 non-whitespace characters")
        if not isinstance(success, bool):
            raise ValueError("success must be a boolean")
        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("value must be a finite number in [0, 1]") from exc
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("value must be a finite number in [0, 1]")
        signal_id = signal_id.strip()
        if signal_id not in self.signal_states:
            self.signal_states[signal_id] = EpistemicState(signal_id=signal_id)
        old_state = self.signal_states[signal_id]
        new_state = old_state.reinforce(success, Decimal(str(value)))
        self.signal_states[signal_id] = new_state
        self.reinforcement_log.append(signal_id, success, value)
        return {
            "success": True,
            "old_confidence": float(old_state.confidence),
            "new_confidence": float(new_state.confidence),
            "reinforcement_count": new_state.reinforcement_count,
        }

    async def get_advice(self, signal_ids: List[str]) -> Dict:
        return await self.actor.send(lambda: self._get_advice_internal(signal_ids))

    async def _get_advice_internal(self, signal_ids: List[str]) -> Dict:
        if not isinstance(signal_ids, list) or len(signal_ids) > 100:
            raise ValueError("signal_ids must be a list containing at most 100 entries")
        if any(not isinstance(sid, str) or not sid.strip() or len(sid) > 128 for sid in signal_ids):
            raise ValueError("Each signal_id must contain 1-128 non-whitespace characters")
        advisories = {}
        for raw_signal_id in signal_ids:
            signal_id = raw_signal_id.strip()
            if signal_id not in self.signal_states:
                self.signal_states[signal_id] = EpistemicState(signal_id=signal_id)
            state = self.signal_states[signal_id].decay(time.time())
            self.signal_states[signal_id] = state
            advisories[signal_id] = self._generate_advisory(state)
        return {"advisories": advisories}

    def _generate_advisory(self, state: EpistemicState) -> Dict:
        confidence_weight = float(state.confidence) - 0.5
        days_since = (time.time() - state.last_reinforced) / 86400
        recency_bonus = max(0, 0.1 * (1 - days_since / 7))
        data_bonus = min(0.1, state.reinforcement_count / 100)
        total_adjustment = confidence_weight + recency_bonus + data_bonus
        return {
            "confidence_weight": confidence_weight,
            "recency_bonus": recency_bonus,
            "data_bonus": data_bonus,
            "total_cfrp_adjustment": total_adjustment,
            "epistemic_notes": self._get_epistemic_notes(state),
        }

    def _get_epistemic_notes(self, state: EpistemicState) -> List[str]:
        notes = []
        if state.reinforcement_count < 10:
            notes.append("Limited data – high uncertainty")
        elif state.reinforcement_count > 100:
            notes.append("Well-established signal")
        if state.confidence < Decimal("0.3"):
            notes.append("Low confidence – experimental")
        elif state.confidence > Decimal("0.8"):
            notes.append("High confidence – reliable")
        return notes
