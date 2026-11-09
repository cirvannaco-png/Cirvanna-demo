"""Offline release validator for real FCI predictions and observed fit outcomes.

This module evaluates a candidate predictor. It does not train, serve, or certify
a model. A candidate pass is only one input to independent model-risk approval.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Sequence

from .metrics import compute_calibration_metrics


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PredictiveValidationStatus(str, Enum):
    INCONCLUSIVE = "inconclusive"
    REJECTED = "rejected"
    CANDIDATE_PASS = "candidate_pass"


@dataclass(frozen=True)
class FitOutcomeObservation:
    """One out-of-time prediction joined to a subsequently observed fit outcome.

    subject_key and candidate_key must be opaque study identifiers, not account
    IDs, names, measurements, photos, or other directly identifying data.
    slices should contain only predeclared, non-sensitive evaluation dimensions
    such as market or product category.
    """

    subject_key: str
    candidate_key: str
    predicted_probability: float
    observed_fit_success: bool
    predicted_at: datetime
    outcome_observed_at: datetime
    slices: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("subject_key", "candidate_key"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty opaque key")
        if (
            isinstance(self.predicted_probability, bool)
            or not isinstance(self.predicted_probability, (int, float))
            or not isfinite(self.predicted_probability)
            or not 0.0 <= self.predicted_probability <= 1.0
        ):
            raise ValueError("predicted_probability must be finite and in [0, 1]")
        if not isinstance(self.observed_fit_success, bool):
            raise ValueError("observed_fit_success must be an observed boolean outcome")
        for name in ("predicted_at", "outcome_observed_at"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.outcome_observed_at < self.predicted_at:
            raise ValueError("fit outcome must be observed at or after prediction time")
        if not isinstance(self.slices, tuple):
            raise ValueError("slices must be a tuple")
        if any(not isinstance(item, str) or not item.strip() for item in self.slices):
            raise ValueError("slice labels must be non-empty strings")
        normalized = tuple(item.strip() for item in self.slices)
        if len(normalized) != len(set(normalized)):
            raise ValueError("slice labels must be unique")


@dataclass(frozen=True)
class PredictiveValidationPolicy:
    """Pre-registered acceptance thresholds; no universal thresholds are implied."""

    policy_version: str
    minimum_rows: int
    minimum_subjects: int
    minimum_high_confidence_rows: int
    high_confidence_threshold: float
    maximum_brier_score: float
    maximum_expected_calibration_error: float
    minimum_roc_auc: float
    maximum_high_confidence_failure_rate: float
    required_slices: tuple[str, ...] = ()
    minimum_rows_per_slice: int = 1
    calibration_bins: int = 10

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must not be empty")
        for name in ("minimum_rows", "minimum_subjects", "minimum_high_confidence_rows",
                     "minimum_rows_per_slice", "calibration_bins"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("high_confidence_threshold", "maximum_brier_score",
                     "maximum_expected_calibration_error", "minimum_roc_auc",
                     "maximum_high_confidence_failure_rate"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValueError(f"{name} must be finite and in [0, 1]")
        if not isinstance(self.required_slices, tuple):
            raise ValueError("required_slices must be a tuple")
        if any(not isinstance(item, str) or not item.strip() for item in self.required_slices):
            raise ValueError("required_slices must contain non-empty labels")
        if len(self.required_slices) != len(set(self.required_slices)):
            raise ValueError("required_slices must be unique")


@dataclass(frozen=True)
class PredictiveValidationReport:
    status: PredictiveValidationStatus
    reasons: tuple[str, ...]
    model_version: str
    model_sha256: str
    outcome_dataset_sha256: str
    policy_version: str
    training_cutoff: datetime
    sample_count: int
    subject_count: int
    metrics: dict[str, float | int | None]
    slice_metrics: dict[str, dict[str, float | int | None]]


def _roc_auc(probabilities: Sequence[float], outcomes: Sequence[bool]) -> float | None:
    positives = sum(outcomes)
    negatives = len(outcomes) - positives
    if positives == 0 or negatives == 0:
        return None

    ranked = sorted(zip(probabilities, outcomes), key=lambda item: item[0])
    positive_rank_sum = 0.0
    index = 0
    while index < len(ranked):
        end = index + 1
        while end < len(ranked) and ranked[end][0] == ranked[index][0]:
            end += 1
        average_rank = ((index + 1) + end) / 2.0
        positive_rank_sum += average_rank * sum(1 for _, label in ranked[index:end] if label)
        index = end
    return (
        positive_rank_sum - positives * (positives + 1) / 2.0
    ) / (positives * negatives)


def _metrics(
    observations: Sequence[FitOutcomeObservation],
    *,
    bins: int,
    high_confidence_threshold: float,
) -> dict[str, float | int | None]:
    probabilities = [float(item.predicted_probability) for item in observations]
    outcomes = [item.observed_fit_success for item in observations]
    calibration = compute_calibration_metrics(
        probabilities,
        outcomes,
        bins=bins,
        high_confidence_threshold=high_confidence_threshold,
    )
    return {
        "sample_count": calibration.sample_count,
        "fit_success_rate": calibration.fit_success_rate,
        "brier_score": calibration.brier_score,
        "expected_calibration_error": calibration.expected_calibration_error,
        "roc_auc": _roc_auc(probabilities, outcomes),
        "high_confidence_failure_rate": calibration.high_confidence_failure_rate,
        "high_confidence_count": sum(
            1 for probability in probabilities if probability >= high_confidence_threshold
        ),
    }


def validate_predictive_release(
    *,
    model_version: str,
    model_sha256: str,
    outcome_dataset_sha256: str,
    training_subject_keys: Sequence[str],
    training_cutoff: datetime,
    observations: Sequence[FitOutcomeObservation],
    policy: PredictiveValidationPolicy,
) -> PredictiveValidationReport:
    """Validate a candidate model on a subject-disjoint, out-of-time outcome set.

    CANDIDATE_PASS means only that this frozen evaluation set met the supplied
    policy thresholds. It does not authorize production use or CAL SHOW.
    """
    if not isinstance(model_version, str) or not model_version.strip():
        raise ValueError("model_version must not be empty")
    if not isinstance(model_sha256, str) or not _SHA256.fullmatch(model_sha256):
        raise ValueError("model_sha256 must be a lowercase SHA-256 digest")
    if not isinstance(outcome_dataset_sha256, str) or not _SHA256.fullmatch(outcome_dataset_sha256):
        raise ValueError("outcome_dataset_sha256 must be a lowercase SHA-256 digest")
    if not isinstance(training_cutoff, datetime) or training_cutoff.tzinfo is None or training_cutoff.utcoffset() is None:
        raise ValueError("training_cutoff must be timezone-aware")
    if not isinstance(policy, PredictiveValidationPolicy):
        raise ValueError("policy must be a PredictiveValidationPolicy")
    if not isinstance(training_subject_keys, (tuple, list)) or not training_subject_keys:
        raise ValueError("training_subject_keys must be a non-empty sequence")
    if any(not isinstance(item, str) or not item.strip() for item in training_subject_keys):
        raise ValueError("training_subject_keys must contain non-empty opaque keys")
    if len(training_subject_keys) != len(set(training_subject_keys)):
        raise ValueError("training_subject_keys must be unique")
    if not isinstance(observations, (tuple, list)) or not observations:
        raise ValueError("observations must be a non-empty sequence")
    if any(not isinstance(item, FitOutcomeObservation) for item in observations):
        raise ValueError("observations must contain FitOutcomeObservation values")

    training_subjects = set(training_subject_keys)
    evaluation_subjects = {item.subject_key for item in observations}
    if training_subjects & evaluation_subjects:
        raise ValueError("training and evaluation subjects must be disjoint")
    keys = [(item.subject_key, item.candidate_key, item.predicted_at) for item in observations]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate subject/candidate prediction rows are not allowed")
    if any(item.predicted_at <= training_cutoff for item in observations):
        raise ValueError("every evaluation prediction must be strictly after training_cutoff")

    global_metrics = _metrics(
        observations, bins=policy.calibration_bins,
        high_confidence_threshold=float(policy.high_confidence_threshold),
    )
    subjects = len(evaluation_subjects)
    slice_metrics: dict[str, dict[str, float | int | None]] = {}
    reasons: list[str] = []
    inconclusive = False
    rejected = False

    if len(observations) < policy.minimum_rows:
        reasons.append("INSUFFICIENT_EVALUATION_ROWS")
        inconclusive = True
    if subjects < policy.minimum_subjects:
        reasons.append("INSUFFICIENT_EVALUATION_SUBJECTS")
        inconclusive = True
    if int(global_metrics["high_confidence_count"] or 0) < policy.minimum_high_confidence_rows:
        reasons.append("INSUFFICIENT_HIGH_CONFIDENCE_OUTCOMES")
        inconclusive = True
    if global_metrics["roc_auc"] is None:
        reasons.append("BOTH_OUTCOME_CLASSES_REQUIRED")
        inconclusive = True

    for slice_name in policy.required_slices:
        subset = [item for item in observations if slice_name in item.slices]
        if len(subset) < policy.minimum_rows_per_slice:
            reasons.append(f"INSUFFICIENT_SLICE_ROWS:{slice_name}")
            inconclusive = True
            continue
        slice_result = _metrics(
            subset, bins=policy.calibration_bins,
            high_confidence_threshold=float(policy.high_confidence_threshold),
        )
        slice_metrics[slice_name] = slice_result
        if slice_result["roc_auc"] is None:
            reasons.append(f"BOTH_OUTCOME_CLASSES_REQUIRED:{slice_name}")
            inconclusive = True

    def check_thresholds(metrics: dict[str, float | int | None], prefix: str = "") -> None:
        nonlocal rejected
        checks = (
            ("brier_score", policy.maximum_brier_score, "max"),
            ("expected_calibration_error", policy.maximum_expected_calibration_error, "max"),
            ("roc_auc", policy.minimum_roc_auc, "min"),
        )
        for metric_name, threshold, direction in checks:
            value = metrics.get(metric_name)
            if value is None:
                continue
            failed = value > threshold if direction == "max" else value < threshold
            if failed:
                label = f"{prefix}{metric_name}"
                reasons.append(f"THRESHOLD_FAILED:{label}")
                rejected = True

    high_confidence_failure = global_metrics["high_confidence_failure_rate"]
    if high_confidence_failure is None:
        reasons.append("HIGH_CONFIDENCE_FAILURE_RATE_UNAVAILABLE")
        inconclusive = True
    elif high_confidence_failure > policy.maximum_high_confidence_failure_rate:
        reasons.append("THRESHOLD_FAILED:high_confidence_failure_rate")
        rejected = True

    check_thresholds(global_metrics)
    for slice_name, metrics in slice_metrics.items():
        check_thresholds(metrics, prefix=f"{slice_name}:")

    if inconclusive:
        status = PredictiveValidationStatus.INCONCLUSIVE
    elif rejected:
        status = PredictiveValidationStatus.REJECTED
    else:
        status = PredictiveValidationStatus.CANDIDATE_PASS
        reasons.append("POLICY_THRESHOLDS_MET_NOT_PRODUCTION_APPROVAL")

    return PredictiveValidationReport(
        status=status,
        reasons=tuple(reasons),
        model_version=model_version,
        model_sha256=model_sha256,
        outcome_dataset_sha256=outcome_dataset_sha256,
        policy_version=policy.policy_version,
        training_cutoff=training_cutoff,
        sample_count=len(observations),
        subject_count=subjects,
        metrics=global_metrics,
        slice_metrics=slice_metrics,
    )
