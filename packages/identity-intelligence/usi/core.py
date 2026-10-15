"""User Style Index (USI) explicit-preference alignment contract.

USI evaluates declared positive style preferences only. Hard dislikes and
non-negotiable exclusions belong to NPL; USI never overrides NPL or authorizes
display. The default threshold is an engineering setting, not an empirically
validated or calibrated probability.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

CONTRACT_VERSION = "1.0.0"
DEFAULT_MIN_ALIGNMENT_SCORE = 0.60


class USIVerdict(str, Enum):
    PASS = "pass"
    REVIEW = "review"
    BELOW_THRESHOLD = "below_threshold"


@dataclass(frozen=True)
class StylePreference:
    preference_id: str
    user_id: str
    attribute: str
    weight: float = 1.0
    active: bool = True

    def __post_init__(self) -> None:
        for name in ("preference_id", "user_id", "attribute"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isfinite(self.weight) or not 0.0 < self.weight <= 1.0:
            raise ValueError("weight must be finite and in (0, 1]")


@dataclass(frozen=True)
class USIProfile:
    profile_id: str
    user_id: str
    version: str
    preferences: tuple[StylePreference, ...]

    def __post_init__(self) -> None:
        for name in ("profile_id", "user_id", "version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.preferences, tuple):
            raise ValueError("preferences must be a tuple")
        if any(not isinstance(item, StylePreference) for item in self.preferences):
            raise ValueError("preferences must contain StylePreference values")
        if any(item.user_id != self.user_id for item in self.preferences):
            raise ValueError("all preferences must belong to the profile user")
        ids = [item.preference_id for item in self.preferences]
        if len(ids) != len(set(ids)):
            raise ValueError("preference IDs must be unique")


@dataclass(frozen=True)
class USIResult:
    contract_version: str
    profile_version: str
    user_id: str
    candidate_id: str
    verdict: USIVerdict
    alignment_score: float | None
    matched_preference_ids: tuple[str, ...]
    unmatched_preference_ids: tuple[str, ...]
    reason_code: str
    explanation: str

    def to_cal_signal(self):
        """Translate alignment evidence into CAL's non-veto identity signal."""
        from catacaci import DecisionSignal, SignalKind, SignalState

        if self.verdict is USIVerdict.REVIEW:
            state = SignalState.UNKNOWN
            confidence = None
        elif self.verdict is USIVerdict.BELOW_THRESHOLD:
            # A soft style mismatch requires review; it is not a hard exclusion.
            state = SignalState.BLOCK
            confidence = self.alignment_score
        else:
            state = SignalState.PASS
            confidence = self.alignment_score
        return DecisionSignal(
            signal_id=f"usi:{self.profile_version}:{self.candidate_id}",
            kind=SignalKind.IDENTITY_ALIGNMENT,
            state=state,
            reason_code=self.reason_code,
            explanation=self.explanation,
            required=True,
            confidence=confidence,
            source_version=f"{self.contract_version}:{self.profile_version}",
        )


def _key(value: str) -> str:
    return value.strip().casefold()


def evaluate(
    profile: USIProfile,
    candidate_id: str,
    candidate_attributes: tuple[str, ...],
    *,
    candidate_attributes_complete: bool,
    minimum_alignment_score: float = DEFAULT_MIN_ALIGNMENT_SCORE,
) -> USIResult:
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError("candidate_id must not be empty")
    if not isinstance(candidate_attributes, tuple):
        raise ValueError("candidate_attributes must be a tuple")
    if any(not isinstance(item, str) or not item.strip() for item in candidate_attributes):
        raise ValueError("candidate attributes must be non-empty strings")
    if not isfinite(minimum_alignment_score) or not 0.0 <= minimum_alignment_score <= 1.0:
        raise ValueError("minimum_alignment_score must be finite and in [0, 1]")

    preferences = tuple(item for item in profile.preferences if item.active)
    if not preferences:
        return USIResult(
            CONTRACT_VERSION, profile.version, profile.user_id, candidate_id,
            USIVerdict.REVIEW, None, (), (), "USI_DECLARED_PREFERENCES_MISSING",
            "No active explicit style preferences are available; alignment cannot be established.",
        )
    if not candidate_attributes_complete:
        return USIResult(
            CONTRACT_VERSION, profile.version, profile.user_id, candidate_id,
            USIVerdict.REVIEW, None, (), (), "USI_CANDIDATE_METADATA_INCOMPLETE",
            "Candidate attributes are incomplete; style alignment is unknown.",
        )

    attributes = {_key(item) for item in candidate_attributes}
    matched = tuple(sorted(item.preference_id for item in preferences if _key(item.attribute) in attributes))
    unmatched = tuple(sorted(item.preference_id for item in preferences if _key(item.attribute) not in attributes))
    total_weight = sum(item.weight for item in preferences)
    matched_weight = sum(item.weight for item in preferences if item.preference_id in set(matched))
    score = matched_weight / total_weight

    if score < minimum_alignment_score:
        verdict = USIVerdict.BELOW_THRESHOLD
        code = "USI_ALIGNMENT_BELOW_THRESHOLD"
        explanation = (
            f"Explicit style alignment score {score:.3f} is below configured threshold "
            f"{minimum_alignment_score:.3f}; route to CAL review rather than hard-blocking."
        )
    else:
        verdict = USIVerdict.PASS
        code = "USI_ALIGNMENT_PASSED"
        explanation = (
            f"Explicit style alignment score {score:.3f} meets configured threshold "
            f"{minimum_alignment_score:.3f}; NPL and CAL still apply."
        )
    return USIResult(
        CONTRACT_VERSION, profile.version, profile.user_id, candidate_id,
        verdict, score, matched, unmatched, code, explanation,
    )
