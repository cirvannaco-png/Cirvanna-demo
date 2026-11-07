"""Cirvanna User Style Index and Style Desk colour preference contracts."""
from .color_profile import ColorPreferenceProfile

from .core import (
    CONTRACT_VERSION,
    DEFAULT_MIN_ALIGNMENT_SCORE,
    StylePreference,
    USIProfile,
    USIResult,
    USIVerdict,
    evaluate,
)

__all__ = [
    "ColorPreferenceProfile",
    "CONTRACT_VERSION",
    "DEFAULT_MIN_ALIGNMENT_SCORE",
    "StylePreference",
    "USIProfile",
    "USIResult",
    "USIVerdict",
    "evaluate",
]
