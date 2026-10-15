"""Collective Intelligence Layer (CIL) cohort aggregation contract.

This is a minimum-contributor suppression gate, not differential privacy.
Upstream code must provide stable pseudonymous contributor tokens and must not
pass direct identifiers or sensitive raw attributes.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class CohortObservation:
    event_id: str
    contributor_token: str
    cohort_key: str
    outcome_success: bool

    def __post_init__(self) -> None:
        for name in ("event_id", "contributor_token", "cohort_key"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.outcome_success, bool):
            raise ValueError("outcome_success must be boolean")


@dataclass(frozen=True)
class CohortAggregate:
    cohort_key: str
    contributor_count: int
    success_rate: float | None
    suppressed: bool
    reason_code: str


def aggregate_cohort(
    observations: tuple[CohortObservation, ...],
    *,
    minimum_contributors: int = 20,
) -> CohortAggregate:
    if not isinstance(observations, tuple):
        raise ValueError("observations must be a tuple")
    if not isinstance(minimum_contributors, int) or minimum_contributors < 2:
        raise ValueError("minimum_contributors must be an integer of at least 2")
    if any(not isinstance(item, CohortObservation) for item in observations):
        raise ValueError("observations must contain CohortObservation values")
    if not observations:
        return CohortAggregate("", 0, None, True, "CIL_NO_OBSERVATIONS")
    cohort_keys = {item.cohort_key for item in observations}
    if len(cohort_keys) != 1:
        raise ValueError("one aggregate call must contain a single cohort")
    if len({item.event_id for item in observations}) != len(observations):
        raise ValueError("event IDs must be unique")
    if len({item.contributor_token for item in observations}) != len(observations):
        raise ValueError("each contributor may contribute only once per cohort aggregate")

    count = len(observations)
    key = observations[0].cohort_key
    if count < minimum_contributors:
        return CohortAggregate(key, count, None, True, "CIL_MINIMUM_COHORT_NOT_MET")
    rate = sum(1 for item in observations if item.outcome_success) / count
    if not isfinite(rate):
        raise ValueError("aggregate rate must be finite")
    return CohortAggregate(key, count, rate, False, "CIL_COHORT_AGGREGATED")
