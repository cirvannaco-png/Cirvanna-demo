from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from validation.dsi_color.evaluator import EvaluationInputError, evaluate_dataset
from validation.dsi_color.schema import (
    ColorValidationSample,
    EvaluationManifest,
    LabD50,
    LightingProfile,
    ReleasePolicy,
    SkinRegion,
)

SAMPLES_SHA256 = "2" * 64


def make_manifest(**overrides) -> EvaluationManifest:
    payload = {
        "dataset_version": "dsi-heldout-v1",
        "samples_sha256": SAMPLES_SHA256,
        "created_at": datetime.now(timezone.utc),
        "held_out_test_data": True,
        "rights_provenance_ref": "rights-registry:release-001",
        "consent_registry_ref": "consent-registry:release-001",
        "training_overlap_audit_ref": "training-audit:release-001",
        "independent_ground_truth_protocol_ref": "spectro-protocol:release-001",
        "reference_instrument_model": "Spectro-Reference-1",
        "reference_instrument_calibration_ref": "instrument-calibration:cert-001",
        "reference_measurement_standard": "CIE_LAB_D50_2DEG",
    }
    payload.update(overrides)
    return EvaluationManifest(**payload)


def make_sample(index: int, *, failed: bool = False, **overrides) -> ColorValidationSample:
    subject_number = index // 4
    region = SkinRegion.FACE_SKIN if index % 4 < 2 else SkinRegion.BODY_SKIN
    reference_lightness = 45.0 + subject_number * 3.0 + (
        14.0 if region == SkinRegion.BODY_SKIN else 0.0
    )
    reference = LabD50(l_star=reference_lightness, a_star=12.0, b_star=16.0)
    predicted = None if failed else LabD50(
        l_star=reference_lightness + 0.2 + 0.05 * (index % 2),
        a_star=11.9,
        b_star=16.1,
    )
    camera = "Pixel 8" if subject_number < 2 else "Galaxy S24"
    payload = {
        "record_id": f"eval_{index + 1:012d}",
        "dataset_version": "dsi-heldout-v1",
        "evaluation_split": "held_out_test",
        "subject_ref": "hmac-sha256:" + f"{subject_number + 1:064x}",
        "capture_ref": f"cap_{index + 1:012d}",
        "capture_session_ref": f"ses_{index + 1:012d}",
        "region": region,
        "camera_vendor": "ExampleVendor",
        "camera_model": camera,
        "operating_system_family": "Android",
        "lighting_profile": LightingProfile.CONTROLLED,
        "skin_model_name": "dsi-colour-preview",
        "skin_model_version": "candidate-1",
        "skin_model_sha256": "b" * 64,
        "segmentation_model_version": "segmenter-1",
        "segmentation_model_sha256": "c" * 64,
        "chart_profile_id": "xrite-colorchecker24-after-2014",
        "chart_profile_sha256": "d" * 64,
        "chart_patch_count_used": None if failed else 23,
        "chart_fit_p95_delta_e_2000": None if failed else 1.0,
        "chart_age_months_declared": 36,
        "chart_condition_declared": "good",
        "reference_instrument_model": "Spectro-Reference-1",
        "reference_instrument_calibration_ref": "instrument-calibration:cert-001",
        "reference_measurement_geometry": "45_0",
        "reference_uncertainty_delta_e_2000": 0.5,
        "reference_lab_d50": reference,
        "prediction_status": "failed" if failed else "completed",
        "predicted_lab_d50": predicted,
        "failure_code": "segmentation_missing" if failed else None,
    }
    payload.update(overrides)
    return ColorValidationSample(**payload)


def approved_policy(**overrides) -> ReleasePolicy:
    payload = {
        "policy_id": "dsi-colour-policy-v1",
        "policy_version": "1",
        "approved_by": "independent-validation-board",
        "approval_ref": "approval-record:2026-001",
        "independent_review_ref": "independent-review:2026-001",
        "approved_at": datetime.now(timezone.utc) - timedelta(minutes=1),
        "minimum_unique_subjects": 4,
        "minimum_successful_samples": 16,
        "minimum_samples_per_slice": 2,
        "required_regions": [SkinRegion.FACE_SKIN, SkinRegion.BODY_SKIN],
        "required_lighting_profiles": [LightingProfile.CONTROLLED],
        "maximum_failure_rate": 0.0,
        "maximum_median_delta_e_2000": 2.0,
        "maximum_p95_delta_e_2000": 3.0,
        "maximum_absolute_l_bias": 1.0,
        "maximum_absolute_a_bias": 1.0,
        "maximum_absolute_b_bias": 1.0,
        "maximum_repeatability_median_delta_e_2000": 1.0,
        "maximum_chart_fit_p95_delta_e_2000": 2.0,
        "bootstrap_repetitions": 100,
        "bootstrap_seed": 12,
    }
    payload.update(overrides)
    return ReleasePolicy(**payload)


