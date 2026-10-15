"""API-gateway decision composition for EEPL, NPL, and CaTaCaCi CAL.

This module composes already-computed domain results. It does not calculate
identity, fit, or model scores. CAL remains the only display authorization.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from catacaci import (
    ArbitrationRequest,
    ArbitrationResult,
    DecisionSignal,
    SignalKind,
    SignalState,
    arbitrate,
)
from eepl import EEPLResult, GateVerdict
from npl import NPLDecision


@dataclass(frozen=True)
class DecisionPipelineResult:
    eepl_result: EEPLResult
    npl_decision: NPLDecision
    cal_result: ArbitrationResult

    @property
    def may_display(self) -> bool:
        """Only CaTaCaCi CAL SHOW can authorize display."""
        return self.cal_result.may_display


def _eepl_signals(result: EEPLResult) -> tuple[DecisionSignal, ...]:
    signals: list[DecisionSignal] = []
    for index, (code, explanation) in enumerate(zip(result.reason_codes, result.explanations)):
        if code == "EEPL_POLICY_PASSED":
            kind, state = SignalKind.CONTEXT_ELIGIBILITY, SignalState.PASS
        elif code in {"EEPL_MINIMUM_AGE_NOT_MET", "EEPL_MAXIMUM_AGE_EXCEEDED"}:
            kind, state = SignalKind.LEGAL_ELIGIBILITY, SignalState.BLOCK
        elif code.startswith("EEPL_REQUIRED_CONTEXT_MISSING_"):
            kind, state = SignalKind.CONTEXT_ELIGIBILITY, SignalState.UNKNOWN
        elif code.endswith("_NOT_ALLOWED"):
            kind, state = SignalKind.CONTEXT_ELIGIBILITY, SignalState.BLOCK
        else:
            # Unknown policy output is not a pass.
            kind, state = SignalKind.CONTEXT_ELIGIBILITY, SignalState.UNKNOWN
        signals.append(DecisionSignal(
            signal_id=f"eepl:{result.policy_id}:{index}:{code}",
            kind=kind,
            state=state,
            reason_code=code,
            explanation=explanation,
            required=True,
            source_version=result.policy_version,
        ))
    return tuple(signals)


def _npl_signals(result: NPLDecision) -> tuple[DecisionSignal, ...]:
    if result.blocked:
        return tuple(
            DecisionSignal(
                signal_id=f"npl:{preference_id}",
                kind=SignalKind.NPL_HARD_NEGATIVE,
                state=SignalState.BLOCK,
                reason_code="NPL_HARD_NEGATIVE",
                explanation=f"Active negative preference '{preference_id}' vetoed this candidate.",
                required=True,
                source_version=result.contract_version,
            )
            for preference_id in result.hard_veto_preference_ids
        )
    return (DecisionSignal(
        signal_id="npl:no-hard-veto",
        kind=SignalKind.NPL_HARD_NEGATIVE,
        state=SignalState.PASS,
        reason_code="NPL_NO_HARD_VETO",
        explanation="NPL found no active hard exclusion for this user and candidate.",
        required=True,
        source_version=result.contract_version,
    ),)


def arbitrate_candidate(
    request: ArbitrationRequest,
    eepl_result: EEPLResult,
    npl_decision: NPLDecision,
) -> DecisionPipelineResult:
    """Compose EEPL and NPL outputs, then require a final CAL verdict."""
    if eepl_result.candidate_id != request.candidate_id:
        raise ValueError("EEPL result candidate_id does not match arbitration request")
    if npl_decision.candidate_id != request.candidate_id:
        raise ValueError("NPL decision candidate_id does not match arbitration request")
    if eepl_result.user_id != npl_decision.user_id:
        raise ValueError("EEPL and NPL results must belong to the same user")

    signals = request.signals + _eepl_signals(eepl_result) + _npl_signals(npl_decision)
    combined_request = replace(request, signals=signals)
    cal_result = arbitrate(combined_request)
    return DecisionPipelineResult(
        eepl_result=eepl_result,
        npl_decision=npl_decision,
        cal_result=cal_result,
    )
