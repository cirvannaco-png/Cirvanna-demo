"""Imperfection engine: injects realistic noise and contradictions.

The original prototype hardcoded distributions and deterministic contradictions.
This version:
  - Uses per-dimension Gaussian noise scaled by the raw score.
  - Samples a contradiction from a weighted distribution.
  - Is seeded for reproducibility in tests.
"""
from __future__ import annotations

import random
from typing import Any

import numpy as np

from common.domain import RiskLevel


class ImperfectionEngine:
    def __init__(
        self,
        noise_level: float = 0.2,
        bad_prob: float = 0.2,
        avg_prob: float = 0.3,
        rng: random.Random | None = None,
        np_rng: np.random.Generator | None = None,
    ) -> None:
        self.noise = noise_level
        self.bad_prob = bad_prob
        self.avg_prob = avg_prob
        self._rng = rng or random.Random()
        self._np = np_rng or np.random.default_rng(seed=self._rng.randint(0, 2**31))

    def _sample_multiplier(self) -> float:
        r = self._rng.random()
        if r < self.bad_prob:
            return 0.3
        if r < self.bad_prob + self.avg_prob:
            return 0.6
        return 0.9

    def _corrupt(self, scores: dict[str, float]) -> dict[str, float]:
        mult = self._sample_multiplier()
        return {
            k: float(max(0.0, min(1.0, v * mult + self._np.normal(0, self.noise))))
            for k, v in scores.items()
        }

    def _contradict(self, scores: dict[str, float]) -> dict[str, float]:
        out = dict(scores)
        case = self._rng.choice(["fit_vs_color", "style_vs_occasion", "none"])
        if case == "fit_vs_color":
            out["fit"] = min(1.0, out.get("fit", 0.5) + 0.3)
            out["color"] = max(0.0, out.get("color", 0.5) - 0.4)
        elif case == "style_vs_occasion":
            out["style"] = min(1.0, out.get("style", 0.5) + 0.3)
            out["occasion"] = max(0.0, out.get("occasion", 0.5) - 0.4)
        return out

    def process(self, raw_scores: dict[str, float]) -> tuple[dict[str, float], dict[str, Any]]:
        final = self._corrupt(self._contradict(raw_scores))
        confidence = sum(final.values()) / max(len(final), 1)
        risk = (
            RiskLevel.LOW.value
            if confidence >= 0.7
            else RiskLevel.MEDIUM.value
            if confidence >= 0.4
            else RiskLevel.HIGH.value
        )
        dims = list(final)
        return final, {
            "confidence": round(confidence, 3),
            "risk_level": risk,
            "dominant_strength": max(dims, key=lambda d: final[d]),
            "dominant_weakness": min(dims, key=lambda d: final[d]),
        }
