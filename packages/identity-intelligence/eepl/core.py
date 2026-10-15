"""Deterministic Eligibility and Environmental Policy Layer (EEPL).

EEPL applies explicit age, location, occasion, and climate rules. It does not
infer missing context: a required unknown routes to REVIEW, and a policy block
cannot be overridden by style, fit, popularity, or recommendation scores.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

CONTRACT_VERSION = "1.0.0"


class GateVerdict(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    REVIEW = "review"


class ContextField(str, Enum):
    AGE = "age"
    LOCATION = "location"
    OCCASION = "occasion"
    CLIMATE = "climate"


@dataclass(frozen=True)
class EEPLContext:
    user_id: str
    age_years: int | None = None
    location: str | None = None
    occasion: str | None = None
    climate: str | None = None


@dataclass(frozen=True)
class EEPLPolicy:
    policy_id: str
    policy_version: str = "1.0.0"
    minimum_age: int | None = None
    maximum_age: int | None = None
    allowed_locations: tuple[str, ...] = ()
    allowed_occasions: tuple[str, ...] = ()
    allowed_climates: tuple[str, ...] = ()
    required_context: tuple[ContextField, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("policy_id must not be empty")
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must not be empty")
        for name in ("minimum_age", "maximum_age"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if self.minimum_age is not None and self.maximum_age is not None:
            if self.minimum_age > self.maximum_age:
                raise ValueError("minimum_age cannot exceed maximum_age")
        for name in ("allowed_locations", "allowed_occasions", "allowed_climates", "required_context"):
            if not isinstance(getattr(self, name), tuple):
                raise ValueError(f"{name} must be a tuple")
        if any(not isinstance(field, ContextField) for field in self.required_context):
            raise ValueError("required_context must contain ContextField values")
        if len(self.required_context) != len(set(self.required_context)):
            raise ValueError("required_context must not contain duplicates")
        for name in ("allowed_locations", "allowed_occasions", "allowed_climates"):
            values = getattr(self, name)
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{name} values must be non-empty strings")


@dataclass(frozen=True)
class EEPLResult:
    contract_version: str
    policy_id: str
    policy_version: str
    user_id: str
    candidate_id: str
    verdict: GateVerdict
    reason_codes: tuple[str, ...]
    explanations: tuple[str, ...]

    @property
    def blocks_candidate(self) -> bool:
        return self.verdict is GateVerdict.BLOCK

    @property
    def requires_review(self) -> bool:
        return self.verdict is GateVerdict.REVIEW


def _key(value: str) -> str:
    return value.strip().casefold()


def evaluate(policy: EEPLPolicy, context: EEPLContext, candidate_id: str) -> EEPLResult:
    """Evaluate configured eligibility constraints without guessing unknown data."""
    if not isinstance(context.user_id, str) or not context.user_id.strip():
        raise ValueError("context.user_id must not be empty")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError("candidate_id must not be empty")
    if context.age_years is not None and (
        not isinstance(context.age_years, int) or isinstance(context.age_years, bool) or context.age_years < 0
    ):
        raise ValueError("context.age_years must be a non-negative integer or None")

    required = set(policy.required_context)
    if policy.minimum_age is not None or policy.maximum_age is not None:
        required.add(ContextField.AGE)
    if policy.allowed_locations:
        required.add(ContextField.LOCATION)
    if policy.allowed_occasions:
        required.add(ContextField.OCCASION)
    if policy.allowed_climates:
        required.add(ContextField.CLIMATE)

    values = {
        ContextField.AGE: context.age_years,
        ContextField.LOCATION: context.location,
        ContextField.OCCASION: context.occasion,
        ContextField.CLIMATE: context.climate,
    }
    reasons: list[tuple[str, str, GateVerdict]] = []
    for field in sorted(required, key=lambda item: item.value):
        value = values[field]
        missing = value is None or (isinstance(value, str) and not value.strip())
        if missing:
            reasons.append((
                f"EEPL_REQUIRED_CONTEXT_MISSING_{field.value.upper()}",
                f"Required context '{field.value}' is unavailable; eligibility cannot be established.",
                GateVerdict.REVIEW,
            ))

    if context.age_years is not None:
        if policy.minimum_age is not None and context.age_years < policy.minimum_age:
            reasons.append(("EEPL_MINIMUM_AGE_NOT_MET", "User age is below the policy minimum.", GateVerdict.BLOCK))
        if policy.maximum_age is not None and context.age_years > policy.maximum_age:
            reasons.append(("EEPL_MAXIMUM_AGE_EXCEEDED", "User age exceeds the policy maximum.", GateVerdict.BLOCK))

    comparisons = (
        (ContextField.LOCATION, policy.allowed_locations, "EEPL_LOCATION_NOT_ALLOWED"),
        (ContextField.OCCASION, policy.allowed_occasions, "EEPL_OCCASION_NOT_ALLOWED"),
        (ContextField.CLIMATE, policy.allowed_climates, "EEPL_CLIMATE_NOT_ALLOWED"),
    )
    for field, allowed, code in comparisons:
        value = values[field]
        if allowed and isinstance(value, str) and value.strip():
            if _key(value) not in {_key(item) for item in allowed}:
                reasons.append((code, f"Context '{field.value}' is outside the policy allowlist.", GateVerdict.BLOCK))

    if any(verdict is GateVerdict.BLOCK for _, _, verdict in reasons):
        verdict = GateVerdict.BLOCK
    elif any(verdict is GateVerdict.REVIEW for _, _, verdict in reasons):
        verdict = GateVerdict.REVIEW
    else:
        verdict = GateVerdict.PASS

    if not reasons:
        reasons = [("EEPL_POLICY_PASSED", "All configured eligibility and context constraints passed.", GateVerdict.PASS)]
    return EEPLResult(
        contract_version=CONTRACT_VERSION,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        user_id=context.user_id,
        candidate_id=candidate_id,
        verdict=verdict,
        reason_codes=tuple(code for code, _, _ in reasons),
        explanations=tuple(message for _, message, _ in reasons),
    )