def evaluate(records, policy, manifest=None, **attestations):
    return evaluate_dataset(
        manifest or make_manifest(),
        records,
        policy,
        manifest_sha256="1" * 64,
        samples_sha256=SAMPLES_SHA256,
        manifest_signature_verified=attestations.get("manifest_signature_verified", True),
        policy_signature_verified=attestations.get("policy_signature_verified", True),
    )


def test_incomplete_release_policy_cannot_approve_model():
    policy = ReleasePolicy(policy_id="pending", policy_version="1", minimum_unique_subjects=4)
    report = evaluate([make_sample(index) for index in range(16)], policy)
    assert report["decision"] == "REVIEW_REQUIRED"
    assert "release_policy_incomplete" in report["decision_reasons"]
    assert report["policy"]["missing_release_fields"]


def test_empty_required_region_or_lighting_lists_are_incomplete():
    policy = approved_policy(required_regions=[], required_lighting_profiles=[])
    report = evaluate([make_sample(index) for index in range(16)], policy)
    assert report["decision"] == "REVIEW_REQUIRED"
    assert "required_regions" in report["policy"]["missing_release_fields"]
    assert "required_lighting_profiles" in report["policy"]["missing_release_fields"]


def test_missing_attestations_cannot_return_pass():
    report = evaluate(
        [make_sample(index) for index in range(16)],
        approved_policy(),
        manifest_signature_verified=False,
        policy_signature_verified=False,
    )
    assert report["decision"] == "REVIEW_REQUIRED"
    assert "dataset_manifest_signature_not_verified" in report["decision_reasons"]
    assert "release_policy_signature_not_verified" in report["decision_reasons"]


def test_approved_policy_reports_error_bias_uncertainty_and_subject_clustered_ci():
    report = evaluate([make_sample(index) for index in range(16)], approved_policy())
    assert report["decision"] == "PASS"
    assert report["overall_metrics"]["n_completed"] == 16
    assert report["overall_metrics"]["n_failed"] == 0
    assert report["overall_metrics"]["reference_instrument_uncertainty_delta_e_2000"]["median"] == 0.5
    assert report["slices"]["region"]["face_skin"]["n_total"] == 8
    assert report["slices"]["region"]["body_skin"]["n_total"] == 8
    assert "operating_system" in report["slices"]
    assert "chart_condition" in report["slices"]
    assert report["repeatability"]["pairwise_comparisons"] > 0
    assert report["cluster_bootstrap_confidence_intervals"]["method"] == "subject_cluster_bootstrap"
    assert report["privacy"]["subject_identifiers_exported"] is False
    assert "hmac-sha256:" not in str(report)


def test_failure_rate_violation_fails_release_gate():
    records = [make_sample(index, failed=(index == 0)) for index in range(16)]
    report = evaluate(records, approved_policy(maximum_failure_rate=0.0))
    assert report["decision"] == "FAIL"
    assert "maximum_failure_rate_exceeded" in report["threshold_failures"]
    assert report["overall_metrics"]["n_failed"] == 1


def test_high_colour_error_fails_delta_e_release_gate():
    records = [make_sample(index) for index in range(16)]
    records[0] = records[0].model_copy(
        update={"predicted_lab_d50": LabD50(l_star=75.0, a_star=30.0, b_star=40.0)}
    )
    report = evaluate(records, approved_policy(maximum_p95_delta_e_2000=2.0))
    assert report["decision"] == "FAIL"
    assert "maximum_p95_delta_e_2000_exceeded" in report["threshold_failures"]


def test_subgroup_camera_error_cannot_be_hidden_by_global_average():
    records = [make_sample(index) for index in range(16)]
    for index in range(8, 16):
        record = records[index]
        records[index] = record.model_copy(
            update={"predicted_lab_d50": LabD50(l_star=record.reference_lab_d50.l_star + 7.0, a_star=12.0, b_star=16.0)}
        )
    report = evaluate(
        records,
        approved_policy(maximum_p95_delta_e_2000=2.0, maximum_median_delta_e_2000=1.0),
    )
    assert report["decision"] == "FAIL"
    assert any(reason.startswith("slice_p95_delta_e_exceeded:camera:") for reason in report["threshold_failures"])


def test_mixed_model_versions_are_rejected():
    records = [make_sample(index) for index in range(16)]
    records[0] = records[0].model_copy(update={"skin_model_version": "different-version"})
    with pytest.raises(EvaluationInputError, match="exactly one skin model"):
        evaluate(records, approved_policy())


