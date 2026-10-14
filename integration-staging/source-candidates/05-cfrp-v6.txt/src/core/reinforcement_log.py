"""
CFRPReinforcementLog – Event-sourced log (non-enterprise).
"""
import time
import uuid
from typing import Dict, List, Optional

class CFRPReinforcementLog:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.events: List[Dict] = []
        self.last_snapshot_time = time.time()
        self.snapshot_interval = 300

    def append(self, signal_id: str, success: bool, value: float):
        event = {
            'timestamp': time.time(),
            'signal_id': signal_id,
            'success': success,
            'value': value,
            'event_id': str(uuid.uuid4())
        }
        self.events.append(event)

    def get_since(self, since_timestamp: float) -> List[Dict]:
        return [e for e in self.events if e['timestamp'] > since_timestamp]

    def needs_snapshot(self) -> bool:
        return time.time() - self.last_snapshot_time > self.snapshot_interval

    def create_snapshot(self, signal_states: Dict) -> Dict:
        self.last_snapshot_time = time.time()
        return {
            'timestamp': self.last_snapshot_time,
            'user_id': self.user_id,
            'signal_states': {
                sid: {
                    'confidence': float(s.confidence),
                    'rolling_baseline': float(s.rolling_baseline),
                    'last_reinforced': s.last_reinforced,
                    'reinforcement_count': s.reinforcement_count
                } for sid, s in signal_states.items()
            },
            'last_event_id': self.events[-1]['event_id'] if self.events else None
        }
