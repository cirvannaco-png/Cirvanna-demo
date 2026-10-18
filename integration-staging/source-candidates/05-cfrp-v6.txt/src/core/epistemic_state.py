"""
EpistemicState – Confidence state with reinforcement and decay.

This remains a staged candidate. Its persistence adapters are simulations and
must not be treated as durable production infrastructure.
"""
from __future__ import annotations

import copy
import math
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

import numpy as np

from src.core.epistemic_context import EpistemicContext
from src.core.epistemic_invariants import EpistemicInvariants
from src.core.learning_prior import LearningPrior


@dataclass
class EpistemicState:
    signal_id: str
    confidence: Decimal = Decimal("0.5")
    rolling_baseline: Decimal = Decimal("0.5")
    last_reinforced: float = field(default_factory=time.time)
    reinforcement_count: int = 0
    baseline_window: int = 100
    learning_metadata: Dict[str, Any] = field(default_factory=dict)
    context_features: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.signal_id, str) or not self.signal_id.strip() or len(self.signal_id) > 128:
            raise ValueError("signal_id must contain 1-128 non-whitespace characters")
        self.signal_id = self.signal_id.strip()
        for name in ("confidence", "rolling_baseline"):
            value = getattr(self, name)
            try:
                value = value if isinstance(value, Decimal) else Decimal(str(value))
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"{name} must be a finite decimal") from exc
            if not value.is_finite() or not Decimal("0") <= value <= Decimal("1"):
                raise ValueError(f"{name} must be in [0, 1]")
            setattr(self, name, value)
        if not math.isfinite(float(self.last_reinforced)):
            raise ValueError("last_reinforced must be finite")
        if self.reinforcement_count < 0:
            raise ValueError("reinforcement_count must be non-negative")
        if self.baseline_window < 1:
            raise ValueError("baseline_window must be positive")
        if not isinstance(self.learning_metadata, dict) or not isinstance(self.context_features, dict):
            raise ValueError("learning_metadata and context_features must be dictionaries")
        self.learning_metadata = copy.deepcopy(self.learning_metadata)
        self.context_features = copy.deepcopy(self.context_features)
        for key, value in self.context_features.items():
            if not isinstance(key, str) or not math.isfinite(float(value)):
                raise ValueError("context_features must contain finite numeric values keyed by strings")

    def reinforce(
        self,
        success: bool,
        value: Decimal,
        prior: Optional[LearningPrior] = None,
        context: Optional[EpistemicContext] = None,
    ) -> "EpistemicState":
        if not isinstance(success, bool):
            raise ValueError("success must be a boolean")
        try:
            value = value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("reinforcement value must be a finite decimal in [0, 1]") from exc
        if not value.is_finite() or not Decimal("0") <= value <= Decimal("1"):
            raise ValueError("reinforcement value must be a finite decimal in [0, 1]")

        success_value = Decimal("1") if success else Decimal("0")
        if self.reinforcement_count < self.baseline_window:
            weight = Decimal("1") / Decimal(str(self.reinforcement_count + 1))
            new_baseline = self.rolling_baseline * (Decimal("1") - weight) + success_value * weight
        else:
            new_baseline = self.rolling_baseline * Decimal("0.99") + success_value * Decimal("0.01")

        if context:
            rates = context.compute_adaptive_rates()
            learning_rate = Decimal(str(rates["learning_rate"]))
            if not learning_rate.is_finite():
                raise ValueError("context learning_rate must be finite")
            learning_rate = max(Decimal("0"), min(EpistemicInvariants.MAX_CONFIDENCE_JUMP, learning_rate))
        else:
            learning_rate = Decimal("0.1")

        learning_metadata = copy.deepcopy(self.learning_metadata)
        if prior:
            user_posterior = np.array([float(self.confidence)], dtype=float)
            posterior, metadata = LearningPrior.compute_posterior(
                user_posterior=user_posterior,
                segment_prior=prior.segment_prior,
                global_prior=prior.global_prior,
            )
            if metadata.get("has_conflict", False):
                learning_rate *= Decimal("0.5")
            base_confidence = Decimal(str(float(posterior[0])))
            learning_metadata = copy.deepcopy(metadata)
        else:
            base_confidence = self.confidence

        if success:
            if success_value > new_baseline:
                increase = learning_rate * (Decimal("1") - base_confidence)
                new_confidence = base_confidence + increase * value
            else:
                new_confidence = base_confidence
        else:
            decrease = learning_rate * base_confidence
            new_confidence = base_confidence - decrease * value

        # Apply the same per-update movement bounds used by the invariant checker.
        max_increase = EpistemicInvariants.MAX_CONFIDENCE_JUMP * (Decimal("1") - self.confidence)
        max_decrease = EpistemicInvariants.MAX_CONFIDENCE_JUMP * self.confidence
        lower_bound = max(
            EpistemicInvariants.MIN_CONFIDENCE,
            self.confidence - max_decrease,
        )
        upper_bound = min(Decimal("1"), self.confidence + max_increase)
        new_confidence = max(lower_bound, min(upper_bound, new_confidence))

        EpistemicInvariants.validate_confidence_change(
            old=self.confidence,
            new=new_confidence,
            success=success,
        )

        return EpistemicState(
            signal_id=self.signal_id,
            confidence=new_confidence,
            rolling_baseline=new_baseline,
            last_reinforced=time.time(),
            reinforcement_count=self.reinforcement_count + 1,
            baseline_window=self.baseline_window,
            learning_metadata=learning_metadata,
            context_features=copy.deepcopy(self.context_features),
        )

    def decay(
        self,
        current_time: float,
        context: Optional[EpistemicContext] = None,
    ) -> "EpistemicState":
        if not math.isfinite(float(current_time)):
            raise ValueError("current_time must be finite")
        days_elapsed = Decimal(str((float(current_time) - self.last_reinforced) / 86400))
        if days_elapsed <= Decimal("0"):
            return self

        if context:
            rates = context.compute_adaptive_rates()
            decay_rate = Decimal(str(rates["confidence_decay"]))
            if not decay_rate.is_finite():
                raise ValueError("context confidence_decay must be finite")
            decay_rate = max(Decimal("0"), min(Decimal("1"), decay_rate))
        else:
            decay_rate = Decimal("0.05")

        halflife_days = 30 / (1 + float(decay_rate) * 10)
        decay_factor = Decimal(str(math.exp(-float(days_elapsed / Decimal(str(halflife_days))))))
        exponential_confidence = self.confidence * decay_factor

        # Bound the exponential target to the invariant's per-day limit.
        allowed_fraction = min(
            Decimal("1"),
            EpistemicInvariants.MAX_DAILY_DECAY * days_elapsed,
        )
        minimum_allowed = self.confidence * (Decimal("1") - allowed_fraction)
        new_confidence = max(
            exponential_confidence,
            minimum_allowed,
            EpistemicInvariants.MIN_CONFIDENCE,
        )

        EpistemicInvariants.validate_decay(
            old=self.confidence,
            new=new_confidence,
            days_elapsed=days_elapsed,
        )

        return EpistemicState(
            signal_id=self.signal_id,
            confidence=new_confidence,
            rolling_baseline=self.rolling_baseline,
            last_reinforced=self.last_reinforced,
            reinforcement_count=self.reinforcement_count,
            baseline_window=self.baseline_window,
            learning_metadata=copy.deepcopy(self.learning_metadata),
            context_features=copy.deepcopy(self.context_features),
        )
