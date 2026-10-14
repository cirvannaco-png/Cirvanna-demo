"""
USIIntegration – Applies CFRP's epistemic gravity to USI suggestions.
"""
from decimal import Decimal
from typing import List, Dict

from src.core.cfrp_manager import CFRPManager
from src.core.epistemic_invariants import EpistemicInvariants

class USIIntegration:
    def __init__(self, cfrp_manager: CFRPManager):
        self.cfrp_manager = cfrp_manager

    async def get_weighted_suggestions(self, user_id: str, raw_suggestions: List[Dict]) -> List[Dict]:
        instance = await self.cfrp_manager.get_instance(user_id)
        signal_ids = [s['signal'] for s in raw_suggestions]
        advice_result = await instance.get_advice(signal_ids)
        advisories = advice_result.get('advisories', {})

        enhanced = []
        weights = []
        for suggestion in raw_suggestions:
            signal_id = suggestion['signal']
            usi_weight = Decimal(str(suggestion['usi_weight']))
            advisory = advisories.get(signal_id, {})
            cfrp_adjustment = Decimal(str(advisory.get('total_cfrp_adjustment', 0.0)))

            final_weight = EpistemicInvariants.validate_cfrp_influence(
                usi_weight=usi_weight,
                cfrp_adjustment=cfrp_adjustment
            )

            enhanced_suggestion = {
                **suggestion,
                'final_weight': float(final_weight),
                'cfrp_adjustment': float(cfrp_adjustment),
                'epistemic_notes': advisory.get('epistemic_notes', [])
            }
            enhanced.append(enhanced_suggestion)
            weights.append(final_weight)

        EpistemicInvariants.validate_no_dominance(weights)
        enhanced.sort(key=lambda x: x['final_weight'], reverse=True)
        return enhanced

    async def process_feedback(self, user_id: str, signal_id: str, success: bool, value: float = 1.0):
        instance = await self.cfrp_manager.get_instance(user_id)
        return await instance.reinforce(signal_id, success, value)
