"""Deterministic offline DSI colour-model evaluation and release gating."""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Any, Iterable

import numpy as np

from app.color_calibration import delta_e_2000

from .schema import (
    ColorValidationSample,
    EvaluationManifest,
    ReleasePolicy,
)


class EvaluationInputError(ValueError):
    """Dataset records cannot support a valid evaluation."""


def _lab_tuple(value) -> tuple[float, float, float]:
    return (value.l_star, value.a_star, value.b_star)


def _record_error(record: ColorValidationSample) -> float | None:
    if record.prediction_status != "completed" or record.predicted_lab_d50 is None:
        return None
    return delta_e_2000(
        _lab_tuple(record.reference_lab_d50),
        _lab_tuple(record.predicted_lab_d50),
    )


def _percentile_summary(values: Iterable[float]) -> dict[str, float] | None:
    materialized = np.asarray(list(values), dtype=np.float64)
    if materialized.size == 0:
        return None
    if not np.isfinite(materialized).all():
        raise EvaluationInputError("evaluation metric contains a non-finite value")
    return {
        "count": int(materialized.size),
        "mean": round(float(np.mean(materialized)), 6),
        "median": round(float(np.median(materialized)), 6),
        "p95": round(float(np.percentile(materialized, 95)), 6),
        "maximum": round(float(np.max(materialized)), 6),
    }


def _summarize(records: list[ColorValidationSample]) -> dict[str, Any]:
    errors: list[float] = []
    l_bias: list[float] = []
    a_bias: list[float] = []
    b_bias: list[float] = []
    fit_p95: list[float] = []
    reference_uncertainty: list[float] = []

    for record in records:
        reference_uncertainty.append(record.reference_uncertainty_delta_e_2000)
        error = _record_error(record)
        if error is None:
            continue
        errors.append(error)
        assert record.predicted_lab_d50 is not None
        l_bias.append(record.predicted_lab_d50.l_star - record.reference_lab_d50.l_star)
        a_bias.append(record.predicted_lab_d50.a_star - record.reference_lab_d50.a_star)
        b_bias.append(record.predicted_lab_d50.b_star - record.reference_lab_d50.b_star)
        if record.chart_fit_p95_delta_e_2000 is not None:
            fit_p95.append(record.chart_fit_p95_delta_e_2000)

    completed = len(errors)
    failed = len(records) - completed
    total = len(records)
    return {
        "n_total": total,
        "n_completed": completed,
        "n_failed": failed,
        "failure_rate": round(failed / total, 6) if total else None,
        "delta_e_2000": _percentile_summary(errors),
        "signed_bias": {
            "l_star": round(float(np.mean(l_bias)), 6) if l_bias else None,
            "a_star": round(float(np.mean(a_bias)), 6) if a_bias else None,
            "b_star": round(float(np.mean(b_bias)), 6) if b_bias else None,
        },
        "absolute_mean_bias": {
            "l_star": round(abs(float(np.mean(l_bias))), 6) if l_bias else None,
            "a_star": round(abs(float(np.mean(a_bias))), 6) if a_bias else None,
            "b_star": round(abs(float(np.mean(b_bias))), 6) if b_bias else None,
        },
        "chart_fit_p95_delta_e_2000": (
            round(float(np.percentile(fit_p95, 95)), 6) if fit_p95 else None
        ),
        "reference_instrument_uncertainty_delta_e_2000": _percentile_summary(reference_uncertainty),
    }


