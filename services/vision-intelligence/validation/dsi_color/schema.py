"""Schemas for offline DSI colour-model validation.

The evaluator accepts only pseudonymous metadata and independently measured
reference values. It intentionally has no field for photographs, videos,
face embeddings, names, email addresses or other direct identifiers.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class LightingProfile(str, Enum):
    CONTROLLED = "controlled"
    DAYLIGHT = "daylight"
    INDOOR = "indoor"
    MIXED = "mixed"
    LOW_LIGHT = "low_light"
    UNKNOWN = "unknown"


class SkinRegion(str, Enum):
    FACE_SKIN = "face_skin"
    BODY_SKIN = "body_skin"


class LabD50(StrictRecord):
    l_star: float = Field(ge=0, le=100)
    a_star: float = Field(ge=-128, le=127)
    b_star: float = Field(ge=-128, le=127)


class EvaluationManifest(StrictRecord):
    dataset_version: str = Field(min_length=1, max_length=100)
    created_at: datetime
    held_out_test_data: Literal[True]
    rights_provenance_ref: str = Field(min_length=8, max_length=256)
    consent_registry_ref: str = Field(min_length=8, max_length=256)
    training_overlap_audit_ref: str = Field(min_length=8, max_length=256)
    independent_ground_truth_protocol_ref: str = Field(min_length=8, max_length=256)
    reference_instrument_model: str = Field(min_length=1, max_length=128)
    reference_instrument_calibration_ref: str = Field(min_length=8, max_length=256)
    reference_measurement_standard: Literal["CIE_LAB_D50_2DEG"]
    source_images_included: Literal[False] = False
    source_videos_included: Literal[False] = False
    face_templates_included: Literal[False] = False
    direct_identifiers_included: Literal[False] = False

    @model_validator(mode="after")
    def validate_timestamp(self) -> "EvaluationManifest":
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return self


class ColorValidationSample(StrictRecord):
    record_id: str = Field(pattern=r"^eval_[A-Za-z0-9_-]{12,96}$")
    dataset_version: str = Field(min_length=1, max_length=100)
    evaluation_split: Literal["held_out_test"]

    # Stable, non-reversible subject pseudonym for clustered statistics.
    subject_ref: str = Field(pattern=r"^hmac-sha256:[a-f0-9]{64}$")
    capture_ref: str = Field(pattern=r"^cap_[A-Za-z0-9_-]{12,96}$")
    capture_session_ref: str = Field(pattern=r"^ses_[A-Za-z0-9_-]{12,96}$")

    region: SkinRegion
    camera_vendor: str = Field(min_length=1, max_length=100)
    camera_model: str = Field(min_length=1, max_length=160)
    operating_system_family: str = Field(min_length=1, max_length=80)
    lighting_profile: LightingProfile

    skin_model_name: str = Field(min_length=1, max_length=128)
    skin_model_version: str = Field(min_length=1, max_length=80)
    skin_model_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    segmentation_model_version: str = Field(min_length=1, max_length=80)
    segmentation_model_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    chart_profile_id: str = Field(min_length=1, max_length=128)
    chart_profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    chart_patch_count_used: int | None = Field(default=None, ge=18, le=24)
    chart_fit_p95_delta_e_2000: float | None = Field(default=None, ge=0, le=100)
    chart_age_months_declared: int | None = Field(default=None, ge=0)
    chart_condition_declared: Literal["good", "worn", "unknown"] = "unknown"

    reference_instrument_model: str = Field(min_length=1, max_length=128)
    reference_instrument_calibration_ref: str = Field(min_length=8, max_length=256)
    reference_measurement_geometry: Literal["45_0", "0_45", "other_documented"]
    reference_uncertainty_delta_e_2000: float = Field(gt=0, le=20)
    reference_lab_d50: LabD50

    prediction_status: Literal["completed", "failed"]
    predicted_lab_d50: LabD50 | None = None
    failure_code: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_prediction_state(self) -> "ColorValidationSample":
        if self.prediction_status == "completed":
            if self.predicted_lab_d50 is None or self.failure_code is not None:
                raise ValueError("completed predictions require Lab output and no failure code")
            if self.chart_patch_count_used is None or self.chart_fit_p95_delta_e_2000 is None:
                raise ValueError("completed predictions require chart-fit diagnostics")
        else:
            if self.predicted_lab_d50 is not None or not self.failure_code:
                raise ValueError("failed predictions require a failure code and no Lab output")
        return self


class ReleasePolicy(StrictRecord):
    policy_id: str = Field(min_length=1, max_length=100)
    policy_version: str = Field(min_length=1, max_length=40)
    approved_by: str | None = Field(default=None, min_length=2, max_length=120)
    approval_ref: str | None = Field(default=None, min_length=8, max_length=256)
    independent_review_ref: str | None = Field(default=None, min_length=8, max_length=256)
    approved_at: datetime | None = None

    minimum_unique_subjects: int | None = Field(default=None, ge=2)
    minimum_successful_samples: int | None = Field(default=None, ge=1)
    minimum_samples_per_slice: int | None = Field(default=None, ge=1)
    required_regions: list[SkinRegion] | None = None
    required_lighting_profiles: list[LightingProfile] | None = None

    maximum_failure_rate: float | None = Field(default=None, ge=0, le=1)
    maximum_median_delta_e_2000: float | None = Field(default=None, gt=0, le=100)
    maximum_p95_delta_e_2000: float | None = Field(default=None, gt=0, le=100)
    maximum_absolute_l_bias: float | None = Field(default=None, gt=0, le=100)
    maximum_absolute_a_bias: float | None = Field(default=None, gt=0, le=255)
    maximum_absolute_b_bias: float | None = Field(default=None, gt=0, le=255)
    maximum_repeatability_median_delta_e_2000: float | None = Field(default=None, gt=0, le=100)
    maximum_chart_fit_p95_delta_e_2000: float | None = Field(default=None, gt=0, le=100)

    bootstrap_repetitions: int = Field(default=500, ge=100, le=5000)
    bootstrap_seed: int = Field(default=20261114, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def validate_approval_timestamp(self) -> "ReleasePolicy":
        if self.approved_at is not None and (
            self.approved_at.tzinfo is None or self.approved_at.utcoffset() is None
        ):
            raise ValueError("approved_at must be timezone-aware")
        return self

    def missing_release_fields(self) -> list[str]:
        required = (
            "approved_by",
            "approval_ref",
            "independent_review_ref",
            "approved_at",
            "minimum_unique_subjects",
            "minimum_successful_samples",
            "minimum_samples_per_slice",
            "required_regions",
            "required_lighting_profiles",
            "maximum_failure_rate",
            "maximum_median_delta_e_2000",
            "maximum_p95_delta_e_2000",
            "maximum_absolute_l_bias",
            "maximum_absolute_a_bias",
            "maximum_absolute_b_bias",
            "maximum_repeatability_median_delta_e_2000",
            "maximum_chart_fit_p95_delta_e_2000",
        )
        return [name for name in required if getattr(self, name) is None]
