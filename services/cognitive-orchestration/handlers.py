"""Initial deterministic PAMASMMA-derived handlers.

These handlers produce operational triage and content-review findings only.
They do not make purchase suitability decisions; those remain under CaTaCaCi/CAL.
"""
from __future__ import annotations

from typing import Any

try:
    from .contracts import CognitiveRequest, CognitiveResponse, CognitiveSystem
except ImportError:  # Direct module loading in repository tests.
    from contracts import CognitiveRequest, CognitiveResponse, CognitiveSystem


def _text(context: dict[str, Any], key: str, *, max_length: int = 4000) -> str:
    value = context.get(key, "")
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_length]


def _response(
    request: CognitiveRequest,
    *,
    action: str,
    rationale: str,
    outputs: dict[str, Any],
    requires_approval: bool,
    impact: str,
) -> CognitiveResponse:
    return CognitiveResponse(
        request_id=request.event_id,
        system=request.system,
        action=action,
        rationale=rationale,
        outputs=outputs,
        requires_founder_approval=requires_approval,
        estimated_impact=impact,
    )


async def executive_operations(request: CognitiveRequest) -> CognitiveResponse:
    """Classify an incident report into a review priority; never triggers remediation."""
    context = request.context
    severity = _text(context, "severity").lower()
    allowed = {"low", "medium", "high", "critical"}
    if severity not in allowed:
        return _response(
            request, action="request_more_information",
            rationale="Incident severity is missing or outside the supported vocabulary.",
            outputs={"valid_severities": sorted(allowed), "automated_remediation": False},
            requires_approval=True, impact="No operational action taken",
        )
    priority = {"low": 4, "medium": 3, "high": 2, "critical": 1}[severity]
    incident = _text(context, "incident_type", max_length=120) or "unspecified"
    service = _text(context, "affected_service", max_length=120) or "unspecified"
    return _response(
        request, action="triage_incident",
        rationale="Priority is derived only from the explicitly supplied severity; no remediation is executed.",
        outputs={
            "severity": severity, "queue_priority": priority,
            "incident_type": incident, "affected_service": service,
            "automated_remediation": False,
        },
        requires_approval=severity in {"high", "critical"},
        impact="Triage recommendation only",
    )


async def relationship_management(request: CognitiveRequest) -> CognitiveResponse:
    """Route support messages using explicit request category and urgency only."""
    context = request.context
    category = _text(context, "category").lower()
    urgency = _text(context, "urgency").lower()
    queues = {
        "account": "account_support",
        "product": "product_support",
        "order": "commerce_support",
        "privacy": "privacy_support",
        "safety": "safety_review",
        "technical": "technical_support",
    }
    if category not in queues or urgency not in {"normal", "urgent"}:
        return _response(
            request, action="request_clarification",
            rationale="A supported category and urgency are required; no personal traits are inferred.",
            outputs={"valid_categories": sorted(queues), "valid_urgencies": ["normal", "urgent"]},
            requires_approval=True, impact="No message sent or account changed",
        )
    return _response(
        request, action="route_support_request",
        rationale="Queue selection uses only the declared support category and urgency.",
        outputs={
            "queue": queues[category], "urgency": urgency,
            "priority_escalation": urgency == "urgent" or category in {"privacy", "safety"},
            "message_sent": False,
        },
        requires_approval=category in {"privacy", "safety"},
        impact="Internal routing recommendation only",
    )


async def narrative_governance(request: CognitiveRequest) -> CognitiveResponse:
    """Check basic copy requirements without claiming broad brand-voice understanding."""
    content = _text(request.context, "content")
    required_terms = request.context.get("required_terms", [])
    if not content:
        return _response(
            request, action="hold_for_revision",
            rationale="No content was supplied for review.",
            outputs={"findings": ["missing_content"], "checks_performed": ["non_empty_content"]},
            requires_approval=True, impact="Content not published",
        )
    if not isinstance(required_terms, list) or not all(isinstance(x, str) for x in required_terms):
        return _response(
            request, action="request_valid_input",
            rationale="required_terms must be a list of strings.",
            outputs={"findings": ["invalid_required_terms"], "checks_performed": []},
            requires_approval=True, impact="Content not published",
        )
    missing = [term for term in required_terms if term.casefold() not in content.casefold()]
    findings = ["missing_required_term:" + term for term in missing]
    return _response(
        request, action="hold_for_revision" if findings else "eligible_for_human_review",
        rationale="This narrow check evaluates only non-empty content and explicitly supplied required terms; it does not certify brand voice or factual accuracy.",
        outputs={
            "findings": findings,
            "checks_performed": ["non_empty_content", "explicit_required_terms"],
            "human_review_required": True,
            "published": False,
        },
        requires_approval=True, impact="Draft review only; no publication performed",
    )


async def persuasion_governance(request: CognitiveRequest) -> CognitiveResponse:
    """Flag explicit high-risk marketing patterns; ambiguous content always needs review."""
    content = _text(request.context, "content", max_length=10000).casefold()
    if not content:
        return _response(
            request, action="hold_for_review",
            rationale="No campaign content was supplied; absence of evidence is not approval.",
            outputs={"findings": ["missing_content"], "policy_pass": False, "human_review_required": True},
            requires_approval=True, impact="Campaign not approved or published",
        )
    checks = {
        "guaranteed_outcome_claim": ("guaranteed results", "guaranteed to fit", "100% guaranteed"),
        "false_scarcity_pattern": ("only today", "last chance", "only 1 left"),
        "coercive_pressure_pattern": ("buy now or regret", "you will be ugly", "everyone will judge you"),
        "undisclosed_sponsorship_marker": ("#ad", "sponsored"),
    }
    findings = []
    for name, markers in checks.items():
        if name == "undisclosed_sponsorship_marker":
            # Presence of a disclosure marker is not a defect; this is a disclosure cue,
            # not proof of adequate disclosure. Leave enforcement to reviewed policy.
            continue
        if any(marker in content for marker in markers):
            findings.append(name)
    disclosure = any(marker in content for marker in checks["undisclosed_sponsorship_marker"])
    if not disclosure:
        findings.append("sponsorship_disclosure_not_detected")
    return _response(
        request, action="hold_for_policy_review" if findings else "eligible_for_human_review",
        rationale="Deterministic lexical preflight only. It cannot establish truth, legal compliance, or the absence of manipulation.",
        outputs={
            "findings": findings,
            "policy_pass": False,
            "human_review_required": True,
            "sponsorship_disclosure_marker_detected": disclosure,
            "published": False,
        },
        requires_approval=True, impact="Preflight only; no campaign approved or published",
    )


HANDLERS = {
    CognitiveSystem.EXECUTIVE_OPERATIONS: executive_operations,
    CognitiveSystem.RELATIONSHIP_MANAGEMENT: relationship_management,
    CognitiveSystem.NARRATIVE_GOVERNANCE: narrative_governance,
    CognitiveSystem.PERSUASION_GOVERNANCE: persuasion_governance,
}