def _reference_lightness_bin(l_star: float) -> str:
    lower = min(int(l_star // 20) * 20, 80)
    upper = lower + 20
    return f"{lower:02d}-{upper:02d}"


def _slice_summaries(
    records: list[ColorValidationSample],
    *,
    min_samples: int | None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    dimensions: dict[str, dict[str, list[ColorValidationSample]]] = {
        "region": defaultdict(list),
        "camera": defaultdict(list),
        "lighting": defaultdict(list),
        "reference_l_star_bin": defaultdict(list),
        "operating_system": defaultdict(list),
        "chart_condition": defaultdict(list),
        "reference_instrument_geometry": defaultdict(list),
    }

    for record in records:
        dimensions["region"][record.region.value].append(record)
        dimensions["camera"][f"{record.camera_vendor} / {record.camera_model}"].append(record)
        dimensions["lighting"][record.lighting_profile.value].append(record)
        dimensions["reference_l_star_bin"][
            _reference_lightness_bin(record.reference_lab_d50.l_star)
        ].append(record)
        dimensions["operating_system"][record.operating_system_family].append(record)
        dimensions["chart_condition"][record.chart_condition_declared].append(record)
        dimensions["reference_instrument_geometry"][record.reference_measurement_geometry].append(record)

    output: dict[str, dict[str, Any]] = {}
    underpowered: list[dict[str, Any]] = []
    for dimension, groups in dimensions.items():
        output[dimension] = {}
        for group_name, group_records in sorted(groups.items()):
            summary = _summarize(group_records)
            output[dimension][group_name] = summary
            if min_samples is not None and summary["n_total"] < min_samples:
                underpowered.append({
                    "dimension": dimension,
                    "slice": group_name,
                    "n_total": summary["n_total"],
                    "minimum_required": min_samples,
                })
    return output, underpowered


def _repeatability(records: list[ColorValidationSample]) -> dict[str, Any]:
    groups: dict[tuple[str, str, str, str, str], list[ColorValidationSample]] = defaultdict(list)
    for record in records:
        if record.predicted_lab_d50 is None:
            continue
        key = (
            record.subject_ref,
            record.region.value,
            record.camera_vendor,
            record.camera_model,
            record.lighting_profile.value,
        )
        groups[key].append(record)

    pairwise: list[float] = []
    repeated_groups = 0
    for group_records in groups.values():
        if len(group_records) < 2:
            continue
        repeated_groups += 1
        for left, right in combinations(group_records, 2):
            assert left.predicted_lab_d50 is not None
            assert right.predicted_lab_d50 is not None
            pairwise.append(
                delta_e_2000(
                    _lab_tuple(left.predicted_lab_d50),
                    _lab_tuple(right.predicted_lab_d50),
                )
            )
    return {
        "repeated_subject_region_device_lighting_groups": repeated_groups,
        "pairwise_comparisons": len(pairwise),
        "pairwise_delta_e_2000": _percentile_summary(pairwise),
        "interpretation": (
            "within-subject prediction variation across repeated captures; "
            "not instrument uncertainty or inter-rater reproducibility"
        ),
    }


def _cluster_bootstrap(
    records: list[ColorValidationSample],
    *,
    repetitions: int,
    seed: int,
) -> dict[str, Any] | None:
    subject_errors: dict[str, list[float]] = defaultdict(list)
    for record in records:
        error = _record_error(record)
        if error is not None:
            subject_errors[record.subject_ref].append(error)
    subjects = sorted(subject_errors)
    if len(subjects) < 2:
        return None

    rng = np.random.default_rng(seed)
    median_values: list[float] = []
    p95_values: list[float] = []
    for _ in range(repetitions):
        chosen = rng.choice(subjects, size=len(subjects), replace=True)
        values: list[float] = []
        for subject in chosen:
            values.extend(subject_errors[str(subject)])
        if not values:
            continue
        sample = np.asarray(values, dtype=np.float64)
        median_values.append(float(np.median(sample)))
        p95_values.append(float(np.percentile(sample, 95)))

    if not median_values:
        return None
    return {
        "method": "subject_cluster_bootstrap",
        "repetitions": len(median_values),
        "confidence_level": 0.95,
        "median_delta_e_2000_ci95": [
            round(float(np.percentile(median_values, 2.5)), 6),
            round(float(np.percentile(median_values, 97.5)), 6),
        ],
        "p95_delta_e_2000_ci95": [
            round(float(np.percentile(p95_values, 2.5)), 6),
            round(float(np.percentile(p95_values, 97.5)), 6),
        ],
        "subject_identifiers_exported": False,
    }


def _check_policy(
    *,
    records: list[ColorValidationSample],
    policy: ReleasePolicy,
    metrics: dict[str, Any],
    repeatability: dict[str, Any],
    slices: dict[str, dict[str, Any]],
    underpowered: list[dict[str, Any]],
    manifest_created_at,
    manifest_signature_verified: bool,
    policy_signature_verified: bool,
) -> tuple[str, list[str], list[str]]:
    missing = policy.missing_release_fields()
    if missing:
        return "REVIEW_REQUIRED", ["release_policy_incomplete"], missing

    reasons: list[str] = []
    failures: list[str] = []
    unique_subjects = len({record.subject_ref for record in records})
    if unique_subjects < policy.minimum_unique_subjects:
        reasons.append("insufficient_unique_subjects")
    if metrics["n_completed"] < policy.minimum_successful_samples:
        reasons.append("insufficient_successful_samples")
    if underpowered:
        reasons.append("underpowered_evaluation_slices")
    if not manifest_signature_verified:
        reasons.append("dataset_manifest_signature_not_verified")
    if not policy_signature_verified:
        reasons.append("release_policy_signature_not_verified")
    if policy.approved_at is not None and policy.approved_at > manifest_created_at:
        reasons.append("release_policy_approval_after_evaluation_manifest")

    present_regions = set(slices["region"])
    for region in policy.required_regions or []:
        if region.value not in present_regions:
            reasons.append(f"missing_required_region:{region.value}")

    present_lighting = set(slices["lighting"])
    for lighting in policy.required_lighting_profiles or []:
        if lighting.value not in present_lighting:
            reasons.append(f"missing_required_lighting_profile:{lighting.value}")

    if metrics["failure_rate"] is not None and metrics["failure_rate"] > policy.maximum_failure_rate:
        failures.append("maximum_failure_rate_exceeded")

    delta = metrics["delta_e_2000"] or {}
    if delta.get("median", float("inf")) > policy.maximum_median_delta_e_2000:
        failures.append("maximum_median_delta_e_2000_exceeded")
    if delta.get("p95", float("inf")) > policy.maximum_p95_delta_e_2000:
        failures.append("maximum_p95_delta_e_2000_exceeded")

    absolute_bias = metrics["absolute_mean_bias"]
    for axis, threshold in (
        ("l_star", policy.maximum_absolute_l_bias),
        ("a_star", policy.maximum_absolute_a_bias),
        ("b_star", policy.maximum_absolute_b_bias),
    ):
        value = absolute_bias[axis]
        if value is None or value > threshold:
            failures.append(f"maximum_absolute_{axis}_exceeded_or_unmeasured")

    repeat_delta = repeatability["pairwise_delta_e_2000"] or {}
    if repeat_delta.get("median", float("inf")) > policy.maximum_repeatability_median_delta_e_2000:
        failures.append("maximum_repeatability_median_delta_e_2000_exceeded")

    chart_fit = metrics["chart_fit_p95_delta_e_2000"]
    if chart_fit is None or chart_fit > policy.maximum_chart_fit_p95_delta_e_2000:
        failures.append("maximum_chart_fit_p95_delta_e_2000_exceeded_or_unmeasured")

    # Apply the same measurement limits to every sufficiently powered slice;
    # an acceptable aggregate must not conceal a failing camera or lighting group.
    for dimension, groups in slices.items():
        for group_name, summary in groups.items():
            if summary["n_total"] < policy.minimum_samples_per_slice:
                continue
            group_delta = summary["delta_e_2000"] or {}
            if group_delta.get("median", float("inf")) > policy.maximum_median_delta_e_2000:
                failures.append(f"slice_median_delta_e_exceeded:{dimension}:{group_name}")
            if group_delta.get("p95", float("inf")) > policy.maximum_p95_delta_e_2000:
                failures.append(f"slice_p95_delta_e_exceeded:{dimension}:{group_name}")
            group_bias = summary["absolute_mean_bias"]
            for axis, threshold in (
                ("l_star", policy.maximum_absolute_l_bias),
                ("a_star", policy.maximum_absolute_a_bias),
                ("b_star", policy.maximum_absolute_b_bias),
            ):
                value = group_bias[axis]
                if value is None or value > threshold:
                    failures.append(f"slice_{axis}_bias_exceeded_or_unmeasured:{dimension}:{group_name}")

    if failures:
        return "FAIL", failures, reasons
    if reasons:
        return "REVIEW_REQUIRED", reasons, []
    return "PASS", ["all_configured_gates_passed"], []


def evaluate_dataset(
    manifest: EvaluationManifest,
    records: list[ColorValidationSample],
    policy: ReleasePolicy,
    *,
    manifest_sha256: str,
    samples_sha256: str,
    manifest_signature_verified: bool = False,
    policy_signature_verified: bool = False,
) -> dict[str, Any]:
    if not records:
        raise EvaluationInputError("evaluation dataset contains no sample records")
    if len({record.record_id for record in records}) != len(records):
        raise EvaluationInputError("record_id values must be unique")
    if any(record.dataset_version != manifest.dataset_version for record in records):
        raise EvaluationInputError("sample dataset_version does not match manifest")
    if samples_sha256 != manifest.samples_sha256:
        raise EvaluationInputError("sample file SHA-256 does not match signed manifest")
    if manifest.created_at > __import__("datetime").datetime.now(__import__("datetime").timezone.utc):
        raise EvaluationInputError("evaluation manifest timestamp cannot be in the future")

    model_versions = {
        (record.skin_model_name, record.skin_model_version, record.skin_model_sha256)
        for record in records
    }
    segmentation_versions = {
        (record.segmentation_model_version, record.segmentation_model_sha256)
        for record in records
    }
    if len(model_versions) != 1 or len(segmentation_versions) != 1:
        raise EvaluationInputError("an evaluation run must contain exactly one skin model and one segmenter version")

    chart_profiles = {(record.chart_profile_id, record.chart_profile_sha256) for record in records}
    instruments = {(record.reference_instrument_model, record.reference_instrument_calibration_ref) for record in records}
    geometries = {record.reference_measurement_geometry for record in records}
    if len(chart_profiles) != 1:
        raise EvaluationInputError("an evaluation run must use exactly one chart reference profile")
    if len(instruments) != 1:
        raise EvaluationInputError("an evaluation run must use exactly one reference instrument and calibration")
    instrument_model, instrument_calibration_ref = next(iter(instruments))
    if instrument_model != manifest.reference_instrument_model:
        raise EvaluationInputError("sample reference instrument does not match the evaluation manifest")
    if instrument_calibration_ref != manifest.reference_instrument_calibration_ref:
        raise EvaluationInputError("sample instrument calibration does not match the evaluation manifest")
    if len(geometries) != 1:
        raise EvaluationInputError("an evaluation run must use one documented reference measurement geometry")

    capture_regions = [(record.capture_ref, record.region.value) for record in records]
    if len(capture_regions) != len(set(capture_regions)):
        raise EvaluationInputError("capture_ref and region combinations must be unique")

    for digest_name, digest in (("manifest_sha256", manifest_sha256), ("samples_sha256", samples_sha256)):
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise EvaluationInputError(f"{digest_name} must be a lowercase SHA-256 digest")

    metrics = _summarize(records)
    slices, underpowered = _slice_summaries(
        records,
        min_samples=policy.minimum_samples_per_slice,
    )
    repeatability = _repeatability(records)
    confidence_intervals = _cluster_bootstrap(
        records,
        repetitions=policy.bootstrap_repetitions,
        seed=policy.bootstrap_seed,
    )
    decision, decision_reasons, threshold_failures = _check_policy(
        records=records,
        policy=policy,
        metrics=metrics,
        repeatability=repeatability,
        slices=slices,
        underpowered=underpowered,
        manifest_created_at=manifest.created_at,
        manifest_signature_verified=manifest_signature_verified,
        policy_signature_verified=policy_signature_verified,
    )
    skin_name, skin_version, skin_sha = next(iter(model_versions))
    segmenter_version, segmenter_sha = next(iter(segmentation_versions))

    return {
        "report_version": "1",
        "decision": decision,
        "decision_reasons": decision_reasons,
        "threshold_failures": threshold_failures,
        "dataset": {
            "dataset_version": manifest.dataset_version,
            "manifest_sha256": manifest_sha256,
            "samples_sha256": samples_sha256,
            "held_out_test_data": True,
            "source_images_included": False,
            "source_videos_included": False,
            "face_templates_included": False,
            "direct_identifiers_included": False,
            "record_count": len(records),
            "unique_subject_count": len({record.subject_ref for record in records}),
            "unique_camera_model_count": len({
                (record.camera_vendor, record.camera_model) for record in records
            }),
            "rights_provenance_ref": manifest.rights_provenance_ref,
            "consent_registry_ref": manifest.consent_registry_ref,
            "training_overlap_audit_ref": manifest.training_overlap_audit_ref,
            "independent_ground_truth_protocol_ref": manifest.independent_ground_truth_protocol_ref,
            "manifest_signature_verified": manifest_signature_verified,
            "policy_signature_verified": policy_signature_verified,
            "reference_measurement_geometry": next(iter(geometries)),
            "chart_profile_id": next(iter(chart_profiles))[0],
            "chart_profile_sha256": next(iter(chart_profiles))[1],
        },
        "models": {
            "skin_model_name": skin_name,
            "skin_model_version": skin_version,
            "skin_model_sha256": skin_sha,
            "segmentation_model_version": segmenter_version,
            "segmentation_model_sha256": segmenter_sha,
        },
        "policy": {
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "approved_by": policy.approved_by,
            "approval_ref": policy.approval_ref,
            "independent_review_ref": policy.independent_review_ref,
            "approved_at": policy.approved_at.isoformat() if policy.approved_at else None,
            "missing_release_fields": policy.missing_release_fields(),
        },
        "overall_metrics": metrics,
        "slices": slices,
        "underpowered_slices": underpowered,
        "repeatability": repeatability,
        "cluster_bootstrap_confidence_intervals": confidence_intervals,
        "privacy": {
            "subject_identifiers_exported": False,
            "raw_media_exported": False,
            "profile_data_exported": False,
        },
        "limitations": [
            "A PASS applies only to this exact model, segmenter, dataset, policy and evaluation protocol.",
            "Synthetic data must not be used as production ground truth.",
            "The evaluator does not train models, ingest raw media or change live model readiness.",
            "Independent review and approved thresholds are mandatory for a release PASS.",
        ],
    }
