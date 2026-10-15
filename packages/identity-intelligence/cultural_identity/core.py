"""Explicit-declaration-only cultural identity policy kernel.

This module enforces only user-declared requirements and explicit candidate
metadata. It never infers culture, religion, ethnicity, or modesty requirements
from appearance, skin tone, name, location, or demographic proxies.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

CONTRACT_VERSION = "1.0.0"


class RequirementKind(str, Enum):
    REQUIRED_ATTRIBUTE = "required_attribute"
    FORBIDDEN_ATTRIBUTE = "forbidden_attribute"


class RequirementVerdict(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    REVIEW = "review"


@dataclass(frozen=True)
class CulturalRequirement:
    requirement_id: str
    declaration_id: str
    user_id: str
    attribute: str
    kind: RequirementKind
    hard: bool = True
    active: bool = True

    def __post_init__(self) -> None:
        for name in ("requirement_id", "declaration_id", "user_id", "attribute"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.kind, RequirementKind):
            raise ValueError("kind must be a RequirementKind")


@dataclass(frozen=True)
class CulturalIdentityResult:
    contract_version: str
    user_id: str
    candidate_id: str
    verdict: RequirementVerdict
    reason_codes: tuple[str, ...]
    explanations: tuple[str, ...]
    hard_conflict_ids: tuple[str, ...]
    soft_conflict_ids: tuple[str, ...]

    @property
    def blocks_candidate(self) -> bool:
        return self.verdict is RequirementVerdict.BLOCK

    @property
    def requires_review(self) -> bool:
        return self.verdict is RequirementVerdict.REVIEW


def _key(value: str) -> str:
    return value.strip().casefold()


def evaluate(
    user_id: str,
    candidate_id: str,
    candidate_attributes: tuple[str, ...],
    requirements: tuple[CulturalRequirement, ...],
    *,
    candidate_attributes_complete: bool,
) -> CulturalIdentityResult:
    """Evaluate only requirements explicitly declared by this user."""
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id must not be empty")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError("candidate_id must not be empty")
    if not isinstance(candidate_attributes, tuple) or not isinstance(requirements, tuple):
        raise ValueError("candidate_attributes and requirements must be tuples")
    if any(not isinstance(item, str) or not item.strip() for item in candidate_attributes):
        raise ValueError("candidate attributes must be non-empty strings")
    if any(not isinstance(item, CulturalRequirement) for item in requirements):
        raise ValueError("requirements must contain CulturalRequirement values")

    attributes = {_key(value) for value in candidate_attributes}
    reasons: list[tuple[str, str, RequirementVerdict, str | None, bool]] = []
    for requirement in sorted(requirements, key=lambda item: item.requirement_id):
        if requirement.user_id != user_id or not requirement.active:
            continue
        present = _key(requirement.attribute) in attributes
        if requirement.kind is RequirementKind.REQUIRED_ATTRIBUTE and not present:
            if requirement.hard and candidate_attributes_complete:
                reasons.append((
                    "CULTURAL_REQUIRED_ATTRIBUTE_MISSING",
                    f"Candidate does not satisfy explicitly declared requirement '{requirement.requirement_id}'.",
                    RequirementVerdict.BLOCK,
                    requirement.requirement_id,
                    True,
                ))
            elif requirement.hard:
                reasons.append((
                    "CULTURAL_CANDIDATE_METADATA_INCOMPLETE",
                    f"Candidate metadata is incomplete for requirement '{requirement.requirement_id}'.",
                    RequirementVerdict.REVIEW,
                    requirement.requirement_id,
                    True,
                ))
            else:
                reasons.append((
                    "CULTURAL_SOFT_REQUIREMENT_UNMET",
                    f"Soft preference '{requirement.requirement_id}' is not confirmed.",
                    RequirementVerdict.PASS,
                    requirement.requirement_id,
                    False,
                ))
        elif requirement.kind is RequirementKind.FORBIDDEN_ATTRIBUTE and present:
            if requirement.hard:
                reasons.append((
                    "CULTURAL_FORBIDDEN_ATTRIBUTE_PRESENT",
                    f"Candidate conflicts with explicit requirement '{requirement.requirement_id}'.",
                    RequirementVerdict.BLOCK,
                    requirement.requirement_id,
                    True,
                ))
            else:
                reasons.append((
                    "CULTURAL_SOFT_CONFLICT",
                    f"Candidate conflicts with soft preference '{requirement.requirement_id}'.",
                    RequirementVerdict.PASS,
                    requirement.requirement_id,
                    False,
                ))

    if any(verdict is RequirementVerdict.BLOCK for _, _, verdict, _, _ in reasons):
        verdict = RequirementVerdict.BLOCK
    elif any(verdict is RequirementVerdict.REVIEW for _, _, verdict, _, _ in reasons):
        verdict = RequirementVerdict.REVIEW
    else:
        verdict = RequirementVerdict.PASS

    if not reasons:
        reasons = [(
            "CULTURAL_DECLARED_REQUIREMENTS_PASSED",
            "No explicit cultural requirement conflicts with the candidate.",
            RequirementVerdict.PASS,
            None,
            False,
        )]
    hard_ids = tuple(sorted({item_id for _, _, _, item_id, hard in reasons if item_id and hard}))
    soft_ids = tuple(sorted({item_id for _, _, _, item_id, hard in reasons if item_id and not hard}))
    return CulturalIdentityResult(
        contract_version=CONTRACT_VERSION,
        user_id=user_id,
        candidate_id=candidate_id,
        verdict=verdict,
        reason_codes=tuple(code for code, _, _, _, _ in reasons),
        explanations=tuple(message for _, message, _, _, _ in reasons),
        hard_conflict_ids=hard_ids,
        soft_conflict_ids=soft_ids,
    )
