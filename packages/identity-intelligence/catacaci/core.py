"""Deterministic CaTaCaCi/CAL arbitration core.

This implements decision governance, not ranking or recommendation. It consumes
precomputed signals and returns an explainable, fail-closed verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Iterable

CONTRACT_VERSION = "1.1.0"


class SignalState(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    UNKNOWN = "unknown"


class DecisionVerdict(str, Enum):
    SHOW = "show"
    BLOCK = "block"
    REVIEW = "review"


class SignalKind(str, Enum):
    SAFETY = "safety"
    LEGAL_ELIGIBILITY = "legal_eligibility"
    USER_HARD_CONSTRAINT = "user_hard_constraint"
    NPL_HARD_NEGATIVE = "npl_hard_negative"
    CULTURAL_REQUIREMENT = "cultural_requirement"
    CONTEXT_ELIGIBILITY = "context_eligibility"
    IDENTITY_ALIGNMENT = "identity_alignment"
    FIT_CONFIDENCE = "fit_confidence"
    OTHER = "other"


_PRECEDENCE = {
    SignalKind.SAFETY: 0,
    SignalKind.LEGAL_ELIGIBILITY: 1,
    SignalKind.USER_HARD_CONSTRAINT: 2,
    SignalKind.NPL_HARD_NEGATIVE: 3,
    SignalKind.CULTURAL_REQUIREMENT: 4,
    SignalKind.CONTEXT_ELIGIBILITY: 5,
    SignalKind.IDENTITY_ALIGNMENT: 6,
    SignalKind.FIT_CONFIDENCE: 7,
    SignalKind.OTHER: 8,
}

# A candidate may be shown only after every configured gate has supplied evidence.
# Upstream services should return PASS when a gate applies but no rule applies.
_DEFAULT_REQUIRED_KINDS = (
    SignalKind.SAFETY,
    SignalKind.LEGAL_ELIGIBILITY,
    SignalKind.USER_HARD_CONSTRAINT,
    SignalKind.NPL_HARD_NEGATIVE,
    SignalKind.CULTURAL_REQUIREMENT,
    SignalKind.CONTEXT_ELIGIBILITY,
    SignalKind.IDENTITY_ALIGNMENT,
    SignalKind.FIT_CONFIDENCE,
)


@dataclass(frozen=True)
class DecisionSignal:
    """A typed upstream signal; missing/unknown evidence is never a pass."""
    signal_id: str
    kind: SignalKind
    state: SignalState
    reason_code: str
    explanation: str
    required: bool = True
    confidence: float | None = None
    source_version: str = "unspecified"

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SignalKind):
            raise ValueError("kind must be a SignalKind")
        if not isinstance(self.state, SignalState):
            raise ValueError("state must be a SignalState")
        if not isinstance(self.signal_id, str) or not self.signal_id.strip():
            raise ValueError("signal_id must not be empty")
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ValueError("reason_code must not be empty")
        if not isinstance(self.explanation, str) or not self.explanation.strip():
            raise ValueError("explanation must not be empty")
        if self.confidence is not None:
            if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
                raise ValueError("confidence must be finite and between 0 and 1")
        if not isinstance(self.source_version, str) or not self.source_version.strip():
            raise ValueError("source_version must not be empty")


@dataclass(frozen=True)
class ArbitrationRequest:
    request_id: str
    candidate_id: str
    signals: tuple[DecisionSignal, ...]
    minimum_fit_confidence: float = 0.70
    policy_version: str = "1.1.0"
    required_kinds: tuple[SignalKind, ...] = _DEFAULT_REQUIRED_KINDS
    maximum_fit_confidence_disagreement: float = 0.10
    require_fit_confidence: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id must not be empty")
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise ValueError("candidate_id must not be empty")
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must not be empty")
        if not isinstance(self.signals, tuple):
            raise ValueError("signals must be a tuple")
        if not isinstance(self.required_kinds, tuple):
            raise ValueError("required_kinds must be a tuple")
        if any(not isinstance(kind, SignalKind) for kind in self.required_kinds):
            raise ValueError("required_kinds must contain only SignalKind values")
        if len(self.required_kinds) != len(set(self.required_kinds)):
            raise ValueError("required_kinds must not contain duplicates")
        if not isfinite(self.minimum_fit_confidence) or not 0 <= self.minimum_fit_confidence <= 1:
            raise ValueError("minimum_fit_confidence must be finite and between 0 and 1")
        if not isinstance(self.require_fit_confidence, bool):
            raise ValueError("require_fit_confidence must be a boolean")
        if (
            not isfinite(self.maximum_fit_confidence_disagreement)
            or not 0 <= self.maximum_fit_confidence_disagreement <= 1
        ):
            raise ValueError(
                "maximum_fit_confidence_disagreement must be finite and between 0 and 1"
            )
        ids = [signal.signal_id for signal in self.signals]
        if len(ids) != len(set(ids)):
            raise ValueError("signal_id values must be unique within a request")


@dataclass(frozen=True)
class ArbitrationReason:
    code: str
    signal_id: str | None
    explanation: str


@dataclass(frozen=True)
class ArbitrationResult:
    contract_version: str
    request_id: str
    candidate_id: str
    verdict: DecisionVerdict
    reasons: tuple[ArbitrationReason, ...]
    evaluated_signal_ids: tuple[str, ...]
    policy_version: str

    @property
    def may_display(self) -> bool:
        """Only an explicit SHOW verdict authorizes display."""
        return self.verdict is DecisionVerdict.SHOW


def _ordered(signals: Iterable[DecisionSignal]) -> list[DecisionSignal]:
    return sorted(signals, key=lambda signal: (_PRECEDENCE[signal.kind], signal.signal_id))


def arbitrate(request: ArbitrationRequest) -> ArbitrationResult:
    """Return a deterministic, explainable CAL verdict.

    Hard blocks dominate all scores. Required unknowns and insufficient or
    conflicting fit evidence produce REVIEW. Scores are never summed, and
    REVIEW never authorizes display.
    """
    signals = _ordered(request.signals)
    hard_blocks = [
        signal for signal in signals
        if signal.state is SignalState.BLOCK
        and signal.kind in {
            SignalKind.SAFETY,
            SignalKind.LEGAL_ELIGIBILITY,
            SignalKind.USER_HARD_CONSTRAINT,
            SignalKind.NPL_HARD_NEGATIVE,
            SignalKind.CULTURAL_REQUIREMENT,
            SignalKind.CONTEXT_ELIGIBILITY,
        }
    ]
    if hard_blocks:
        reasons = [
            ArbitrationReason(signal.reason_code, signal.signal_id, signal.explanation)
            for signal in hard_blocks
        ]
        return _result(request, DecisionVerdict.BLOCK, reasons, signals)

    non_veto_blocks = [
        signal for signal in signals
        if signal.state is SignalState.BLOCK
    ]
    if non_veto_blocks:
        return _result(request, DecisionVerdict.REVIEW, [
            ArbitrationReason(
                "NON_VETO_SIGNAL_BLOCKED",
                signal.signal_id,
                f"{signal.kind.value}: {signal.explanation}",
            )
            for signal in non_veto_blocks
        ], signals)

    present_kinds = {signal.kind for signal in signals}
    missing_required_kinds = [
        kind for kind in request.required_kinds
        if kind is not SignalKind.FIT_CONFIDENCE and kind not in present_kinds
    ]
    if missing_required_kinds:
        return _result(request, DecisionVerdict.REVIEW, [
            ArbitrationReason(
                "REQUIRED_SIGNAL_MISSING",
                None,
                f"Required gate '{kind.value}' supplied no evidence; display is not authorized.",
            )
            for kind in missing_required_kinds
        ], signals)

    required_kinds = set(request.required_kinds)
    unknown_required = [
        signal for signal in signals
        if (signal.required or signal.kind in required_kinds)
        and signal.state is SignalState.UNKNOWN
    ]
    if unknown_required:
        reasons = [
            ArbitrationReason(
                "REQUIRED_SIGNAL_UNKNOWN",
                signal.signal_id,
                f"{signal.kind.value}: {signal.explanation}",
            )
            for signal in unknown_required
        ]
        return _result(request, DecisionVerdict.REVIEW, reasons, signals)

    fit_signals = [signal for signal in signals if signal.kind is SignalKind.FIT_CONFIDENCE]
    if request.require_fit_confidence:
        if not fit_signals:
            return _result(request, DecisionVerdict.REVIEW, [
                ArbitrationReason(
                    "FIT_CONFIDENCE_MISSING",
                    None,
                    "No fit-confidence signal was supplied; display is not authorized.",
                )
            ], signals)

        unavailable = [signal for signal in fit_signals if signal.confidence is None]
        if unavailable:
            return _result(request, DecisionVerdict.REVIEW, [
                ArbitrationReason(
                    "FIT_CONFIDENCE_UNAVAILABLE",
                    signal.signal_id,
                    "Fit-confidence signal has no calibrated confidence value.",
                )
                for signal in unavailable
            ], signals)

        values = [float(signal.confidence) for signal in fit_signals if signal.confidence is not None]
        if max(values) - min(values) > request.maximum_fit_confidence_disagreement:
            return _result(request, DecisionVerdict.REVIEW, [
                ArbitrationReason(
                    "FIT_CONFIDENCE_DISAGREEMENT",
                    signal.signal_id,
                    "Fit-confidence sources disagree by more than "
                    f"{request.maximum_fit_confidence_disagreement:.3f}; review is required.",
                )
                for signal in fit_signals
            ], signals)

        below = [
            signal for signal in fit_signals
            if signal.confidence is not None
            and signal.confidence < request.minimum_fit_confidence
        ]
        if below:
            return _result(request, DecisionVerdict.REVIEW, [
                ArbitrationReason(
                    "FIT_CONFIDENCE_BELOW_THRESHOLD",
                    signal.signal_id,
                    f"Fit confidence {signal.confidence:.3f} is below threshold "
                    f"{request.minimum_fit_confidence:.3f}.",
                )
                for signal in below
            ], signals)

    # Product-only decisions may explicitly waive physical fit confidence. This
    # does not waive any other required gate or turn unknown evidence into PASS.
    return _result(request, DecisionVerdict.SHOW, [
        ArbitrationReason(
            "ALL_REQUIRED_GATES_PASSED",
            None,
            "No hard veto or required unknown remains; all gates required by the decision profile passed.",
        )
    ], signals)


def _result(
    request: ArbitrationRequest,
    verdict: DecisionVerdict,
    reasons: list[ArbitrationReason],
    signals: list[DecisionSignal],
) -> ArbitrationResult:
    return ArbitrationResult(
        contract_version=CONTRACT_VERSION,
        request_id=request.request_id,
        candidate_id=request.candidate_id,
        verdict=verdict,
        reasons=tuple(reasons),
        evaluated_signal_ids=tuple(signal.signal_id for signal in signals),
        policy_version=request.policy_version,
    )
