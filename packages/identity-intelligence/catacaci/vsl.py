"""Value System Layer (VSL) versioned priority governance.

VSL proposals are never applied automatically. A second authorized approver must
approve a versioned proposal, and safety/legal precedence is invariant.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ValueDimension(str, Enum):
    SAFETY = "safety"
    LEGAL_ELIGIBILITY = "legal_eligibility"
    USER_HARD_CONSTRAINT = "user_hard_constraint"
    NPL_HARD_NEGATIVE = "npl_hard_negative"
    CULTURAL_REQUIREMENT = "cultural_requirement"
    CONTEXT_ELIGIBILITY = "context_eligibility"
    IDENTITY_ALIGNMENT = "identity_alignment"
    FIT_CONFIDENCE = "fit_confidence"
    OTHER = "other"


def _validate_order(order: tuple[ValueDimension, ...]) -> None:
    if not isinstance(order, tuple) or any(not isinstance(item, ValueDimension) for item in order):
        raise ValueError("priority_order must be a tuple of ValueDimension values")
    if len(order) != len(ValueDimension) or set(order) != set(ValueDimension):
        raise ValueError("priority_order must include every dimension exactly once")
    if order[:2] != (ValueDimension.SAFETY, ValueDimension.LEGAL_ELIGIBILITY):
        raise ValueError("safety and legal eligibility must remain the first two priorities")


@dataclass(frozen=True)
class ValueProfile:
    version: str
    priority_order: tuple[ValueDimension, ...]
    approved_by: str = "bootstrap"
    approval_event_id: str = "bootstrap"

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("version must not be empty")
        if not isinstance(self.approved_by, str) or not self.approved_by.strip():
            raise ValueError("approved_by must not be empty")
        if not isinstance(self.approval_event_id, str) or not self.approval_event_id.strip():
            raise ValueError("approval_event_id must not be empty")
        _validate_order(self.priority_order)


@dataclass(frozen=True)
class ValueChangeProposal:
    proposal_id: str
    base_version: str
    proposed_version: str
    proposed_order: tuple[ValueDimension, ...]
    rationale: str
    proposer_id: str

    def __post_init__(self) -> None:
        for name in ("proposal_id", "base_version", "proposed_version", "rationale", "proposer_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.base_version == self.proposed_version:
            raise ValueError("proposed_version must differ from base_version")
        _validate_order(self.proposed_order)


def approve_change(
    current: ValueProfile,
    proposal: ValueChangeProposal,
    *,
    approver_id: str,
    approval_event_id: str,
) -> ValueProfile:
    if proposal.base_version != current.version:
        raise ValueError("proposal base_version does not match current profile")
    if not isinstance(approver_id, str) or not approver_id.strip():
        raise ValueError("approver_id must not be empty")
    if not isinstance(approval_event_id, str) or not approval_event_id.strip():
        raise ValueError("approval_event_id must not be empty")
    if approver_id == proposal.proposer_id:
        raise PermissionError("value changes require a distinct approver")
    return ValueProfile(
        version=proposal.proposed_version,
        priority_order=proposal.proposed_order,
        approved_by=approver_id,
        approval_event_id=approval_event_id,
    )
