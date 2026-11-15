from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.dsi_capture import (
    CaptureMode,
    ChartCondition,
    ControlState,
    DSICaptureProvenance,
    ImageColorProfileState,
    ImageProcessingState,
    IlluminationSetup,
    IlluminanceSource,
    PolarizationSetup,
    assess_capture_declaration,
)


def valid_capture(**overrides):
    values = {
        "capture_ref": "cap_dsi_capture_0001",
        "reported_camera_vendor": "Example",
        "reported_camera_model": "Model X",
        "reported_operating_system": "Android",
        "capture_app_version": "0.1.0",
        "capture_mode": CaptureMode.CONTROLLED_DIFFUSE,
        "illumination_setup": IlluminationSetup.STANDARDIZED_DIFFUSE,
        "reported_illuminant_name": "documented-light-source-profile",
        "reported_illuminance_lux": 1000.0,
        "illuminance_source": IlluminanceSource.CALIBRATED_METER,
        "illuminance_meter_model": "Reference lux meter",
        "illuminance_meter_calibration_ref": "calibration-certificate:meter-001",
        "white_balance_state": ControlState.LOCKED,
        "exposure_state": ControlState.LOCKED,
        "image_color_profile_state": ImageColorProfileState.EMBEDDED_ICC,
        "image_color_profile_sha256": "a" * 64,
        "chart_present": True,
        "chart_profile_id": "xrite-colorchecker24-after-2014",
        "chart_profile_sha256": "b" * 64,
        "chart_condition": ChartCondition.GOOD,
        "chart_production_edition": "post-november-2014",
        "hdr_processing": ImageProcessingState.DISABLED,
        "beauty_filter_processing": ImageProcessingState.DISABLED,
        "polarization": None,
    }
    values.update(overrides)
    return DSICaptureProvenance.model_validate(values)


def test_complete_controlled_capture_is_only_a_review_candidate():
    evidence = valid_capture()
    result = assess_capture_declaration(evidence)

    assert result["capture_declaration_state"] == "conditions_declared_for_review"
    assert result["evidence_kind"] == "client_or_device_declaration_not_independent_attestation"
    assert result["absolute_colour_measurement_approved"] is False
    assert result["measurement_uncertainty_validated"] is False
    assert result["inference_authorized"] is False


def test_ambient_capture_cannot_be_declared_ready_for_calibrated_colour():
    evidence = valid_capture(
        capture_mode=CaptureMode.AMBIENT_RELATIVE,
        illumination_setup=IlluminationSetup.AMBIENT_DAYLIGHT,
        chart_present=False,
        chart_profile_id=None,
        chart_profile_sha256=None,
        chart_condition=ChartCondition.NOT_PRESENT,
        illuminance_source=IlluminanceSource.DEVICE_SENSOR,
        illuminance_meter_model=None,
        illuminance_meter_calibration_ref=None,
    )
    result = assess_capture_declaration(evidence)

    assert result["capture_declaration_state"] == "review_required"
    assert "capture_mode_not_controlled" in result["review_required_reasons"]
    assert "physical_color_reference_not_present" in result["review_required_reasons"]


def test_cross_polarized_capture_requires_both_optical_components_and_orientation():
    with pytest.raises(ValidationError, match="cross-polarized capture requires"):
        valid_capture(capture_mode=CaptureMode.CROSS_POLARIZED)


def test_cross_polarized_capture_records_declared_pair_without_claiming_verification():
    evidence = valid_capture(
        capture_mode=CaptureMode.CROSS_POLARIZED,
        polarization=PolarizationSetup(
            light_source_polarizer_ref="light-polarizer-A",
            camera_analyzer_ref="lens-analyzer-B",
            relative_orientation_degrees=90.0,
            optical_setup_reference="lab-setup:polarization-001",
        ),
    )
    result = assess_capture_declaration(evidence)

    assert result["capture_declaration_state"] == "conditions_declared_for_review"
    assert result["evidence_kind"] == "client_or_device_declaration_not_independent_attestation"
    assert result["absolute_colour_measurement_approved"] is False


def test_embedded_icc_requires_digest():
    with pytest.raises(ValidationError, match="requires its SHA-256"):
        valid_capture(image_color_profile_sha256=None)


def test_untagged_srgb_is_not_treated_as_a_profiled_calibrated_capture():
    evidence = valid_capture(
        image_color_profile_state=ImageColorProfileState.UNTAGGED_ASSUMED_SRGB,
        image_color_profile_sha256=None,
    )
    result = assess_capture_declaration(evidence)

    assert "supported_image_color_profile_not_declared" in result["review_required_reasons"]


def test_missing_chart_has_no_profile_metadata():
    with pytest.raises(ValidationError, match="missing chart cannot carry chart profile metadata"):
        valid_capture(
            chart_present=False,
            chart_condition=ChartCondition.NOT_PRESENT,
        )


def test_calibrated_meter_requires_a_calibration_certificate_and_reading():
    with pytest.raises(ValidationError, match="requires model and calibration reference"):
        valid_capture(illuminance_meter_calibration_ref=None)


def test_unknown_image_processing_is_review_required():
    evidence = valid_capture(hdr_processing=ImageProcessingState.UNKNOWN)
    result = assess_capture_declaration(evidence)

    assert "hdr_processing_not_confirmed_disabled" in result["review_required_reasons"]
