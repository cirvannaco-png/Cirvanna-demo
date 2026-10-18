"""
EpistemicInvariants – Mathematical guarantees for CFRP's reasoning.
"""
from decimal import Decimal
from typing import List


class EpistemicInvariantViolation(ValueError):
    """Raised when an epistemic invariant is violated."""


class EpistemicInvariants:
    MAX_CONFIDENCE_JUMP = Decimal("0.3")
    MAX_DAILY_DECAY = Decimal("0.05")
    MIN_CONFIDENCE = Decimal("0.1")
    MAX_CFRP_INFLUENCE = Decimal("0.3")
    MIN_USI_AUTONOMY = Decimal("0.7")
    MAX_DOMINANCE_RATIO = Decimal("10.0")

    @classmethod
    def validate_confidence_change(cls, old: Decimal, new: Decimal, success: bool) -> None:
        if not old.is_finite() or not new.is_finite():
            raise EpistemicInvariantViolation("Confidence values must be finite")
        if not cls.MIN_CONFIDENCE <= old <= Decimal("1"):
            raise EpistemicInvariantViolation(f"Old confidence must be in [{cls.MIN_CONFIDENCE}, 1]")
        if not cls.MIN_CONFIDENCE <= new <= Decimal("1"):
            raise EpistemicInvariantViolation(f"New confidence must be in [{cls.MIN_CONFIDENCE}, 1]")
        if not isinstance(success, bool):
            raise EpistemicInvariantViolation("success must be a boolean")
        delta = new - old
        if success:
            max_increase = cls.MAX_CONFIDENCE_JUMP * (Decimal("1") - old)
            if delta > max_increase:
                raise EpistemicInvariantViolation(
                    f"Confidence increase {delta} > allowed {max_increase}"
                )
        else:
            max_decrease = cls.MAX_CONFIDENCE_JUMP * old
            if delta < -max_decrease:
                raise EpistemicInvariantViolation(
                    f"Confidence decrease {-delta} > allowed {max_decrease}"
                )

    @classmethod
    def validate_decay(cls, old: Decimal, new: Decimal, days_elapsed: Decimal) -> None:
        if not old.is_finite() or not new.is_finite() or not days_elapsed.is_finite():
            raise EpistemicInvariantViolation("Decay inputs must be finite")
        if not cls.MIN_CONFIDENCE <= old <= Decimal("1"):
            raise EpistemicInvariantViolation(f"Old confidence must be in [{cls.MIN_CONFIDENCE}, 1]")
        if not cls.MIN_CONFIDENCE <= new <= old:
            raise EpistemicInvariantViolation(
                f"Decayed confidence must remain in [{cls.MIN_CONFIDENCE}, old confidence]"
            )
        if days_elapsed <= Decimal("0"):
            raise EpistemicInvariantViolation("days_elapsed must be positive for decay validation")
        max_decay = cls.MAX_DAILY_DECAY * days_elapsed * old
        actual_decay = old - new
        if actual_decay > max_decay:
            raise EpistemicInvariantViolation(
                f"Decay {actual_decay} > allowed {max_decay}"
            )

    @classmethod
    def validate_cfrp_influence(cls, usi_weight: Decimal, cfrp_adjustment: Decimal) -> Decimal:
        if not usi_weight.is_finite() or not cfrp_adjustment.is_finite():
            raise EpistemicInvariantViolation("CFRP influence inputs must be finite")
        bounded = max(-cls.MAX_CFRP_INFLUENCE, min(cls.MAX_CFRP_INFLUENCE, cfrp_adjustment))
        final = usi_weight * (Decimal("1") + bounded)
        min_weight = usi_weight * cls.MIN_USI_AUTONOMY
        if final < min_weight:
            return min_weight
        return final

    @classmethod
    def validate_no_dominance(cls, weights: List[Decimal]) -> None:
        if any(not weight.is_finite() for weight in weights):
            raise EpistemicInvariantViolation("Signal weights must be finite")
        if len(weights) < 2:
            return
        non_zero = [w for w in weights if w > Decimal("0")]
        if len(non_zero) < 2:
            return
        max_w = max(non_zero)
        min_w = min(non_zero)
        ratio = max_w / min_w
        if ratio > cls.MAX_DOMINANCE_RATIO:
            raise EpistemicInvariantViolation(
                f"Signal dominance ratio {ratio} > allowed {cls.MAX_DOMINANCE_RATIO}"
            )