def test_mixed_chart_profiles_are_rejected():
    records = [make_sample(index) for index in range(16)]
    records[0] = records[0].model_copy(update={"chart_profile_id": "other-chart"})
    with pytest.raises(EvaluationInputError, match="exactly one chart reference"):
        evaluate(records, approved_policy())


def test_reference_instrument_must_match_manifest():
    records = [make_sample(index) for index in range(16)]
    records[0] = records[0].model_copy(update={"reference_instrument_model": "Different-Instrument"})
    with pytest.raises(EvaluationInputError, match="one reference instrument"):
        evaluate(records, approved_policy())


def test_manifest_and_sample_digests_must_be_sha256():
    with pytest.raises(EvaluationInputError, match="manifest_sha256"):
        evaluate_dataset(
            make_manifest(),
            [make_sample(index) for index in range(16)],
            approved_policy(),
            manifest_sha256="not-a-digest",
            samples_sha256=SAMPLES_SHA256,
            manifest_signature_verified=True,
            policy_signature_verified=True,
        )


def test_sample_digest_must_match_signed_manifest():
    with pytest.raises(EvaluationInputError, match="does not match signed manifest"):
        evaluate_dataset(
            make_manifest(samples_sha256="3" * 64),
            [make_sample(index) for index in range(16)],
            approved_policy(),
            manifest_sha256="1" * 64,
            samples_sha256=SAMPLES_SHA256,
            manifest_signature_verified=True,
            policy_signature_verified=True,
        )


def test_duplicate_record_id_is_rejected():
    records = [make_sample(index) for index in range(16)]
    records[1] = records[0]
    with pytest.raises(EvaluationInputError, match="record_id values must be unique"):
        evaluate(records, approved_policy())


def test_duplicate_capture_region_is_rejected():
    records = [make_sample(index) for index in range(16)]
    records[1] = records[0].model_copy(update={"record_id": "eval_000000000099"})
    with pytest.raises(EvaluationInputError, match="capture_ref and region"):
        evaluate(records, approved_policy())


def test_dataset_version_mismatch_is_rejected():
    records = [make_sample(index) for index in range(16)]
    records[0] = records[0].model_copy(update={"dataset_version": "another-version"})
    with pytest.raises(EvaluationInputError, match="does not match manifest"):
        evaluate(records, approved_policy())


def test_future_policy_approval_cannot_retroactively_pass_older_evaluation():
    manifest = make_manifest(created_at=datetime.now(timezone.utc) - timedelta(days=2))
    report = evaluate(
        [make_sample(index) for index in range(16)],
        approved_policy(approved_at=datetime.now(timezone.utc)),
        manifest=manifest,
    )
    assert report["decision"] == "REVIEW_REQUIRED"
    assert "release_policy_approval_after_evaluation_manifest" in report["decision_reasons"]


def test_manifest_must_not_include_source_media_or_direct_identifiers():
    with pytest.raises(ValidationError):
        make_manifest(source_images_included=True)
    with pytest.raises(ValidationError):
        ColorValidationSample(**{**make_sample(0).model_dump(), "raw_image_path": "/private/images/face.jpg"})


def test_underpowered_camera_and_lighting_slices_require_review():
    records = [make_sample(index) for index in range(4)]
    policy = approved_policy(
        minimum_unique_subjects=2,
        minimum_successful_samples=4,
        minimum_samples_per_slice=3,
    )
    report = evaluate(records, policy)
    assert report["decision"] == "REVIEW_REQUIRED"
    assert "underpowered_evaluation_slices" in report["decision_reasons"]
    assert report["underpowered_slices"]



def test_missing_repeatability_is_review_not_a_false_model_failure():
    records = [
        make_sample(index).model_copy(
            update={"subject_ref": "hmac-sha256:" + f"{index + 100:064x}"}
        )
        for index in range(16)
    ]
    report = evaluate(records, approved_policy())
    assert report["decision"] == "REVIEW_REQUIRED"
    assert "repeatability_evidence_missing" in report["decision_reasons"]
    assert not report["threshold_failures"]


def test_missing_successful_measurements_are_review_not_metric_failure():
    records = [make_sample(index, failed=True) for index in range(16)]
    report = evaluate(records, approved_policy(maximum_failure_rate=1.0))
    assert report["decision"] == "REVIEW_REQUIRED"
    assert "colour_error_metrics_unavailable" in report["decision_reasons"]
    assert "chart_fit_metrics_unavailable" in report["decision_reasons"]
    assert "repeatability_evidence_missing" in report["decision_reasons"]
    assert not report["threshold_failures"]
