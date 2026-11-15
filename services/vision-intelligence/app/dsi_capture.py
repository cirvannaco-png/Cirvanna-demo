"""Strict DSI capture-provenance contracts for calibrated colour work.

The values in this module are declarations/metadata, not proof that camera
controls or physical lighting were actually enforced. This contract deliberately
cannot approve an absolute colour measurement or enable inference.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CaptureContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CaptureMode(str, Enum):
    CONTROLLED_DIFFUSE = "controlled_diffuse"
    CROSS_POLARIZED = "cross_polarized"
    AMBIENT_RELATIVE = "ambient_relative"
    UNKNOWN = "unknown"


class ControlState(str, Enum):
    LOCKED = "locked"
    AUTOMATIC = "automatic"
    UNKNOWN = "unknown"


class IlluminationSetup(str, Enum):
    STANDARDIZED_DIFFUSE = "standardized_diffuse"
    AMBIENT_DAYLIGHT = "ambient_daylight"
    AMBIENT_INDOOR = "ambient_indoor"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ImageColorProfileState(str, Enum):
    EMBEDDED_ICC = "embedded_icc"
    PINNED_CAMERA_PROFILE = "pinned_camera_profile"
    UNTAGGED_ASSUMED_SRGB = "untagged_assumed_srgb"
    MISSING = "missing"
    INVALID = "invalid"


class ImageProcessingState(str, Enum):
    DISABLED = "disabled"
    ENABLED = "enabled"
    UNKNOWN = "unknown"


class ChartCondition(str, Enum):
    GOOD = "good"
    WORN = "worn"
    UNKNOWN = "unknown"
    NOT_PRESENT = "not_present"


class IlluminanceSource(str, Enum):
    CALIBRATED_METER = "calibrated_meter"
    DEVICE_SENSOR = "device_sensor"
    USER_DECLARED = "user_declared"
    UNAVAILABLE = "unavailable"


class PolarizationSetup(CaptureContract):
    """Declared optical components; the server must not treat them as verified."""

    light_source_polarizer_ref: str = Field(min_length=3, max_length=128)
    camera_analyzer_ref: str = Field(min_length=3, max_length=128)
    relative_orientation_degrees: float | None = Field(default=None, ge=0, le=180)
    optical_setup_reference: str = Field(min_length=8, max_length=256)


class DSICaptureProvenance(CaptureContract):
    """Non-identifying capture metadata for evaluation and quality review.

    Do not add names, account IDs, device serial numbers, geolocation, raw EXIF,
    face landmarks, source image bytes or other direct identifiers here.
    Fields named reported_* and declared_* are not trusted attestations.
    """

    schema_version: Literal["dsi-capture-v1"] = "dsi-capture-v1"
    capture_ref: str = Field(pattern=r"^cap_[A-Za-z0-9_-]{12,96}$")

    reported_camera_vendor: str | None = Field(default=None, min_length=1, max_length=100)
    reported_camera_model: str | None = Field(default=None, min_length=1, max_length=160)
    reported_operating_system: str | None = Field(default=None, min_length=1, max_length=80)
    capture_app_version: str | None = Field(default=None, min_length=1, max_length=80)

    capture_mode: CaptureMode
    illumination_setup: IlluminationSetup
    reported_illuminant_name: str | None = Field(default=None, min_length=1, max_length=80)
    reported_illuminance_lux: float | None = Field(default=None, ge=0, le=200_000)
    illuminance_source: IlluminanceSource = IlluminanceSource.UNAVAILABLE
    illuminance_meter_model: str | None = Field(default=None, min_length=1, max_length=128)
    illuminance_meter_calibration_ref: str | None = Field(default=None, min_length=8, max_length=256)

    white_balance_state: ControlState
    exposure_state: ControlState
    image_color_profile_state: ImageColorProfileState
    image_color_profile_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    chart_present: bool
    chart_profile_id: str | None = Field(default=None, min_length=1, max_length=128)
    chart_profile_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    chart_condition: ChartCondition
    chart_production_edition: str | None = Field(default=None, min_length=1, max_length=80)

    hdr_processing: ImageProcessingState
    beauty_filter_processing: ImageProcessingState
    polarization: PolarizationSetup | None = None

    @model_validator(mode="after")
    def validate_capture_provenance(self) -> "DSICaptureProvenance":
        if self.image_color_profile_state in {
            ImageColorProfileState.EMBEDDED_ICC,
            ImageColorProfileState.PINNED_CAMERA_PROFILE,
        } and self.image_color_profile_sha256 is None:
            raise ValueError("a supported image colour profile requires its SHA-256 digest")

        if self.image_color_profile_state in {
            ImageColorProfileState.UNTAGGED_ASSUMED_SRGB,
            ImageColorProfileState.MISSING,
            ImageColorProfileState.INVALID,
        } and self.image_color_profile_sha256 is not None:
            raise ValueError("unprofiled or invalid input cannot carry a trusted profile digest")

        if self.chart_present:
            if not self.chart_profile_id or not self.chart_profile_sha256:
                raise ValueError("a present chart requires a pinned chart profile ID and digest")
            if self.chart_condition == ChartCondition.NOT_PRESENT:
                raise ValueError("a present chart cannot use the not_present condition")
        else:
            if self.chart_condition != ChartCondition.NOT_PRESENT:
                raise ValueError("a missing chart must use the not_present condition")
            if self.chart_profile_id is not None or self.chart_profile_sha256 is not None:
                raise ValueError("a missing chart cannot carry chart profile metadata")

        if self.capture_mode == CaptureMode.CROSS_POLARIZED and self.polarization is None:
            raise ValueError("cross-polarized capture requires declared source and camera polarizers")
        if self.capture_mode != CaptureMode.CROSS_POLARIZED and self.polarization is not None:
            raise ValueError("polarization metadata is only valid for cross-polarized capture")

        if self.illuminance_source == IlluminanceSource.CALIBRATED_METER:
            if not self.illuminance_meter_model or not self.illuminance_meter_calibration_ref:
                raise ValueError("calibrated-meter illuminance requires model and calibration reference")
            if self.reported_illuminance_lux is None:
                raise ValueError("calibrated-meter illuminance requires a lux reading")
        elif self.illuminance_meter_model or self.illuminance_meter_calibration_ref:
            raise ValueError("meter identity/calibration fields require calibrated_meter source")

        return self


def assess_capture_declaration(evidence: DSICaptureProvenance) -> dict[str, object]:
    """Assess declaration completeness without authorizing measurement or inference."""
    reasons: list[str] = []

    if evidence.capture_mode not in {CaptureMode.CONTROLLED_DIFFUSE, CaptureMode.CROSS_POLARIZED}:
        reasons.append("capture_mode_not_controlled")
    if evidence.illumination_setup != IlluminationSetup.STANDARDIZED_DIFFUSE:
        reasons.append("standardized_diffuse_illumination_not_declared")
    if evidence.white_balance_state != ControlState.LOCKED:
        reasons.append("white_balance_not_declared_locked")
    if evidence.exposure_state != ControlState.LOCKED:
        reasons.append("exposure_not_declared_locked")
    if evidence.image_color_profile_state not in {
        ImageColorProfileState.EMBEDDED_ICC,
        ImageColorProfileState.PINNED_CAMERA_PROFILE,
    }:
        reasons.append("supported_image_color_profile_not_declared")
    if not evidence.chart_present:
        reasons.append("physical_color_reference_not_present")
    if evidence.chart_condition != ChartCondition.GOOD:
        reasons.append("chart_condition_not_confirmed_good")
    if evidence.illuminance_source != IlluminanceSource.CALIBRATED_METER:
        reasons.append("calibrated_illuminance_measurement_not_declared")
    if evidence.hdr_processing != ImageProcessingState.DISABLED:
        reasons.append("hdr_processing_not_confirmed_disabled")
    if evidence.beauty_filter_processing != ImageProcessingState.DISABLED:
        reasons.append("beauty_filter_processing_not_confirmed_disabled")
    if evidence.capture_mode == CaptureMode.CROSS_POLARIZED:
        if evidence.polarization is None:
            reasons.append("cross_polarization_setup_incomplete")

    declaration_state = "conditions_declared_for_review" if not reasons else "review_required"
    return {
        "capture_declaration_state": declaration_state,
        "evidence_kind": "client_or_device_declaration_not_independent_attestation",
        "review_required_reasons": reasons,
        "absolute_colour_measurement_approved": False,
        "measurement_uncertainty_validated": False,
        "inference_authorized": False,
        "note": (
            "A complete declaration is only a candidate for controlled evaluation. "
            "It does not prove physical lighting, camera-control enforcement, chart integrity, "
            "cross-polarizer geometry or camera colour accuracy."
        ),
    }
