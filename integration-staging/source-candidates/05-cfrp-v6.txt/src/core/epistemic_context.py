"""
EpistemicContext – Adaptive context for CFRP.
"""
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

@dataclass
class EpistemicContext:
    cultural_sensitivity: float = 0.0
    wardrobe_stability: float = 0.5
    exploration_budget: float = 0.2
    signal_volatility: float = 0.0
    last_context_update: float = field(default_factory=time.time)

    @classmethod
    async def from_user_id(cls, user_id: str, redis) -> 'EpistemicContext':
        key = f"context:{user_id}"
        cached = await redis.get(key)
        if cached:
            return EpistemicContext(**cached)
        return EpistemicContext()

    async def save(self, user_id: str, redis):
        key = f"context:{user_id}"
        await redis.set(key, {
            'cultural_sensitivity': self.cultural_sensitivity,
            'wardrobe_stability': self.wardrobe_stability,
            'exploration_budget': self.exploration_budget,
            'signal_volatility': self.signal_volatility,
            'last_context_update': self.last_context_update
        }, ttl=86400)

    def compute_adaptive_rates(self) -> Dict[str, float]:
        base_lr = 0.1
        learning_rate = base_lr * (1 - self.cultural_sensitivity * 0.5)
        base_decay = 0.05
        confidence_decay = base_decay * (1 - self.wardrobe_stability * 0.3)
        exploration_boost = self.exploration_budget * 0.2
        return {
            'learning_rate': max(0.01, min(0.3, learning_rate)),
            'confidence_decay': max(0.01, min(0.1, confidence_decay)),
            'exploration_boost': exploration_boost,
            'volatility_multiplier': 1 + self.signal_volatility * 0.5
        }
