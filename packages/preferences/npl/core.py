"""Deterministic Negative Preference Layer (NPL) policy kernel.

This module enforces explicit hard exclusions and durable learned exclusions.
It deliberately has no database, ranking model, network access, or hidden learning.
Persistence and audit-event delivery belong in the consuming service.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable

CONTRACT_VERSION = "1.0.0"
DEFAULT_REJECTION_THRESHOLD = 3


class PreferenceSource(str, Enum):
    USER_DECLARED = "user_declared"
    LEARNED_REJECTION = "learned_rejection"


class TargetType(str, Enum):
    ITEM = "item"
    ATTRIBUTE = "attribute"


@dataclass(frozen=True)
class NegativePreference:
    preference_id: str
    user_id: str
    target_type: TargetType
    target_value: str
    source: PreferenceSource
    rejection_event_ids: tuple[str, ...] = ()
    rejection_threshold: int = DEFAULT_REJECTION_THRESHOLD
    active: bool = True
    correction_event_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("preference_id", "user_id", "target_value"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if not isinstance(self.target_type, TargetType):
            raise ValueError("target_type must be a TargetType")
        if not isinstance(self.source, PreferenceSource):
            raise ValueError("source must be a PreferenceSource")
        if not isinstance(self.rejection_event_ids, tuple):
            raise ValueError("rejection_event_ids must be a tuple")
        if any(not isinstance(event_id, str) or not event_id.strip() for event_id in self.rejection_event_ids):
            raise ValueError("rejection event IDs must be non-empty strings")
        if len(self.rejection_event_ids) != len(set(self.rejection_event_ids)):
            raise ValueError("rejection event IDs must be unique")
        if not isinstance(self.rejection_threshold, int) or self.rejection_threshold < 1:
            raise ValueError("rejection_threshold must be a positive integer")
        if self.source is PreferenceSource.USER_DECLARED and not self.active and not self.correction_event_id:
            raise ValueError("retracting a user-declared preference requires a correction event ID")

    @property
    def rejection_count(self) -> int:
        return len(self.rejection_event_ids)

    @property
    def is_hard_veto(self) -> bool:
        if not self.active:
            return False
        if self.source is PreferenceSource.USER_DECLARED:
            return True
        return self.rejection_count >= self.rejection_threshold


@dataclass(frozen=True)
class NPLDecision:
    contract_version: str
    user_id: str
    candidate_id: str
    blocked: bool
    reason_code: str
    hard_veto_preference_ids: tuple[str, ...]
    soft_negative_preference_ids: tuple[str, ...]

    @property
    def may_display(self) -> bool:
        """NPL only denies display; passing NPL does not authorize display."""
        return not self.blocked


def _normalize(value: str) -> str:
    return value.strip().casefold()


def record_rejection(
    preference: NegativePreference,
    rejection_event_id: str,
) -> NegativePreference:
    """Record one rejection idempotently; threshold crossing creates a durable veto."""
    if not isinstance(rejection_event_id, str) or not rejection_event_id.strip():
        raise ValueError("rejection_event_id must not be empty")
    if preference.source is not PreferenceSource.LEARNED_REJECTION:
        raise ValueError("rejection events may only update learned preferences")
    if not preference.active:
        raise ValueError("a retracted preference cannot learn new rejections")
    if rejection_event_id in preference.rejection_event_ids:
        return preference
    return replace(
        preference,
        rejection_event_ids=preference.rejection_event_ids + (rejection_event_id,),
    )


def retract_preference(
    preference: NegativePreference,
    correction_event_id: str,
) -> NegativePreference:
    """Retract a preference only through an explicit, auditable correction event."""
    if not isinstance(correction_event_id, str) or not correction_event_id.strip():
        raise ValueError("correction_event_id must not be empty")
    if not preference.active:
        if preference.correction_event_id == correction_event_id:
            return preference
        raise ValueError("preference is already retracted")
    return replace(preference, active=False, correction_event_id=correction_event_id)


def evaluate(
    user_id: str,
    candidate_id: str,
    candidate_attributes: Iterable[str],
    preferences: Iterable[NegativePreference],
) -> NPLDecision:
    """Evaluate only the current user's exclusions; never infer or score identity."""
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id must not be empty")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError("candidate_id must not be empty")

    attributes = {_normalize(value) for value in candidate_attributes if isinstance(value, str) and value.strip()}
    item_key = _normalize(candidate_id)
    hard_vetoes: list[str] = []
    soft_negatives: list[str] = []

    for preference in preferences:
        if preference.user_id != user_id or not preference.active:
            continue
        target = _normalize(preference.target_value)
        matches = (
            preference.target_type is TargetType.ITEM and target == item_key
        ) or (
            preference.target_type is TargetType.ATTRIBUTE and target in attributes
        )
        if not matches:
            continue
        if preference.is_hard_veto:
            hard_vetoes.append(preference.preference_id)
        elif preference.source is PreferenceSource.LEARNED_REJECTION:
            soft_negatives.append(preference.preference_id)

    hard_ids = tuple(sorted(set(hard_vetoes)))
    soft_ids = tuple(sorted(set(soft_negatives) - set(hard_ids)))
    blocked = bool(hard_ids)
    return NPLDecision(
        contract_version=CONTRACT_VERSION,
        user_id=user_id,
        candidate_id=candidate_id,
        blocked=blocked,
        reason_code="NPL_HARD_NEGATIVE" if blocked else "NPL_NO_HARD_VETO",
        hard_veto_preference_ids=hard_ids,
        soft_negative_preference_ids=soft_ids,
    )
