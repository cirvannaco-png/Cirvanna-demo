
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.dsi_device_baselines import (
    BaselineProfileStatus,
    CameraAPI,
    CameraFacing,
    CaptureMode,
    ChartCondition,
    DeviceBaselineError,
    DeviceBaselineProfile,
    DeviceBaselineRegistry,
    DeviceCaptureCapabilities,
    DeviceCaptureReport,
    DevicePipelineFingerprint,
    DeviceValidationEvidence,
    LensRole,
    MinimumCaptureStandard,
    OutputFormat,
    Platform,
    QualificationLevel,
    load_device_baseline_registry,
    baseline_result,
)


def fingerprint(**overrides):
    values = {
        "platform": Platform.ANDROID,
        "manufacturer": "Example OEM",
        "model": "Model Z",
        "camera_module_id": "rear-main-module-v1",
        "camera_facing": CameraFacing.REAR,
        "lens_role": LensRole.REAR_WIDE,
        "os_release": "Android 15",
        "camera_api": CameraAPI.ANDROID_CAMERA2,
        "capture_runtime": "CirvannaCapture",
        "capture_runtime_version": "1.2.0",
        "capture_pipeline_revision": "camera-pipeline-3",
        "output_format": OutputFormat.JPEG,
        "colour_profile_sha256": "a" * 64,
    }
    values.update(overrides)
    return DevicePipelineFingerprint.model_validate(values)


def report(**capability_overrides):
    capabilities = {
        "output_width": 3024,
        "output_height": 4032,
        "manual_exposure_supported": True,
        "exposure_lock_applied": True,
        "white_balance_lock_supported": True,
        "white_balance_lock_applied": True,
        "raw_capture_supported": False,
        "raw_capture_used": False,
        "sensor_colour_calibration_available": False,
        "output_colour_profile_sha256": "a" * 64,
        "hdr_disabled": True,
        "beauty_processing_disabled": True,
        "capture_mode": CaptureMode.CONTROLLED_DIFFUSE,
        "chart_condition": ChartCondition.GOOD,
        "chart_profile_id": "xrite-colorchecker24-after-2014",
        "chart_profile_sha256": "b" * 64,
    }
    capabilities.update(capability_overrides)
    return DeviceCaptureReport(
        fingerprint=fingerprint(),
        capabilities=DeviceCaptureCapabilities.model_validate(capabilities),
    )


def standard(**overrides):
    values = {
        "minimum_width": 1200,
        "minimum_height": 1600,
        "required_capture_modes": [CaptureMode.CONTROLLED_DIFFUSE],
        "accepted_output_formats": [OutputFormat.JPEG],
        "require_manual_exposure_lock": True,
        "require_white_balance_lock": True,
        "require_hdr_disabled": True,
        "require_beauty_processing_disabled": True,
        "require_chart_in_frame": True,
        "required_chart_profile_id": "xrite-colorchecker24-after-2014",
        "required_chart_profile_sha256": "b" * 64,
        "require_raw_or_colour_profile": True,
    }
    values.update(overrides)
    return MinimumCaptureStandard.model_validate(values)


def validation_evidence(now=None):
    now = now or datetime.now(timezone.utc)
    return DeviceValidationEvidence(
        calibration_profile_ref="calibration-profile:device-z",
        calibration_profile_sha256="c" * 64,
        validation_report_ref="validation-report:device-z",
        validation_report_sha256="d" * 64,
        evaluation_dataset_sha256="e" * 64,
        reference_instrument_model="Spectrophotometer model R",
        reference_instrument_calibration_ref="instrument-certificate:2026-01",
        independent_review_ref="independent-review:device-z",
        approved_by="Independent measurement reviewer",
        approved_at=now - timedelta(days=1),
        valid_until=now + timedelta(days=30),
        evaluated_device_unit_count=12,
        validated_regions=["face_skin", "neck"],
        validated_measured_lightness_ranges=["L00-20", "L20-40", "L40-60", "L60-80", "L80-100"],
        evaluated_lighting_profiles=["controlled_diffuse"],
    )


