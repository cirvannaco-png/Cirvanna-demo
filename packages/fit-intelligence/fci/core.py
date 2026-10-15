"""Fit Confidence Index (FCI) calibrated-estimate contract.

This is a model boundary, not a trained fit predictor. It accepts an upstream
estimate only with explicit provenance and calibration metadata. Uncalibrated
estimates become UNKNOWN signals so CAL cannot mistake them for a pass.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

CONTRACT_VERSION = "1.0.0"


@dataclass(frozen=True)
class FitConfidenceEstimate:
    estimate_id: str
    user_id: str
    candidate_id: str
    model_version: str
    calibrated: bool
    confidence: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    calibration_version: str | None = None
    evidence_ids: tuple[str, ...] = ()
    interval_level: float = 0.95

    def __post_init__(self) -> None:
        for name in ("estimate_id", "user_id", "candidate_id", "model_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.evidence_ids, tuple):
            raise ValueError("evidence_ids must be a tuple")
        if any(not isinstance(item, str) or not item.strip() for item in self.evidence_ids):
            raise ValueError("evidence IDs must be non-empty strings")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evidence IDs must be unique")
        if not isfinite(self.interval_level) or not 0.0 < self.interval_level < 1.0:
            raise ValueError("interval_level must be between 0 and 1")
        for name in ("confidence", "lower_bound", "upper_bound"):
            value = getattr(self, name)
            if value is not None and (not isfinite(value) or not 0.0 <= value <= 1.0):
                raise ValueError(f"{name} must be finite and between 0 and 1")
        if self.calibrated:
            if self.confidence is None or self.lower_bound is None or self.upper_bound is None:
                raise ValueError("calibrated estimates require confidence and interval bounds")
            if not isinstance(self.calibration_version, str) or not self.calibration_version.strip():
                raise ValueError("calibrated estimates require calibration_version")
            if not self.evidence_ids:
                raise ValueError("calibrated estimates require evidence provenance")
            if self.lower_bound > self.confidence or self.confidence > self.upper_bound:
                raise ValueError("confidence must lie within its interval")
        elif self.calibration_version is not None and not self.calibration_version.strip():
            raise ValueError("calibration_version must be non-empty or None")

    @property
    def interval_width(self) -> float | None:
        if self.lower_bound is None or self.upper_bound is None:
            return None
        return self.upper_bound - self.lower_bound

    def to_cal_signal(self):
        """Map this estimate to a typed CAL signal without authorizing display."""
        from catacaci import DecisionSignal, SignalKind, SignalState

        if not self.calibrated:
            return DecisionSignal(
                signal_id=f"fci:{self.estimate_id}:{self.candidate_id}",
                kind=SignalKind.FIT_CONFIDENCE,
                state=SignalState.UNKNOWN,
                reason_code="FCI_UNCALIBRATED_ESTIMATE",
                explanation="Fit estimate is not calibrated; CAL must route the candidate to review.",
                required=True,
                confidence=None,
                source_version=f"{CONTRACT_VERSION}:{self.model_version}:uncalibrated",
            )
        return DecisionSignal(
            signal_id=f"fci:{self.estimate_id}",
            kind=SignalKind.FIT_CONFIDENCE,
            state=SignalState.PASS,
            reason_code="FCI_CALIBRATED_ESTIMATE",
            explanation=(
                f"Calibrated fit confidence {self.confidence:.3f}; "
                f"{self.interval_level:.0%} interval [{self.lower_bound:.3f}, {self.upper_bound:.3f}] "
                f"from model {self.model_version} / calibration {self.calibration_version}."
            ),
            required=True,
            confidence=self.confidence,
            source_version=f"{CONTRACT_VERSION}:{self.model_version}:{self.calibration_version}",
        )
