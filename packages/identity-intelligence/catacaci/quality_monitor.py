"""Offline aggregation for auditable CAL decision-quality telemetry.

The aggregator deliberately does not create a database, dashboard, or live
monitoring claim. The caller must supply privacy-minimized, durable decision
events from the real serving path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Sequence

from .core import DecisionVerdict


@dataclass(frozen=True)
class DecisionQualityEvent:
    """A minimal decision event; do not add user IDs, measurements, or image data."""

    decision_id: str
    verdict: DecisionVerdict
    displayed: bool
    policy_version: str
    missing_required_evidence: int = 0
    provider_failures: int = 0
    fci_probability: float | None = None
    observed_fit_success: bool | None = None
    outcome_observed_at: datetime | None = None
    cohort_key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision_id, str) or not self.decision_id.strip():
            raise ValueError("decision_id must be a non-empty opaque identifier")
        if not isinstance(self.verdict, DecisionVerdict):
            raise ValueError("verdict must be a DecisionVerdict")
        if not isinstance(self.displayed, bool):
            raise ValueError("displayed must be boolean")
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must not be empty")
        for name in ("missing_required_evidence", "provider_failures"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.fci_probability is not None and (
            isinstance(self.fci_probability, bool)
            or not isinstance(self.fci_probability, (int, float))
            or not isfinite(self.fci_probability)
            or not 0.0 <= self.fci_probability <= 1.0
        ):
            raise ValueError("fci_probability must be finite and in [0, 1]")
        if self.observed_fit_success is not None:
            if not isinstance(self.observed_fit_success, bool):
                raise ValueError("observed_fit_success must be boolean or None")
            if self.fci_probability is None:
                raise ValueError("an observed fit outcome requires its original FCI probability")
            if not isinstance(self.outcome_observed_at, datetime) or self.outcome_observed_at.tzinfo is None or self.outcome_observed_at.utcoffset() is None:
                raise ValueError("an observed fit outcome requires a timezone-aware observation timestamp")
        elif self.outcome_observed_at is not None:
            raise ValueError("outcome_observed_at requires an observed fit outcome")
        if self.cohort_key is not None and (
            not isinstance(self.cohort_key, str) or not self.cohort_key.strip()
        ):
            raise ValueError("cohort_key must be a non-empty declared cohort label or None")


@dataclass(frozen=True)
class DecisionQualitySnapshot:
    status: str
    total_decisions: int
    show_count: int
    block_count: int
    review_count: int
    displayed_non_show_count: int
    incomplete_evidence_count: int
    provider_failure_count: int
    show_rate: float | None
    incomplete_evidence_rate: float | None
    provider_failure_rate: float | None
    labeled_fit_outcomes: int
    fit_outcome_success_rate: float | None
    fci_brier_score: float | None
    high_confidence_failure_rate: float | None
    policy_versions: tuple[str, ...]


def summarize_decision_quality(
    events: Sequence[DecisionQualityEvent],
    *,
    high_confidence_threshold: float = 0.8,
) -> DecisionQualitySnapshot:
    """Summarize CAL policy integrity and outcome evidence without conflating them.

    A displayed non-SHOW is a critical release-path violation. Rates are
    descriptive monitoring signals, not proof of model quality or causality.
    """
    if not isinstance(events, (tuple, list)) or not events:
        raise ValueError("at least one decision event is required")
    if any(not isinstance(item, DecisionQualityEvent) for item in events):
        raise ValueError("events must contain DecisionQualityEvent values")
    if not isinstance(high_confidence_threshold, (int, float)) or isinstance(high_confidence_threshold, bool) or not isfinite(high_confidence_threshold) or not 0.0 <= high_confidence_threshold <= 1.0:
        raise ValueError("high_confidence_threshold must be finite and in [0, 1]")
    decision_ids = [item.decision_id for item in events]
    if len(decision_ids) != len(set(decision_ids)):
        raise ValueError("decision_id values must be unique within a snapshot")

    shows = sum(item.verdict is DecisionVerdict.SHOW for item in events)
    blocks = sum(item.verdict is DecisionVerdict.BLOCK for item in events)
    reviews = sum(item.verdict is DecisionVerdict.REVIEW for item in events)
    leaks = sum(item.displayed and item.verdict is not DecisionVerdict.SHOW for item in events)
    incomplete = sum(item.missing_required_evidence > 0 for item in events)
    provider_failures = sum(item.provider_failures > 0 for item in events)
    outcomes = [item for item in events if item.observed_fit_success is not None]
    high_confidence = [
        item for item in outcomes
        if float(item.fci_probability) >= high_confidence_threshold
    ]
    brier = (
        sum(
            (float(item.fci_probability) - (1.0 if item.observed_fit_success else 0.0)) ** 2
            for item in outcomes
        ) / len(outcomes)
        if outcomes else None
    )
    failure_rate = (
        sum(not item.observed_fit_success for item in high_confidence) / len(high_confidence)
        if high_confidence else None
    )
    total = len(events)
    status = (
        "critical" if leaks
        else "attention_required" if incomplete or provider_failures
        else "collecting"
    )
    return DecisionQualitySnapshot(
        status=status,
        total_decisions=total,
        show_count=shows,
        block_count=blocks,
        review_count=reviews,
        displayed_non_show_count=leaks,
        incomplete_evidence_count=incomplete,
        provider_failure_count=provider_failures,
        show_rate=shows / total,
        incomplete_evidence_rate=incomplete / total,
        provider_failure_rate=provider_failures / total,
        labeled_fit_outcomes=len(outcomes),
        fit_outcome_success_rate=(
            sum(bool(item.observed_fit_success) for item in outcomes) / len(outcomes)
            if outcomes else None
        ),
        fci_brier_score=brier,
        high_confidence_failure_rate=failure_rate,
        policy_versions=tuple(sorted({item.policy_version for item in events})),
    )