def profile(level=QualificationLevel.COLOUR_VALIDATED, now=None, **overrides):
    values = {
        "profile_id": "device-z-rear-wide-android15-v1",
        "profile_version": "1.0.0",
        "fingerprint": fingerprint(),
        "status": BaselineProfileStatus.ACTIVE,
        "qualification_level": level,
        "minimum_standard": standard(),
        "validation": validation_evidence(now) if level != QualificationLevel.CAPTURE_CANDIDATE else None,
        "cross_polarization_validation_report_ref": None,
        "cross_polarization_validation_report_sha256": None,
    }
    values.update(overrides)
    return DeviceBaselineProfile.model_validate(values)


def registry(profile_value):
    return DeviceBaselineRegistry(
        schema_version="dsi-device-baseline-registry-v1",
        registry_version="test-1",
        profiles=[profile_value],
    )


def test_fingerprint_is_deterministic_and_camera_pipeline_specific():
    original = fingerprint()
    same = fingerprint()
    another_os = fingerprint(os_release="Android 16")
    another_lens = fingerprint(lens_role=LensRole.REAR_ULTRAWIDE, camera_module_id="rear-ultra-v1")

    assert original.fingerprint_sha256 == same.fingerprint_sha256
    assert original.fingerprint_sha256 != another_os.fingerprint_sha256
    assert original.fingerprint_sha256 != another_lens.fingerprint_sha256


def test_unknown_device_has_relative_only_fallback():
    result = baseline_result(
        report(),
        DeviceBaselineRegistry(schema_version="dsi-device-baseline-registry-v1", registry_version="empty", profiles=[]),
        registry_configured=True,
    )

    assert result["operational_tier"] == "relative_only"
    assert result["absolute_colour_measurement_allowed"] is False
    assert result["review_required_reasons"] == ["no_exact_camera_pipeline_profile"]


def test_unconfigured_registry_never_guesses_a_device_profile():
    result = baseline_result(report(), None, registry_configured=False)

    assert result["operational_tier"] == "relative_only"
    assert result["review_required_reasons"] == ["device_baseline_registry_not_configured"]


def test_exact_profile_match_without_server_verified_capture_attestation_stays_relative_only():
    result = baseline_result(report(), registry(profile()), registry_configured=True)

    assert result["profile_match"] == "exact_claim_match_attestation_pending"
    assert result["operational_tier"] == "relative_only"
    assert result["absolute_colour_measurement_allowed"] is False
    assert result["review_required_reasons"] == ["trusted_capture_attestation_not_verified"]


def test_validated_profile_only_becomes_colour_validated_after_internal_attestation():
    result = baseline_result(
        report(),
        registry(profile()),
        registry_configured=True,
        capture_attestation_verified=True,
    )

    assert result["operational_tier"] == "colour_validated"
    assert result["device_pipeline_colour_qualified"] is True
    assert result["absolute_colour_measurement_allowed"] is False
    assert result["individual_measurement_release_required"] is True
    assert result["cross_polarized_pipeline_qualified"] is False


def test_capture_candidate_profile_never_authorizes_absolute_colour():
    candidate = profile(
        level=QualificationLevel.CAPTURE_CANDIDATE,
        validation=None,
    )
    result = baseline_result(
        report(),
        registry(candidate),
        registry_configured=True,
        capture_attestation_verified=True,
    )

    assert result["operational_tier"] == "controlled_capture_candidate"
    assert result["absolute_colour_measurement_allowed"] is False


@pytest.mark.parametrize(
    ("override", "expected_reason"),
    [
        ({"exposure_lock_applied": False}, "manual_or_locked_exposure_unavailable"),
        ({"white_balance_lock_applied": False}, "white_balance_lock_unavailable"),
        ({"hdr_disabled": False}, "hdr_processing_not_disabled"),
        ({"beauty_processing_disabled": False}, "beauty_processing_not_disabled"),
        ({"chart_condition": ChartCondition.WORN}, "valid_in_frame_colour_reference_required"),
        ({"output_width": 640}, "output_resolution_below_device_baseline"),
        ({"output_colour_profile_sha256": "f" * 64}, "raw_sensor_or_pinned_colour_profile_required"),
    ],
)
def test_minimum_standard_failure_prevents_qualification(override, expected_reason):
    result = baseline_result(
        report(**override),
        registry(profile()),
        registry_configured=True,
        capture_attestation_verified=True,
    )

    assert result["operational_tier"] == "relative_only"
    assert expected_reason in result["review_required_reasons"]


