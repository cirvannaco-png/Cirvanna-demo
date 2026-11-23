"""Server-owned, version-pinned CaTaCaCi/CAL policy registry."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from math import isfinite
from typing import Any


class CALPolicyRegistryError(ValueError):
    """The active server-side CAL policy registry is absent or invalid."""


@dataclass(frozen=True)
class CALPolicy:
    policy_id: str
    policy_version: str
    minimum_fit_confidence: float
    maximum_fit_confidence_disagreement: float
    minimum_alignment_score: float


_REQUIRED_FIELDS = {
    "policy_version",
    "minimum_fit_confidence",
    "maximum_fit_confidence_disagreement",
    "minimum_alignment_score",
}


def _unit_interval(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CALPolicyRegistryError(f"{field} must be a numeric value")
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise CALPolicyRegistryError(f"{field} must be finite and within [0, 1]")
    return float(value)


def validate_registry(raw: str | None = None) -> dict[str, dict[str, Any]]:
    source = os.getenv("CATACACI_POLICY_REGISTRY_JSON", "") if raw is None else raw
    if not isinstance(source, str) or not source.strip():
        raise CALPolicyRegistryError("server CAL policy registry is not configured")
    try:
        registry = json.loads(source)
    except json.JSONDecodeError as exc:
        raise CALPolicyRegistryError("server CAL policy registry is invalid JSON") from exc
    if not isinstance(registry, dict) or not registry:
        raise CALPolicyRegistryError("server CAL policy registry must be a non-empty object")
    for policy_id, entry in registry.items():
        if not isinstance(policy_id, str) or not policy_id.strip():
            raise CALPolicyRegistryError("policy IDs must be non-empty strings")
        if not isinstance(entry, dict) or set(entry) != _REQUIRED_FIELDS:
            raise CALPolicyRegistryError(f"policy {policy_id!r} has an invalid schema")
        if not isinstance(entry["policy_version"], str) or not entry["policy_version"].strip():
            raise CALPolicyRegistryError(f"policy {policy_id!r} has an invalid version")
        for field in (
            "minimum_fit_confidence",
            "maximum_fit_confidence_disagreement",
            "minimum_alignment_score",
        ):
            _unit_interval(entry[field], field)
    return registry


def resolve_cal_policy(policy_id: str, policy_version: str) -> CALPolicy:
    if not isinstance(policy_id, str) or not policy_id.strip():
        raise CALPolicyRegistryError("policy_id must be a non-empty string")
    if not isinstance(policy_version, str) or not policy_version.strip():
        raise CALPolicyRegistryError("policy_version must be a non-empty string")
    registry = validate_registry()
    entry = registry.get(policy_id)
    if entry is None or entry["policy_version"] != policy_version:
        raise CALPolicyRegistryError("requested CAL policy is not active on this server")
    return CALPolicy(
        policy_id=policy_id,
        policy_version=entry["policy_version"],
        minimum_fit_confidence=float(entry["minimum_fit_confidence"]),
        maximum_fit_confidence_disagreement=float(entry["maximum_fit_confidence_disagreement"]),
        minimum_alignment_score=float(entry["minimum_alignment_score"]),
    )
