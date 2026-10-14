"""
EpistemicInvariants – Mathematical guarantees for CFRP's reasoning.
"""
from decimal import Decimal
from typing import List

class EpistemicInvariantViolation(Exception):
    """Raised when an epistemic invariant is violated"""
    pass

class EpistemicInvariants:
    MAX_CONFIDENCE_JUMP = Decimal('0.3')
    MAX_DAILY_DECAY = Decimal('0.05')
    MIN_CONFIDENCE = Decimal('0.1')
    MAX_CFRP_INFLUENCE = Decimal('0.3')
    MIN_USI_AUTONOMY = Decimal('0.7')
    MAX_DOMINANCE_RATIO = Decimal('10.0')

    @classmethod
    def validate_confidence_change(cls, old: Decimal, new: Decimal, success: bool):
        delta = new - old
        if success:
            max_increase = cls.MAX_CONFIDENCE_JUMP * (Decimal('1') - old)
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
    def validate_decay(cls, old: Decimal, new: Decimal, days_elapsed: Decimal):
        if new < cls.MIN_CONFIDENCE:
            raise EpistemicInvariantViolation(
                f"Confidence {new} < minimum {cls.MIN_CONFIDENCE}"
            )
        if days_elapsed > Decimal('0'):
            max_decay = cls.MAX_DAILY_DECAY * days_elapsed * old
            actual_decay = old - new
            if actual_decay > max_decay:
                raise EpistemicInvariantViolation(
                    f"Decay {actual_decay} > allowed {max_decay}"
                )

    @classmethod
    def validate_cfrp_influence(cls, usi_weight: Decimal, cfrp_adjustment: Decimal) -> Decimal:
        bounded = max(-cls.MAX_CFRP_INFLUENCE, min(cls.MAX_CFRP_INFLUENCE, cfrp_adjustment))
        final = usi_weight * (Decimal('1') + bounded)
        min_weight = usi_weight * cls.MIN_USI_AUTONOMY
        if final < min_weight:
            return min_weight
        return final

    @classmethod
    def validate_no_dominance(cls, weights: List[Decimal]):
        if len(weights) < 2:
            return
        non_zero = [w for w in weights if w > Decimal('0')]
        if len(non_zero) < 2:
            return
        max_w = max(non_zero)
        min_w = min(non_zero)
        if min_w == Decimal('0'):
            return
        ratio = max_w / min_w
        if ratio > cls.MAX_DOMINANCE_RATIO:
            raise EpistemicInvariantViolation(
                f"Signal dominance ratio {ratio} > allowed {cls.MAX_DOMINANCE_RATIO}"
            )
