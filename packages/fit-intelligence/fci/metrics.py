"""Offline fit-confidence calibration metrics.

These metrics evaluate predictions against subsequently observed outcomes. They
are not a fit predictor, calibration model, or authorization signal. CAL must
continue to treat FCI as UNKNOWN unless a separately validated provider supplies
calibrated estimates with provenance.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence


@dataclass(frozen=True)
class CalibrationMetrics:
    """Aggregate metrics for a fixed, outcome-labelled evaluation cohort."""

    sample_count: int
    brier_score: float
    expected_calibration_error: float
    fit_success_rate: float
    high_confidence_failure_rate: float | None
    mean_interval_width: float | None


def compute_calibration_metrics(
    predictions: Sequence[float],
    outcomes: Sequence[bool],
    *,
    interval_widths: Sequence[float] | None = None,
    bins: int = 10,
    high_confidence_threshold: float = 0.8,
) -> CalibrationMetrics:
    """Compute Brier score, equal-width ECE, success rate and failure rate.

    Predictions must be probabilities in [0, 1] and outcomes must be observed
    binary fit outcomes. Inputs must come from the same fixed cohort; do not mix
    simulated labels with observed outcomes. Interval widths are optional and,
    when supplied, must align one-to-one with the cohort.

    Empty cohorts and malformed inputs raise ValueError rather than returning
    apparently valid zero-valued metrics.
    """
    if len(predictions) == 0:
        raise ValueError("at least one labelled prediction is required")
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must have equal lengths")
    if not isinstance(bins, int) or isinstance(bins, bool) or bins < 1:
        raise ValueError("bins must be a positive integer")
    if (
        not isinstance(high_confidence_threshold, (int, float))
        or isinstance(high_confidence_threshold, bool)
        or not isfinite(high_confidence_threshold)
        or not 0.0 <= high_confidence_threshold <= 1.0
    ):
        raise ValueError("high_confidence_threshold must be finite and in [0, 1]")

    probabilities: list[float] = []
    labels: list[float] = []
    for probability, outcome in zip(predictions, outcomes):
        if (
            not isinstance(probability, (int, float))
            or isinstance(probability, bool)
            or not isfinite(probability)
            or not 0.0 <= probability <= 1.0
        ):
            raise ValueError("every prediction must be finite and in [0, 1]")
        if not isinstance(outcome, bool):
            raise ValueError("every outcome must be a boolean observed label")
        probabilities.append(float(probability))
        labels.append(1.0 if outcome else 0.0)

    widths: list[float] | None = None
    if interval_widths is not None:
        if len(interval_widths) != len(probabilities):
            raise ValueError("interval_widths must align with predictions")
        widths = []
        for width in interval_widths:
            if (
                not isinstance(width, (int, float))
                or isinstance(width, bool)
                or not isfinite(width)
                or not 0.0 <= width <= 1.0
            ):
                raise ValueError("every interval width must be finite and in [0, 1]")
            widths.append(float(width))

    count = len(probabilities)
    brier = sum((p - y) ** 2 for p, y in zip(probabilities, labels)) / count

    # Equal-width bins; the rightmost bin includes probability 1.0.
    bin_counts = [0] * bins
    bin_confidence = [0.0] * bins
    bin_accuracy = [0.0] * bins
    for probability, label in zip(probabilities, labels):
        index = min(int(probability * bins), bins - 1)
        bin_counts[index] += 1
        bin_confidence[index] += probability
        bin_accuracy[index] += label

    ece = 0.0
    for index, bin_count in enumerate(bin_counts):
        if not bin_count:
            continue
        mean_confidence = bin_confidence[index] / bin_count
        mean_accuracy = bin_accuracy[index] / bin_count
        ece += (bin_count / count) * abs(mean_accuracy - mean_confidence)

    high_confidence = [
        label
        for probability, label in zip(probabilities, labels)
        if probability >= high_confidence_threshold
    ]
    failure_rate = (
        sum(1.0 - label for label in high_confidence) / len(high_confidence)
        if high_confidence
        else None
    )

    return CalibrationMetrics(
        sample_count=count,
        brier_score=brier,
        expected_calibration_error=ece,
        fit_success_rate=sum(labels) / count,
        high_confidence_failure_rate=failure_rate,
        mean_interval_width=(sum(widths) / len(widths)) if widths is not None else None,
    )
