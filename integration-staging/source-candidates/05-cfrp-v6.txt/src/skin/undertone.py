"""
Undertone classification: warm, cool, neutral, olive.
"""
from enum import Enum
import numpy as np

class Undertone(Enum):
    WARM = "warm"
    COOL = "cool"
    NEUTRAL = "neutral"
    OLIVE = "olive"
    GOLDEN = "golden"
    RED = "red"

class UndertoneAnalyzer:
    @staticmethod
    def classify_from_rgb(rgb_patch: np.ndarray) -> Undertone:
        r_mean = np.mean(rgb_patch[..., 0])
        g_mean = np.mean(rgb_patch[..., 1])
        b_mean = np.mean(rgb_patch[..., 2])

        if r_mean > g_mean * 1.1 and r_mean > b_mean * 1.2:
            return Undertone.WARM
        elif b_mean > r_mean * 1.1:
            return Undertone.COOL
        elif abs(r_mean - g_mean) < 5 and abs(r_mean - b_mean) < 5:
            return Undertone.NEUTRAL
        else:
            return Undertone.OLIVE
