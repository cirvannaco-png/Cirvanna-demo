"""Evidence-coverage gate for fit confidence signals.

This module does not estimate fit or calibrate a model. It makes evidence
coverage explicit and downgrades a model estimate to UNKNOWN when required
inputs are missing or the estimate is not calibrated.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from catacaci import DecisionSignal, SignalKind, SignalState
from .core import FitConfidenceEstimate

CONFIDENCE_ENGINE_VERSION = "1.0.0"


class ConfidenceStatus(str, Enum):
    READY = "ready"
    UNCALIBRATED = "uncalibrated"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class ConfidenceAssessment:
    contract_version: str
    estimate: FitConfidenceEstimate
    status: ConfidenceStatus
    coverage_ratio: float
    required_fields: tuple[str, ...]
    observed_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    minimum_coverage: float
    reason_code: str

    def to_cal_signal(self) -> DecisionSignal:
        """Return a typed CAL signal; only ready evidence can carry a score."""
        if self.status is not ConfidenceStatus.READY:
            reason_map = {
                ConfidenceStatus.UNCALIBRATED: (
                    "FCI_UNCALIBRATED_ESTIMATE",
                    "Fit estimate lacks validated calibration evidence; review is required.",
                ),
                ConfidenceStatus.INSUFFICIENT_EVIDENCE: (
                    "FCI_INSUFFICIENT_EVIDENCE_COVERAGE",
                    "Required fit evidence is missing or coverage is below the configured threshold; review is required.",
                ),
            }
            code, explanation = reason_map[self.status]
            return DecisionSignal(
                signal_id=f"fci:{self.estimate.estimate_id}:{self.estimate.candidate_id}",
                kind=SignalKind.FIT_CONFIDENCE,
                state=SignalState.UNKNOWN,
                reason_code=code,
                explanation=explanation,
                required=True,
                confidence=None,
                source_version=(
                    f"{self.contract_version}:{self.estimate.model_version}:"
                    f"{self.status.value}"
                ),
            )

        upstream = self.estimate.to_cal_signal()
        return DecisionSignal(
            signal_id=upstream.signal_id,
            kind=upstream.kind,
            state=upstream.state,
            reason_code=upstream.reason_code,
            explanation=(
                f"{upstream.explanation} Evidence coverage "
                f"{self.coverage_ratio:.3f} "
                f"({len(self.required_fields) - len(self.missing_fields)}/"
                f"{len(self.required_fields)} required fields)."
            ),
            required=upstream.required,
            confidence=upstream.confidence,
            source_version=(
                f"{self.contract_version}:{upstream.source_version}:"
                f"coverage-{self.coverage_ratio:.3f}"
            ),
        )


def assess_fit_confidence(
    estimate: FitConfidenceEstimate,
    *,
    required_fields: tuple[str, ...],
    observed_fields: tuple[str, ...],
    minimum_coverage: float = 1.0,
) -> ConfidenceAssessment:
    """Assess input coverage and calibration before producing a CAL signal.

    Field names represent non-sensitive evidence categories (for example,
    body_measurements or garment_size_chart), not raw measurements.
    No required-field declaration is treated as insufficient evidence.
    """
    if not isinstance(estimate, FitConfidenceEstimate):
        raise ValueError("estimate must be a FitConfidenceEstimate")
    if not isinstance(required_fields, tuple) or not isinstance(observed_fields, tuple):
        raise ValueError("required_fields and observed_fields must be tuples")
    for collection_name, values in (
        ("required_fields", required_fields),
        ("observed_fields", observed_fields),
    ):
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"{collection_name} must contain non-empty strings")
        normalized = [value.strip().casefold() for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{collection_name} must not contain duplicates")
    if (
        not isinstance(minimum_coverage, (int, float))
        or isinstance(minimum_coverage, bool)
        or not isfinite(minimum_coverage)
        or not 0.0 < minimum_coverage <= 1.0
    ):
        raise ValueError("minimum_coverage must be finite and in (0, 1]")

    required = tuple(sorted({value.strip().casefold() for value in required_fields}))
    observed = tuple(sorted({value.strip().casefold() for value in observed_fields}))
    observed_set = set(observed)
    missing = tuple(value for value in required if value not in observed_set)
    coverage = (len(required) - len(missing)) / len(required) if required else 0.0

    if not required or coverage < minimum_coverage:
        status = ConfidenceStatus.INSUFFICIENT_EVIDENCE
        reason_code = "FCI_INSUFFICIENT_EVIDENCE_COVERAGE"
    elif not estimate.calibrated:
        status = ConfidenceStatus.UNCALIBRATED
        reason_code = "FCI_UNCALIBRATED_ESTIMATE"
    else:
        status = ConfidenceStatus.READY
        reason_code = "FCI_CONFIDENCE_EVIDENCE_READY"

    return ConfidenceAssessment(
        contract_version=CONFIDENCE_ENGINE_VERSION,
        estimate=estimate,
        status=status,
        coverage_ratio=coverage,
        required_fields=required,
        observed_fields=observed,
        missing_fields=missing,
        minimum_coverage=float(minimum_coverage),
        reason_code=reason_code,
    )