def test_profile_validity_expiry_returns_relative_only():
    now = datetime.now(timezone.utc)
    expired = validation_evidence(now - timedelta(days=60))
    expired = expired.model_copy(update={
        "approved_at": now - timedelta(days=40),
        "valid_until": now - timedelta(days=1),
    })
    device_profile = profile(now=now, validation=expired)

    result = baseline_result(
        report(),
        registry(device_profile),
        registry_configured=True,
        capture_attestation_verified=True,
        now=now,
    )

    assert result["operational_tier"] == "relative_only"
    assert result["review_required_reasons"] == ["device_profile_validation_expired_or_not_yet_valid"]


def test_cross_polarized_profile_requires_separate_optical_validation_and_capture_mode():
    now = datetime.now(timezone.utc)
    cross_standard = standard(
        required_capture_modes=[CaptureMode.CROSS_POLARIZED],
    )
    cross_profile = profile(
        level=QualificationLevel.CROSS_POLARIZED_VALIDATED,
        now=now,
        minimum_standard=cross_standard,
        cross_polarization_validation_report_ref="polarization-report:device-z",
        cross_polarization_validation_report_sha256="f" * 64,
    )
    diffuse_result = baseline_result(
        report(),
        registry(cross_profile),
        registry_configured=True,
        capture_attestation_verified=True,
        now=now,
    )
    assert diffuse_result["operational_tier"] == "relative_only"
    assert "capture_mode_not_qualified" in diffuse_result["review_required_reasons"]

    cross_report = report(capture_mode=CaptureMode.CROSS_POLARIZED)
    cross_result = baseline_result(
        cross_report,
        registry(cross_profile),
        registry_configured=True,
        capture_attestation_verified=True,
        now=now,
    )
    assert cross_result["operational_tier"] == "cross_polarized_validated"
    assert cross_result["cross_polarized_pipeline_qualified"] is True
    assert cross_result["absolute_colour_measurement_allowed"] is False
    assert cross_result["individual_measurement_release_required"] is True


def test_registry_rejects_duplicate_camera_pipeline_profiles():
    same = profile()
    duplicate = same.model_copy(update={"profile_id": "another-profile"})
    with pytest.raises(ValidationError, match="only one baseline"):
        DeviceBaselineRegistry(
            schema_version="dsi-device-baseline-registry-v1",
            registry_version="duplicate",
            profiles=[same, duplicate],
        )


def test_colour_validated_profile_requires_independent_evidence():
    with pytest.raises(ValidationError, match="require independent validation evidence"):
        profile(validation=None)


def test_loader_requires_both_path_and_sha_pin(monkeypatch):
    monkeypatch.setenv("DSI_DEVICE_BASELINE_REGISTRY_PATH", "/tmp/registry.json")
    monkeypatch.delenv("DSI_DEVICE_BASELINE_REGISTRY_SHA256", raising=False)

    with pytest.raises(DeviceBaselineError, match="both be configured"):
        load_device_baseline_registry()


def test_loader_accepts_only_exact_sha256_pinned_registry(tmp_path, monkeypatch):
    registry_bytes = b'{"schema_version":"dsi-device-baseline-registry-v1","registry_version":"empty","profiles":[]}'
    path = tmp_path / "registry.json"
    path.write_bytes(registry_bytes)
    monkeypatch.setenv("DSI_DEVICE_BASELINE_REGISTRY_PATH", str(path))
    monkeypatch.setenv("DSI_DEVICE_BASELINE_REGISTRY_SHA256", hashlib.sha256(registry_bytes).hexdigest())

    loaded, configured = load_device_baseline_registry()

    assert configured is True
    assert loaded is not None
    assert loaded.registry_version == "empty"

    monkeypatch.setenv("DSI_DEVICE_BASELINE_REGISTRY_SHA256", "0" * 64)
    with pytest.raises(DeviceBaselineError, match="SHA-256 mismatch"):
        load_device_baseline_registry()
