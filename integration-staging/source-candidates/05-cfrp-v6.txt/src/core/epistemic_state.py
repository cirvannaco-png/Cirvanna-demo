"""
EpistemicState – Confidence state with reinforcement and decay.
"""
import time
import math
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

from src.core.epistemic_invariants import EpistemicInvariants
from src.core.learning_prior import LearningPrior
from src.core.epistemic_context import EpistemicContext

@dataclass
class EpistemicState:
    signal_id: str
    confidence: Decimal = Decimal('0.5')
    rolling_baseline: Decimal = Decimal('0.5')
    last_reinforced: float = field(default_factory=time.time)
    reinforcement_count: int = 0
    baseline_window: int = 100
    learning_metadata: Dict[str, Any] = field(default_factory=dict)
    context_features: Dict[str, float] = field(default_factory=dict)

    def reinforce(self, success: bool, value: Decimal,
                  prior: Optional[LearningPrior] = None,
                  context: Optional[EpistemicContext] = None) -> 'EpistemicState':
        success_value = Decimal('1') if success else Decimal('0')

        if self.reinforcement_count < self.baseline_window:
            weight = Decimal('1') / Decimal(str(self.reinforcement_count + 1))
            new_baseline = self.rolling_baseline * (Decimal('1') - weight) + success_value * weight
        else:
            new_baseline = self.rolling_baseline * Decimal('0.99') + success_value * Decimal('0.01')

        if context:
            rates = context.compute_adaptive_rates()
            learning_rate = Decimal(str(rates['learning_rate']))
        else:
            learning_rate = Decimal('0.1')

        if prior:
            user_posterior = np.array([float(self.confidence)])
            posterior, metadata = LearningPrior.compute_posterior(
                user_posterior=user_posterior,
                segment_prior=prior.segment_prior,
                global_prior=prior.global_prior
            )
            if metadata.get('has_conflict', False):
                learning_rate *= Decimal('0.5')
            base_confidence = Decimal(str(posterior[0]))
            self.learning_metadata = metadata
        else:
            base_confidence = self.confidence

        if success:
            if success_value > new_baseline:
                increase = learning_rate * (Decimal('1') - base_confidence)
                new_confidence = base_confidence + increase * value
            else:
                new_confidence = base_confidence
        else:
            decrease = learning_rate * base_confidence
            new_confidence = base_confidence - decrease * value

        new_confidence = max(Decimal('0'), min(Decimal('1'), new_confidence))

        EpistemicInvariants.validate_confidence_change(
            old=self.confidence,
            new=new_confidence,
            success=success
        )

        return EpistemicState(
            signal_id=self.signal_id,
            confidence=new_confidence,
            rolling_baseline=new_baseline,
            last_reinforced=time.time(),
            reinforcement_count=self.reinforcement_count + 1,
            learning_metadata=self.learning_metadata,
            context_features=self.context_features
        )

    def decay(self, current_time: float, context: Optional[EpistemicContext] = None) -> 'EpistemicState':
        days_elapsed = Decimal(str((current_time - self.last_reinforced) / 86400))

        if days_elapsed <= Decimal('0'):
            return self

        if context:
            rates = context.compute_adaptive_rates()
            decay_rate = Decimal(str(rates['confidence_decay']))
        else:
            decay_rate = Decimal('0.05')

        halflife_days = 30 / (1 + float(decay_rate) * 10)
        decay_factor = Decimal(str(math.exp(-float(days_elapsed / Decimal(str(halflife_days))))))

        new_confidence = self.confidence * decay_factor

        EpistemicInvariants.validate_decay(
            old=self.confidence,
            new=new_confidence,
            days_elapsed=days_elapsed
        )

        return EpistemicState(
            signal_id=self.signal_id,
            confidence=new_confidence,
            rolling_baseline=self.rolling_baseline,
            last_reinforced=self.last_reinforced,
            reinforcement_count=self.reinforcement_count,
            learning_metadata=self.learning_metadata,
            context_features=self.context_features
        )
