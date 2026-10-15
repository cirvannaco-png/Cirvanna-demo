"""Counterfactual Auditing Module (CAM) records scenario comparisons, not causality."""
from __future__ import annotations

from dataclasses import dataclass

from .core import ArbitrationResult


@dataclass(frozen=True)
class CounterfactualAudit:
    audit_id: str
    request_id: str
    candidate_id: str
    observed_verdict: str
    simulated_verdict: str
    changed_signal_ids: tuple[str, ...]
    policy_version: str
    replay_version: str
    evaluated_at: str
    interpretation: str = "counterfactual_scenario_not_observed_causality"

    def __post_init__(self) -> None:
        for name in ("audit_id", "request_id", "candidate_id", "observed_verdict", "simulated_verdict", "policy_version", "replay_version", "evaluated_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.changed_signal_ids, tuple):
            raise ValueError("changed_signal_ids must be a tuple")
        if any(not isinstance(item, str) or not item.strip() for item in self.changed_signal_ids):
            raise ValueError("changed signal IDs must be non-empty strings")
        if len(self.changed_signal_ids) != len(set(self.changed_signal_ids)):
            raise ValueError("changed signal IDs must be unique")


def record_counterfactual(
    audit_id: str,
    observed: ArbitrationResult,
    simulated: ArbitrationResult,
    changed_signal_ids: tuple[str, ...],
    replay_version: str,
    evaluated_at: str,
) -> CounterfactualAudit:
    if observed.request_id != simulated.request_id or observed.candidate_id != simulated.candidate_id:
        raise ValueError("counterfactual replay must use the same request and candidate")
    if observed.policy_version != simulated.policy_version:
        raise ValueError("counterfactual replay must use the same policy version")
    return CounterfactualAudit(
        audit_id=audit_id,
        request_id=observed.request_id,
        candidate_id=observed.candidate_id,
        observed_verdict=observed.verdict.value,
        simulated_verdict=simulated.verdict.value,
        changed_signal_ids=changed_signal_ids,
        policy_version=observed.policy_version,
        replay_version=replay_version,
        evaluated_at=evaluated_at,
    )
