# src/explainability/explainer.py
from typing import Optional
from src.core.eepl import CandidateItem
from src.core.domain.entities import UserProfile
from src.infrastructure.external.climate_service import EnvironmentalSignalVector

class Explainer:
    async def explain(self, candidate: CandidateItem, user: Optional[UserProfile], context: dict, esv: EnvironmentalSignalVector) -> str:
        reasons = []
        if candidate.fci_score is not None:
            reasons.append(f"Fit confidence: {candidate.fci_score:.2f}")
        if candidate.environmental_score > 0.7:
            reasons.append("Great for current weather")
        if candidate.revival_boost > 0.1:
            reasons.append("Trending item")
        if not reasons:
            reasons.append("Balanced recommendation")
        return ", ".join(reasons)
