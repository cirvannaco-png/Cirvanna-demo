"""Model provenance and validation-card contracts."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from .source_registry import DataPurpose, _required_text


class ModelValidationStatus(StrEnum):
    UNVALIDATED = "unvalidated"
    INTERNALLY_VALIDATED = "internally_validated"
    INDEPENDENTLY_VALIDATED = "independently_validated"
    DEPRECATED = "deprecated"


@dataclass(frozen=True)
class ModelMetric:
    name: str
    value: float
    population: str
    sample_size: int

    def __post_init__(self) -> None:
        for name in ("name", "population"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name, max_length=160))
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)) or not isfinite(self.value):
            raise ValueError("metric value must be finite")
        if not isinstance(self.sample_size, int) or isinstance(self.sample_size, bool) or self.sample_size < 1:
            raise ValueError("metric sample_size must be a positive integer")


@dataclass(frozen=True)
class ModelValidationCard:
    model_id: str
    model_version: str
    provider: str
    task: str
    status: ModelValidationStatus
    intended_uses: tuple[DataPurpose, ...]
    evaluated_populations: tuple[str, ...] = ()
    metrics: tuple[ModelMetric, ...] = ()
    validation_dataset_reference: str | None = None
    validation_report_reference: str | None = None
    independent_reviewer: str | None = None
    calibration_method: str | None = None
    expected_calibration_error: float | None = None
    brier_score: float | None = None
    known_limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("model_id", "model_version", "provider", "task"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name, max_length=240))
        if not isinstance(self.status, ModelValidationStatus):
            raise ValueError("status must be a ModelValidationStatus")
        if not isinstance(self.intended_uses, tuple) or any(not isinstance(item, DataPurpose) for item in self.intended_uses):
            raise ValueError("intended_uses must be a tuple of DataPurpose values")
        if len(self.intended_uses) != len(set(self.intended_uses)):
            raise ValueError("intended_uses must not contain duplicates")
        if not isinstance(self.evaluated_populations, tuple) or not isinstance(self.metrics, tuple):
            raise ValueError("evaluated_populations and metrics must be tuples")
        if any(not isinstance(item, ModelMetric) for item in self.metrics):
            raise ValueError("metrics must contain ModelMetric values")
        if not isinstance(self.known_limitations, tuple) or any(not isinstance(item, str) or not item.strip() for item in self.known_limitations):
            raise ValueError("known_limitations must be a tuple of non-empty strings")
        for name in ("validation_dataset_reference", "validation_report_reference", "independent_reviewer", "calibration_method"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _required_text(value, name, max_length=500))
        for name in ("expected_calibration_error", "brier_score"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not isfinite(value) or not 0.0 <= value <= 1.0
            ):
                raise ValueError(f"{name} must be finite and between 0 and 1")

        if self.status in {ModelValidationStatus.INTERNALLY_VALIDATED, ModelValidationStatus.INDEPENDENTLY_VALIDATED}:
            if not self.validation_dataset_reference or not self.validation_report_reference:
                raise ValueError("validated models require dataset and validation-report references")
            if not self.evaluated_populations or not self.metrics or not self.known_limitations:
                raise ValueError("validated models require evaluated populations, metrics, and known limitations")
        if self.status is ModelValidationStatus.INDEPENDENTLY_VALIDATED:
            if not self.independent_reviewer:
                raise ValueError("independent validation requires an identified reviewer or institution")
            if not self.calibration_method or self.expected_calibration_error is None or self.brier_score is None:
                raise ValueError("independent validation requires calibration method, ECE, and Brier score")

    @property
    def eligible_for_user_facing_assessment(self) -> bool:
        """Fail closed unless independent validation and calibration are recorded."""
        return (
            self.status is ModelValidationStatus.INDEPENDENTLY_VALIDATED
            and self.calibration_method is not None
            and self.expected_calibration_error is not None
            and self.brier_score is not None
            and bool(self.evaluated_populations)
            and DataPurpose.COMMERCIAL_RECOMMENDATION in self.intended_uses
        )
