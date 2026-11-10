"""Model provenance and policy-specific validation/readiness contracts."""
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

class MetricDirection(StrEnum):
    MINIMUM = "minimum"
    MAXIMUM = "maximum"

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
class MetricThreshold:
    name: str
    population: str
    direction: MetricDirection
    threshold: float
    def __post_init__(self) -> None:
        for field_name in ("name", "population"):
            object.__setattr__(self, field_name, _required_text(getattr(self, field_name), field_name, max_length=160))
        if not isinstance(self.direction, MetricDirection):
            raise ValueError("direction must be a MetricDirection")
        if isinstance(self.threshold, bool) or not isinstance(self.threshold, (int, float)) or not isfinite(self.threshold):
            raise ValueError("metric threshold must be finite")

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
        if not isinstance(self.evaluated_populations, tuple) or any(not isinstance(item, str) or not item.strip() for item in self.evaluated_populations):
            raise ValueError("evaluated_populations must be a tuple of non-empty population identifiers")
        if len(self.evaluated_populations) != len(set(self.evaluated_populations)):
            raise ValueError("evaluated_populations must not contain duplicates")
        if not isinstance(self.metrics, tuple) or any(not isinstance(item, ModelMetric) for item in self.metrics):
            raise ValueError("metrics must be a tuple of ModelMetric values")
        metric_keys = [(item.name, item.population) for item in self.metrics]
        if len(metric_keys) != len(set(metric_keys)):
            raise ValueError("model metrics must be unique by name and population")
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
            if any(metric.population not in self.evaluated_populations for metric in self.metrics):
                raise ValueError("each metric population must be listed among evaluated populations")
        if self.status is ModelValidationStatus.INDEPENDENTLY_VALIDATED:
            if not self.independent_reviewer:
                raise ValueError("independent validation requires an identified reviewer or institution")
            if not self.calibration_method or self.expected_calibration_error is None or self.brier_score is None:
                raise ValueError("independent validation requires calibration method, ECE, and Brier score")

@dataclass(frozen=True)
class ModelReadinessPolicy:
    """Task-specific release thresholds; no universal beauty-model cutoff exists."""
    policy_id: str
    task: str
    intended_use: DataPurpose
    required_populations: tuple[str, ...]
    metric_thresholds: tuple[MetricThreshold, ...]
    maximum_expected_calibration_error: float
    maximum_brier_score: float
    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _required_text(self.policy_id, "policy_id", max_length=160))
        object.__setattr__(self, "task", _required_text(self.task, "task", max_length=240))
        if not isinstance(self.intended_use, DataPurpose):
            raise ValueError("intended_use must be a DataPurpose")
        if not isinstance(self.required_populations, tuple) or not self.required_populations:
            raise ValueError("required_populations must be a non-empty tuple")
        normalized_populations = tuple(_required_text(item, "required_population", max_length=160) for item in self.required_populations)
        if len(normalized_populations) != len(set(normalized_populations)):
            raise ValueError("required_populations must be unique")
        object.__setattr__(self, "required_populations", normalized_populations)
        if not isinstance(self.metric_thresholds, tuple) or not self.metric_thresholds:
            raise ValueError("metric_thresholds must be a non-empty tuple")
        if any(not isinstance(item, MetricThreshold) for item in self.metric_thresholds):
            raise ValueError("metric_thresholds must contain MetricThreshold values")
        threshold_keys = [(item.name, item.population) for item in self.metric_thresholds]
        if len(threshold_keys) != len(set(threshold_keys)):
            raise ValueError("metric threshold pairs must be unique")
        for name in ("maximum_expected_calibration_error", "maximum_brier_score"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and between 0 and 1")
        if any(item.population not in normalized_populations for item in self.metric_thresholds):
            raise ValueError("metric thresholds must target required populations")

@dataclass(frozen=True)
class ModelReadinessResult:
    policy_id: str
    eligible: bool
    reason_codes: tuple[str, ...]

def assess_model_readiness(card: ModelValidationCard, policy: ModelReadinessPolicy) -> ModelReadinessResult:
    """Evaluate one immutable model card against an explicit task release policy."""
    if not isinstance(card, ModelValidationCard) or not isinstance(policy, ModelReadinessPolicy):
        raise ValueError("card and policy must be validated CIL contracts")
    reasons: list[str] = []
    if card.status is not ModelValidationStatus.INDEPENDENTLY_VALIDATED:
        reasons.append("MODEL_NOT_INDEPENDENTLY_VALIDATED")
    if card.task != policy.task:
        reasons.append("MODEL_TASK_MISMATCH")
    if policy.intended_use not in card.intended_uses:
        reasons.append("MODEL_INTENDED_USE_NOT_APPROVED")
    if set(policy.required_populations) - set(card.evaluated_populations):
        reasons.append("REQUIRED_POPULATION_NOT_EVALUATED")
    if card.expected_calibration_error is None or card.expected_calibration_error > policy.maximum_expected_calibration_error:
        reasons.append("EXPECTED_CALIBRATION_ERROR_THRESHOLD_NOT_MET")
    if card.brier_score is None or card.brier_score > policy.maximum_brier_score:
        reasons.append("BRIER_SCORE_THRESHOLD_NOT_MET")
    metric_index = {(metric.name, metric.population): metric for metric in card.metrics}
    for threshold in policy.metric_thresholds:
        metric = metric_index.get((threshold.name, threshold.population))
        if metric is None:
            reasons.append("REQUIRED_MODEL_METRIC_MISSING")
        elif threshold.direction is MetricDirection.MINIMUM and metric.value < threshold.threshold:
            reasons.append("MODEL_METRIC_MINIMUM_NOT_MET")
        elif threshold.direction is MetricDirection.MAXIMUM and metric.value > threshold.threshold:
            reasons.append("MODEL_METRIC_MAXIMUM_EXCEEDED")
    normalized_reasons = tuple(sorted(set(reasons)))
    return ModelReadinessResult(policy.policy_id, not normalized_reasons, normalized_reasons)
