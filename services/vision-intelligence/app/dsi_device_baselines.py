
"""Versioned device/camera-pipeline baselines for DSI.

Profiles are scoped to an exact camera pipeline, not a brand name alone.
Client-reported values are not trusted attestations. Without a separately
verified capture attestation, device resolution is guidance-only.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DeviceBaselineError(ValueError):
    """Invalid or untrusted device-baseline registry configuration."""


class BaselineContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Platform(str, Enum):
    ANDROID = "android"
    IOS = "ios"


class CameraAPI(str, Enum):
    ANDROID_CAMERA2 = "android_camera2"
    ANDROID_CAMERAX = "android_camerax"
    IOS_AVFOUNDATION = "ios_avfoundation"


class CameraFacing(str, Enum):
    FRONT = "front"
    REAR = "rear"
    EXTERNAL = "external"


class LensRole(str, Enum):
    FRONT = "front"
    REAR_WIDE = "rear_wide"
    REAR_ULTRAWIDE = "rear_ultrawide"
    REAR_TELEPHOTO = "rear_telephoto"
    REAR_MACRO = "rear_macro"
    UNKNOWN = "unknown"


class OutputFormat(str, Enum):
    RAW_SENSOR = "raw_sensor"
    DNG = "dng"
    RAW10 = "raw10"
    YUV_420_888 = "yuv_420_888"
    JPEG = "jpeg"
    HEIF = "heif"


class CaptureMode(str, Enum):
    CONTROLLED_DIFFUSE = "controlled_diffuse"
    CROSS_POLARIZED = "cross_polarized"
    AMBIENT_RELATIVE = "ambient_relative"


class BaselineProfileStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class QualificationLevel(str, Enum):
    CAPTURE_CANDIDATE = "capture_candidate"
    COLOUR_VALIDATED = "colour_validated"
    CROSS_POLARIZED_VALIDATED = "cross_polarized_validated"


class ChartCondition(str, Enum):
    GOOD = "good"
    WORN = "worn"
    UNKNOWN = "unknown"
    NOT_PRESENT = "not_present"


class DevicePipelineFingerprint(BaselineContract):
    """Stable public pipeline identity; never a physical-device serial/ID."""

    platform: Platform
    manufacturer: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=160)
    camera_id: str = Field(min_length=1, max_length=160)
    physical_camera_ids: list[str] = Field(default_factory=list, max_length=16)
    camera_facing: CameraFacing
    lens_role: LensRole
    os_release: str = Field(min_length=1, max_length=80)
    security_patch: str = Field(min_length=1, max_length=80)
    camera_api: CameraAPI
    capture_runtime: str = Field(min_length=1, max_length=100)
    capture_runtime_version: str = Field(min_length=1, max_length=80)
    capture_app_version: str = Field(min_length=1, max_length=80)
    capture_pipeline_revision: str = Field(min_length=1, max_length=100)
    output_format: OutputFormat
    colour_profile_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    hardware_level: str = Field(min_length=1, max_length=40)
    pixel_array_width: int | None = Field(default=None, ge=1, le=20000)
    pixel_array_height: int | None = Field(default=None, ge=1, le=20000)
    physical_sensor_width_mm: str | None = Field(default=None, min_length=1, max_length=32)
    physical_sensor_height_mm: str | None = Field(default=None, min_length=1, max_length=32)
    focal_lengths_mm: list[str] = Field(default_factory=list, max_length=16)
    colour_filter_arrangement: int | None = None
    sensor_calibration_transform1_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    sensor_calibration_transform2_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    sensor_color_transform1_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    sensor_color_transform2_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    sensor_forward_matrix1_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    sensor_forward_matrix2_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    reference_illuminant1: int | None = None
    reference_illuminant2: int | None = None
    available_request_keys: list[str] = Field(default_factory=list, max_length=1000)
    available_result_keys: list[str] = Field(default_factory=list, max_length=1000)
    raw_output_sizes: list[str] = Field(default_factory=list, max_length=100)
    jpeg_output_sizes: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_platform_api(self) -> "DevicePipelineFingerprint":
        if self.platform == Platform.ANDROID and self.camera_api == CameraAPI.IOS_AVFOUNDATION:
            raise ValueError("iOS AVFoundation cannot identify an Android capture pipeline")
        if self.platform == Platform.IOS and self.camera_api != CameraAPI.IOS_AVFOUNDATION:
            raise ValueError("iOS capture pipelines must use AVFoundation")
        if self.lens_role == LensRole.FRONT and self.camera_facing != CameraFacing.FRONT:
            raise ValueError("front lens role requires front-facing camera")
        if self.lens_role in {
            LensRole.REAR_WIDE,
            LensRole.REAR_ULTRAWIDE,
            LensRole.REAR_TELEPHOTO,
            LensRole.REAR_MACRO,
        } and self.camera_facing != CameraFacing.REAR:
            raise ValueError("rear lens roles require rear-facing camera")
        if self.camera_facing == CameraFacing.EXTERNAL and self.lens_role != LensRole.UNKNOWN:
            raise ValueError("external cameras must use unknown lens role until independently classified")
        if self.output_format in {OutputFormat.JPEG, OutputFormat.HEIF} and not self.colour_profile_sha256:
            raise ValueError("processed image formats require a pinned colour-profile digest")
        return self

    @property
    def fingerprint_sha256(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


class DeviceCaptureCapabilities(BaselineContract):
    """Client-reported session capabilities; not trusted until attested."""

    output_width: int = Field(ge=1, le=20_000)
    output_height: int = Field(ge=1, le=20_000)
    exposure_lock_supported: bool
    exposure_lock_applied: bool
    white_balance_lock_supported: bool
    white_balance_lock_applied: bool
    raw_capture_supported: bool
    raw_capture_used: bool
    sensor_colour_calibration_available: bool
    output_colour_profile_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    hdr_disabled: bool | None = None
    beauty_processing_disabled: bool | None = None
    capture_mode: CaptureMode
    chart_condition: ChartCondition
    chart_profile_id: str | None = Field(default=None, min_length=1, max_length=128)
    chart_profile_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_session_claims(self) -> "DeviceCaptureCapabilities":
        if self.raw_capture_used and not self.raw_capture_supported:
            raise ValueError("raw capture cannot be used when the camera reports no raw support")
        if self.raw_capture_used and self.output_colour_profile_sha256 is not None:
            raise ValueError("raw sensor output must not claim a processed output ICC profile")
        if self.chart_condition == ChartCondition.NOT_PRESENT:
            if self.chart_profile_id is not None or self.chart_profile_sha256 is not None:
                raise ValueError("absent chart cannot carry chart profile metadata")
        elif not self.chart_profile_id or not self.chart_profile_sha256:
            raise ValueError("present chart condition requires a pinned chart profile")
        return self


class DeviceCaptureReport(BaselineContract):
    schema_version: Literal["dsi-device-capture-v1"] = "dsi-device-capture-v1"
    fingerprint: DevicePipelineFingerprint
    capabilities: DeviceCaptureCapabilities
    # A reference is a locator only; this service does not verify its signature.
    capture_attestation_ref: str | None = Field(default=None, min_length=8, max_length=256)


class MinimumCaptureStandard(BaselineContract):
    minimum_width: int = Field(ge=1, le=20_000)
    minimum_height: int = Field(ge=1, le=20_000)
    required_capture_modes: list[CaptureMode] = Field(min_length=1)
    accepted_output_formats: list[OutputFormat] = Field(min_length=1)
    require_exposure_lock: bool = True
    require_white_balance_lock: bool = True
    require_hdr_disabled: bool = True
    require_beauty_processing_disabled: bool = True
    require_chart_in_frame: bool = True
    required_chart_profile_id: str | None = Field(default=None, min_length=1, max_length=128)
    required_chart_profile_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    require_raw_or_colour_profile: bool = True

    @model_validator(mode="after")
    def validate_standard(self) -> "MinimumCaptureStandard":
        if self.required_chart_profile_sha256 and not self.required_chart_profile_id:
            raise ValueError("required chart digest requires a chart profile ID")
        if self.required_chart_profile_id and not self.require_chart_in_frame:
            raise ValueError("a required chart profile implies chart-in-frame requirement")
        if len(self.required_capture_modes) != len(set(self.required_capture_modes)):
            raise ValueError("required capture modes must be unique")
        if len(self.accepted_output_formats) != len(set(self.accepted_output_formats)):
            raise ValueError("accepted output formats must be unique")
        return self


class DeviceValidationEvidence(BaselineContract):
    calibration_profile_ref: str = Field(min_length=8, max_length=256)
    calibration_profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    validation_report_ref: str = Field(min_length=8, max_length=256)
    validation_report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluation_dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reference_instrument_model: str = Field(min_length=1, max_length=128)
    reference_instrument_calibration_ref: str = Field(min_length=8, max_length=256)
    independent_review_ref: str = Field(min_length=8, max_length=256)
    approved_by: str = Field(min_length=2, max_length=120)
    approved_at: datetime
    valid_until: datetime
    evaluated_device_unit_count: int = Field(ge=1)
    validated_regions: list[str] = Field(min_length=1)
    validated_measured_lightness_ranges: list[str] = Field(min_length=1)
    evaluated_lighting_profiles: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_approval_window(self) -> "DeviceValidationEvidence":
        for value in (self.approved_at, self.valid_until):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("device validation timestamps must be timezone-aware")
        if self.valid_until <= self.approved_at:
            raise ValueError("device baseline validity must end after approval")
        return self


class DeviceBaselineProfile(BaselineContract):
    profile_id: str = Field(min_length=3, max_length=120)
    profile_version: str = Field(min_length=1, max_length=40)
    fingerprint: DevicePipelineFingerprint
    status: BaselineProfileStatus
    qualification_level: QualificationLevel
    minimum_standard: MinimumCaptureStandard
    validation: DeviceValidationEvidence | None = None
    cross_polarization_validation_report_ref: str | None = Field(default=None, min_length=8, max_length=256)
    cross_polarization_validation_report_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_qualification_evidence(self) -> "DeviceBaselineProfile":
        if self.qualification_level == QualificationLevel.CAPTURE_CANDIDATE:
            if self.validation is not None:
                raise ValueError("capture-candidate profiles cannot claim validated colour evidence")
            if self.cross_polarization_validation_report_ref or self.cross_polarization_validation_report_sha256:
                raise ValueError("capture-candidate profiles cannot claim polarization validation")
        else:
            if self.status != BaselineProfileStatus.ACTIVE:
                raise ValueError("validated device profiles must be active")
            if self.validation is None:
                raise ValueError("validated device profiles require independent validation evidence")
        if self.qualification_level == QualificationLevel.CROSS_POLARIZED_VALIDATED:
            if not self.cross_polarization_validation_report_ref or not self.cross_polarization_validation_report_sha256:
                raise ValueError("cross-polarized profile requires its own optical validation report")
            if CaptureMode.CROSS_POLARIZED not in self.minimum_standard.required_capture_modes:
                raise ValueError("cross-polarized profile must require cross-polarized capture")
        elif self.cross_polarization_validation_report_ref or self.cross_polarization_validation_report_sha256:
            raise ValueError("cross-polarization evidence is only valid for a cross-polarized profile")
        return self


class DeviceBaselineRegistry(BaselineContract):
    schema_version: Literal["dsi-device-baseline-registry-v1"]
    registry_version: str = Field(min_length=1, max_length=40)
    profiles: list[DeviceBaselineProfile] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def validate_unique_profiles(self) -> "DeviceBaselineRegistry":
        ids = [profile.profile_id for profile in self.profiles]
        fingerprints = [profile.fingerprint.fingerprint_sha256 for profile in self.profiles]
        if len(ids) != len(set(ids)):
            raise ValueError("device baseline profile IDs must be unique")
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("each exact camera pipeline fingerprint may have only one baseline")
        return self


def evaluate_minimum_standard(report: DeviceCaptureReport, standard: MinimumCaptureStandard) -> list[str]:
    """Return failure reasons for the exact session declarations."""
    fingerprint = report.fingerprint
    capabilities = report.capabilities
    reasons: list[str] = []

    if fingerprint.output_format not in standard.accepted_output_formats:
        reasons.append("output_format_not_accepted")
    if capabilities.output_width < standard.minimum_width or capabilities.output_height < standard.minimum_height:
        reasons.append("output_resolution_below_device_baseline")
    if standard.require_exposure_lock and (
        not capabilities.exposure_lock_supported or not capabilities.exposure_lock_applied
    ):
        reasons.append("manual_or_locked_exposure_unavailable")
    if standard.require_white_balance_lock and (
        not capabilities.white_balance_lock_supported or not capabilities.white_balance_lock_applied
    ):
        reasons.append("white_balance_lock_unavailable")
    if standard.require_hdr_disabled and not capabilities.hdr_disabled:
        reasons.append("hdr_processing_not_disabled")
    if standard.require_beauty_processing_disabled and not capabilities.beauty_processing_disabled:
        reasons.append("beauty_processing_not_disabled")
    if capabilities.capture_mode not in standard.required_capture_modes:
        reasons.append("capture_mode_not_qualified")
    if standard.require_chart_in_frame:
        if capabilities.chart_condition != ChartCondition.GOOD:
            reasons.append("valid_in_frame_colour_reference_required")
        if standard.required_chart_profile_id and capabilities.chart_profile_id != standard.required_chart_profile_id:
            reasons.append("chart_profile_id_mismatch")
        if standard.required_chart_profile_sha256 and capabilities.chart_profile_sha256 != standard.required_chart_profile_sha256:
            reasons.append("chart_profile_digest_mismatch")
    if standard.require_raw_or_colour_profile:
        raw_path_valid = (
            fingerprint.output_format in {OutputFormat.RAW_SENSOR, OutputFormat.DNG, OutputFormat.RAW10}
            and capabilities.raw_capture_supported
            and capabilities.raw_capture_used
            and capabilities.sensor_colour_calibration_available
        )
        profiled_path_valid = (
            fingerprint.output_format in {OutputFormat.JPEG, OutputFormat.HEIF, OutputFormat.YUV_420_888}
            and fingerprint.colour_profile_sha256 is not None
            and capabilities.output_colour_profile_sha256 == fingerprint.colour_profile_sha256
        )
        if not (raw_path_valid or profiled_path_valid):
            reasons.append("raw_sensor_or_pinned_colour_profile_required")
    return reasons


def baseline_result(
    report: DeviceCaptureReport,
    registry: DeviceBaselineRegistry | None,
    *,
    registry_configured: bool,
    capture_attestation_verified: bool = False,
    now: datetime | None = None,
) -> dict[str, object]:
    """Resolve exact device pipeline; attestation flag is server-internal only."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("resolver time must be timezone-aware")

    result: dict[str, object] = {
        "schema_version": "dsi-device-baseline-result-v1",
        "registry_configured": registry_configured,
        "registry_version": registry.registry_version if registry else None,
        "device_pipeline_fingerprint_sha256": report.fingerprint.fingerprint_sha256,
        "device_identity_verified": capture_attestation_verified,
        "operational_tier": "relative_only",
        "profile_match": "none",
        "profile_id": None,
        "profile_version": None,
        "qualification_level": None,
        "device_pipeline_colour_qualified": False,
        "cross_polarized_pipeline_qualified": False,
        "absolute_colour_measurement_allowed": False,
        "individual_measurement_release_required": True,
        "validated_scope": None,
        "review_required_reasons": [],
        "minimum_capture_standard": {
            "chart_in_frame": True,
            "white_balance_locked": True,
            "exposure_locked": True,
            "hdr_disabled": True,
            "beauty_processing_disabled": True,
            "raw_or_pinned_colour_profile": True,
            "exact_device_pipeline_profile_required": True,
        },
        "note": (
            "A baseline qualifies an exact camera pipeline, not a brand name alone. "
            "Client-reported identity and capabilities are declarations, not attestations. "
            "Unknown or unverified pipelines remain relative-only."
        ),
    }

    if not registry_configured or registry is None:
        result["review_required_reasons"] = ["device_baseline_registry_not_configured"]
        return result

    matches = [
        profile for profile in registry.profiles
        if profile.fingerprint.fingerprint_sha256 == report.fingerprint.fingerprint_sha256
    ]
    if not matches:
        result["review_required_reasons"] = ["no_exact_camera_pipeline_profile"]
        return result

    profile = matches[0]
    result["profile_match"] = "exact_client_claim_match"
    result["profile_id"] = profile.profile_id
    result["profile_version"] = profile.profile_version
    result["qualification_level"] = profile.qualification_level.value

    if profile.status != BaselineProfileStatus.ACTIVE:
        result["review_required_reasons"] = [f"device_profile_{profile.status.value}"]
        return result

    if profile.validation is not None:
        if now < profile.validation.approved_at or now >= profile.validation.valid_until:
            result["review_required_reasons"] = ["device_profile_validation_expired_or_not_yet_valid"]
            return result

    failures = evaluate_minimum_standard(report, profile.minimum_standard)
    if failures:
        result["review_required_reasons"] = failures
        return result

    if not capture_attestation_verified:
        result["profile_match"] = "exact_claim_match_attestation_pending"
        result["review_required_reasons"] = ["trusted_capture_attestation_not_verified"]
        return result

    if profile.qualification_level == QualificationLevel.CAPTURE_CANDIDATE:
        result["operational_tier"] = "controlled_capture_candidate"
    elif profile.qualification_level == QualificationLevel.COLOUR_VALIDATED:
        result["operational_tier"] = "colour_validated"
        result["device_pipeline_colour_qualified"] = True
        result["validated_scope"] = {
            "regions": profile.validation.validated_regions,
            "measured_lightness_ranges": profile.validation.validated_measured_lightness_ranges,
            "lighting_profiles": profile.validation.evaluated_lighting_profiles,
        }
    elif profile.qualification_level == QualificationLevel.CROSS_POLARIZED_VALIDATED:
        if report.capabilities.capture_mode != CaptureMode.CROSS_POLARIZED:
            result["review_required_reasons"] = ["cross_polarized_capture_required"]
            return result
        result["operational_tier"] = "cross_polarized_validated"
        result["device_pipeline_colour_qualified"] = True
        result["cross_polarized_pipeline_qualified"] = True
        result["validated_scope"] = {
            "regions": profile.validation.validated_regions,
            "measured_lightness_ranges": profile.validation.validated_measured_lightness_ranges,
            "lighting_profiles": profile.validation.evaluated_lighting_profiles,
        }
    result["review_required_reasons"] = []
    return result


def load_device_baseline_registry() -> tuple[DeviceBaselineRegistry | None, bool]:
    """Load deployment-mounted registry whose exact bytes are pinned by SHA-256."""
    configured_path = os.getenv("DSI_DEVICE_BASELINE_REGISTRY_PATH", "").strip()
    expected_sha256 = os.getenv("DSI_DEVICE_BASELINE_REGISTRY_SHA256", "").strip().lower()
    if not configured_path and not expected_sha256:
        return None, False
    if not configured_path or len(expected_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in expected_sha256):
        raise DeviceBaselineError("device baseline registry path and SHA-256 pin must both be configured")

    path = Path(configured_path)
    try:
        if not path.is_file() or path.stat().st_size > 1_000_000:
            raise DeviceBaselineError("device baseline registry file is missing or too large")
        raw = path.read_bytes()
    except OSError as exc:
        raise DeviceBaselineError("device baseline registry cannot be read") from exc

    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise DeviceBaselineError("device baseline registry SHA-256 mismatch")
    try:
        registry = DeviceBaselineRegistry.model_validate_json(raw)
    except Exception as exc:
        raise DeviceBaselineError("device baseline registry schema is invalid") from exc
    return registry, True
