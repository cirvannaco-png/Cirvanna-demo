"""
CFRPInstance – Single authoritative CFRP instance per user.
"""
import asyncio
import time
import logging
from decimal import Decimal
from typing import Dict, List, Optional

from src.actor.cfrp_actor import CFRPActor
from src.core.epistemic_state import EpistemicState
from src.core.reinforcement_log import CFRPReinforcementLog
from src.infrastructure.redis_client import RedisClient

class CFRPInstance:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.actor = CFRPActor(user_id)
        self.signal_states: Dict[str, EpistemicState] = {}
        self.reinforcement_log = CFRPReinforcementLog(user_id)
        self.running = False
        self.maintenance_task: Optional[asyncio.Task] = None
        self.shutdown_event = asyncio.Event()
        self.redis = RedisClient.get_instance()

    async def start(self):
        if self.running:
            return
        await self.actor.start()
        await self._load_state()
        self.running = True
        self.maintenance_task = asyncio.create_task(self._maintenance_loop())

    async def stop(self):
        if not self.running:
            return
        self.running = False
        self.shutdown_event.set()
        if self.maintenance_task:
            self.maintenance_task.cancel()
            try:
                await self.maintenance_task
            except asyncio.CancelledError:
                pass
        await self.actor.stop()
        await self._flush_state()

    async def _load_state(self):
        # In production: load from Redis snapshot + replay events
        snapshot = await self.redis.get(f"snapshot:{self.user_id}")
        if snapshot:
            # Reconstruct signal_states from snapshot
            pass

    async def _flush_state(self):
        if self.reinforcement_log.needs_snapshot():
            snapshot = self.reinforcement_log.create_snapshot(self.signal_states)
            await self.redis.set(f"snapshot:{self.user_id}", snapshot)

    async def _maintenance_loop(self):
        while not self.shutdown_event.is_set():
            try:
                await asyncio.wait(
                    [asyncio.create_task(asyncio.sleep(60)),
                     asyncio.create_task(self.shutdown_event.wait())],
                    return_when=asyncio.FIRST_COMPLETED
                )
                if self.shutdown_event.is_set():
                    break
                await self._perform_maintenance()
            except asyncio.CancelledError:
                break

    async def _perform_maintenance(self):
        for signal_id in list(self.signal_states.keys()):
            await self.actor.send(lambda: self._apply_decay(signal_id))
        if self.reinforcement_log.needs_snapshot():
            snapshot = self.reinforcement_log.create_snapshot(self.signal_states)
            await self.redis.set(f"snapshot:{self.user_id}", snapshot)

    async def _apply_decay(self, signal_id: str):
        if signal_id in self.signal_states:
            state = self.signal_states[signal_id]
            self.signal_states[signal_id] = state.decay(time.time())

    async def reinforce(self, signal_id: str, success: bool, value: float = 1.0) -> Dict:
        return await self.actor.send(lambda: self._reinforce_internal(signal_id, success, value))

    async def _reinforce_internal(self, signal_id: str, success: bool, value: float) -> Dict:
        if signal_id not in self.signal_states:
            self.signal_states[signal_id] = EpistemicState(signal_id=signal_id)
        old_state = self.signal_states[signal_id]
        new_state = old_state.reinforce(success, Decimal(str(value)))
        self.signal_states[signal_id] = new_state
        self.reinforcement_log.append(signal_id, success, value)
        return {
            'success': True,
            'old_confidence': float(old_state.confidence),
            'new_confidence': float(new_state.confidence),
            'reinforcement_count': new_state.reinforcement_count
        }

    async def get_advice(self, signal_ids: List[str]) -> Dict:
        return await self.actor.send(lambda: self._get_advice_internal(signal_ids))

    async def _get_advice_internal(self, signal_ids: List[str]) -> Dict:
        advisories = {}
        for signal_id in signal_ids:
            if signal_id not in self.signal_states:
                self.signal_states[signal_id] = EpistemicState(signal_id=signal_id)
            state = self.signal_states[signal_id]
            state = state.decay(time.time())
            self.signal_states[signal_id] = state
            advisory = self._generate_advisory(state)
            advisories[signal_id] = advisory
        return {'advisories': advisories}

    def _generate_advisory(self, state: EpistemicState) -> Dict:
        confidence_weight = float(state.confidence) - 0.5
        days_since = (time.time() - state.last_reinforced) / 86400
        recency_bonus = max(0, 0.1 * (1 - days_since / 7))
        data_bonus = min(0.1, state.reinforcement_count / 100)
        total_adjustment = confidence_weight + recency_bonus + data_bonus
        return {
            'confidence_weight': confidence_weight,
            'recency_bonus': recency_bonus,
            'data_bonus': data_bonus,
            'total_cfrp_adjustment': total_adjustment,
            'epistemic_notes': self._get_epistemic_notes(state)
        }

    def _get_epistemic_notes(self, state: EpistemicState) -> List[str]:
        notes = []
        if state.reinforcement_count < 10:
            notes.append("Limited data – high uncertainty")
        elif state.reinforcement_count > 100:
            notes.append("Well‑established signal")
        if state.confidence < Decimal('0.3'):
            notes.append("Low confidence – experimental")
        elif state.confidence > Decimal('0.8'):
            notes.append("High confidence – reliable")
        return notes
