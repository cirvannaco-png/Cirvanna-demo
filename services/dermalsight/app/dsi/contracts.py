"""Versioned, privacy-minimising DSI domain contracts.

These contracts describe validated outputs and authorized intents. They do not
perform image inference, retain media, identify people or create consent.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DSIContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class BodyRegion(str, Enum):
    FACE = "face"
    NECK = "neck"
    CHEST = "chest"
    LEFT_UPPER_ARM = "left_upper_arm"
    RIGHT_UPPER_ARM = "right_upper_arm"
    LEFT_FOREARM = "left_forearm"
    RIGHT_FOREARM = "right_forearm"
    LEFT_HAND = "left_hand"
    RIGHT_HAND = "right_hand"
    LEFT_THIGH = "left_thigh"
    RIGHT_THIGH = "right_thigh"
    LEFT_LOWER_LEG = "left_lower_leg"
    RIGHT_LOWER_LEG = "right_lower_leg"
    OTHER = "other"


class ModelTask(str, Enum):
    SKIN_TONE_ESTIMATION = "skin_tone_estimation"
    BODY_REGION_SEGMENTATION = "body_region_segmentation"
    FACIAL_GEOMETRY = "facial_geometry"
    COSMETIC_ATTRIBUTE_ANALYSIS = "cosmetic_attribute_analysis"
    APPEARANCE_CORRECTION = "appearance_correction"


class CaptureKind(str, Enum):
    STILL = "still"
    VIDEO_FRAME = "video_frame"


class CaptureQuality(str, Enum):
    ACCEPTED = "accepted"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


class LightingProfile(str, Enum):
    CONTROLLED = "controlled"
    UNCONTROLLED = "uncontrolled"


class ToneMeasurementStatus(str, Enum):
    CALIBRATED = "calibrated"
    RELATIVE_ONLY = "relative_only"
    REVIEW_REQUIRED = "review_required"


class FaceShape(str, Enum):
    OVAL = "oval"
    ROUND = "round"
    SQUARE = "square"
    HEART = "heart"
    DIAMOND = "diamond"
    OBLONG = "oblong"
    UNKNOWN = "unknown"


class HairlineShape(str, Enum):
    ROUNDED = "rounded"
    STRAIGHT = "straight"
    WIDOWS_PEAK = "widows_peak"
    HIGH_OR_RECEDING_APPEARANCE = "high_or_receding_appearance"
    UNKNOWN = "unknown"


class ConsentPurpose(str, Enum):
    COSMETIC_SKIN_ANALYSIS = "cosmetic_skin_analysis"
    FACIAL_GEOMETRY_ANALYSIS = "facial_geometry_analysis"
    BODY_TONE_ANALYSIS = "body_tone_analysis"
    APPEARANCE_CORRECTION = "appearance_correction"
    GLOBAL_MODEL_TRAINING = "global_model_training"


class CorrectionOperation(str, Enum):
    MAKEUP_PLACEMENT_PREVIEW = "makeup_placement_preview"
    FOUNDATION_SHADE_PREVIEW = "foundation_shade_preview"
    CONCEALER_PLACEMENT_PREVIEW = "concealer_placement_preview"
    HAIRSTYLE_PREVIEW = "hairstyle_preview"
    COSMETIC_COLOR_PREVIEW = "cosmetic_color_preview"


class ModelEvidence(DSIContract):
    task: ModelTask
    model_name: str = Field(min_length=1, max_length=100)
    model_version: str = Field(min_length=1, max_length=64)
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    validation_report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    validation_report_ref: str = Field(min_length=8, max_length=256)
    evaluation_dataset_version: str = Field(min_length=1, max_length=100)
    evaluated_population_slices: list[str] = Field(min_length=1, max_length=64)
    validation_decision: Literal["approved"]

    @model_validator(mode="after")
    def validate_task_coverage(self) -> "ModelEvidence":
        slices = {item.strip().casefold() for item in self.evaluated_population_slices}
        required_by_task = {
            ModelTask.SKIN_TONE_ESTIMATION: {"skin_tone", "lighting", "device"},
            ModelTask.BODY_REGION_SEGMENTATION: {"skin_tone", "body_region", "lighting", "device"},
            ModelTask.FACIAL_GEOMETRY: {"skin_tone", "pose", "occlusion", "camera"},
            ModelTask.COSMETIC_ATTRIBUTE_ANALYSIS: {"skin_tone", "lighting", "device"},
            ModelTask.APPEARANCE_CORRECTION: {"skin_tone", "lighting", "device", "geometry_preservation"},
        }
        missing = required_by_task[self.task] - slices
        if missing:
            raise ValueError(
                f"model validation evidence is missing task-specific evaluation slices: {sorted(missing)}"
            )
        return self


class CaptureEvidence(DSIContract):
    capture_ref: str = Field(pattern=r"^cap_[A-Za-z0-9_-]{12,96}$")
    capture_session_ref: str = Field(pattern=r"^ses_[A-Za-z0-9_-]{12,96}$")
    kind: CaptureKind
    quality: CaptureQuality
    lighting: LightingProfile
    white_balance_locked: bool
    exposure_locked: bool
    color_reference_id: str | None = Field(default=None, min_length=3, max_length=128)
    quality_report_ref: str | None = Field(default=None, min_length=8, max_length=256)
    quality_assessor_version: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_capture_quality(self) -> "CaptureEvidence":
        if not self.quality_report_ref or not self.quality_assessor_version:
            raise ValueError("every capture decision requires a versioned quality report")
        if self.quality == CaptureQuality.ACCEPTED:
            if self.lighting != LightingProfile.CONTROLLED:
                raise ValueError("accepted capture requires controlled lighting")
            if not self.white_balance_locked or not self.exposure_locked:
                raise ValueError("accepted capture requires locked white balance and exposure")
        return self


class CIELABEstimate(DSIContract):
    l_star: float = Field(ge=0, le=100)
    a_star: float = Field(ge=-128, le=127)
    b_star: float = Field(ge=-128, le=127)
    delta_e_uncertainty: float = Field(gt=0, le=100)
    color_reference_id: str = Field(min_length=3, max_length=128)
    calibration_report_ref: str = Field(min_length=8, max_length=256)


class ToneObservation(DSIContract):
    region: BodyRegion
    capture: CaptureEvidence
    status: ToneMeasurementStatus
    cielab: CIELABEstimate | None = None
    relative_tone_index: float | None = Field(default=None, ge=0, le=1)
    relative_uncertainty: float | None = Field(default=None, gt=0, le=1)

    @model_validator(mode="after")
    def validate_measurement_evidence(self) -> "ToneObservation":
        if self.capture.quality != CaptureQuality.ACCEPTED:
            if self.status != ToneMeasurementStatus.REVIEW_REQUIRED:
                raise ValueError("non-accepted captures cannot produce a tone measurement")
            if (
                self.cielab is not None
                or self.relative_tone_index is not None
                or self.relative_uncertainty is not None
            ):
                raise ValueError("non-accepted captures cannot carry measured tone values")
            return self

        if self.status == ToneMeasurementStatus.CALIBRATED:
            if self.cielab is None or self.relative_tone_index is not None:
                raise ValueError("calibrated tone requires CIELAB and forbids a relative-only value")
            if self.capture.color_reference_id != self.cielab.color_reference_id:
                raise ValueError("tone calibration reference must match the capture reference")
            if self.relative_uncertainty is not None:
                raise ValueError("calibrated CIELAB observations cannot carry relative uncertainty")
        elif self.status == ToneMeasurementStatus.RELATIVE_ONLY:
            if self.cielab is not None or self.relative_tone_index is None:
                raise ValueError("relative-only tone requires a relative index and forbids CIELAB")
            if self.relative_uncertainty is None:
                raise ValueError("relative-only tone requires an uncertainty bound")
            if self.capture.lighting != LightingProfile.CONTROLLED:
                raise ValueError("relative tone comparison requires controlled lighting")
        elif (
            self.cielab is not None
            or self.relative_tone_index is not None
            or self.relative_uncertainty is not None
        ):
            raise ValueError("review-required observations cannot carry measured tone values")
        return self


class BodyToneAlignment(DSIContract):
    observations: list[ToneObservation] = Field(min_length=2, max_length=len(BodyRegion))
    model_evidence: list[ModelEvidence] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def validate_regions_and_models(self) -> "BodyToneAlignment":
        regions = [item.region for item in self.observations]
        if len(regions) != len(set(regions)):
            raise ValueError("body-tone observations must have unique body regions")
        tasks = {item.task for item in self.model_evidence}
        required = {ModelTask.SKIN_TONE_ESTIMATION, ModelTask.BODY_REGION_SEGMENTATION}
        if not required.issubset(tasks):
            raise ValueError("body-tone alignment requires tone-estimation and region-segmentation evidence")
        relative = [
            item for item in self.observations
            if item.status == ToneMeasurementStatus.RELATIVE_ONLY
        ]
        if relative and len({item.capture.capture_session_ref for item in relative}) != 1:
            raise ValueError("relative-only tone comparisons must share one capture session")
        return self


class IntervalEstimate(DSIContract):
    point: float = Field(ge=0, le=3)
    lower: float = Field(ge=0, le=3)
    upper: float = Field(ge=0, le=3)

    @model_validator(mode="after")
    def validate_interval(self) -> "IntervalEstimate":
        if not self.lower <= self.point <= self.upper:
            raise ValueError("estimate point must lie within its uncertainty interval")
        return self


class FacialGeometry(DSIContract):
    face_shape: FaceShape
    hairline_shape: HairlineShape
    face_width_to_height: IntervalEstimate
    jaw_to_cheek_width: IntervalEstimate
    forehead_to_cheek_width: IntervalEstimate
    landmark_coverage: float = Field(ge=0, le=1)
    model_evidence: ModelEvidence

    @model_validator(mode="after")
    def require_geometry_model(self) -> "FacialGeometry":
        if self.model_evidence.task != ModelTask.FACIAL_GEOMETRY:
            raise ValueError("facial geometry requires facial_geometry model evidence")
        return self


class DermalSightProfile(DSIContract):
    profile_id: UUID
    contract_version: Literal["1"] = "1"
    created_at: datetime
    body_tone: BodyToneAlignment | None = None
    facial_geometry: FacialGeometry | None = None
    media_retained: Literal[False] = False
    identity_recognition_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_timestamp_and_payload(self) -> "DermalSightProfile":
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.body_tone is None and self.facial_geometry is None:
            raise ValueError("profile must contain at least one validated assessment")
        return self


class PurposeConsent(DSIContract):
    receipt_ref: str = Field(pattern=r"^consent_[A-Za-z0-9_-]{12,96}$")
    subject_binding_ref: str = Field(pattern=r"^hmac-sha256:[a-f0-9]{64}$")
    purpose: ConsentPurpose
    issued_at: datetime
    expires_at: datetime
    active: bool
    revoked: bool
    verified_by_privacy_service: bool
    verification_ref: str = Field(min_length=8, max_length=256)

    @model_validator(mode="after")
    def validate_consent_dates(self) -> "PurposeConsent":
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("consent timestamps must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValueError("consent expiry must follow issuance")
        return self


class GlobalLearningAggregate(DSIContract):
    """Aggregate-only evaluation record; never carries per-user training examples."""

    task: ModelTask
    dataset_version: str = Field(min_length=1, max_length=100)
    consented_dataset_receipt_ref: str = Field(min_length=8, max_length=256)
    purpose_consent_registry_ref: str = Field(min_length=8, max_length=256)
    training_consent_scope: Literal["global_model_training"]
    independent_review_ref: str = Field(min_length=8, max_length=256)
    distinct_contributors: int = Field(ge=30)
    aggregate_metrics: dict[str, float] = Field(min_length=1, max_length=64)
    source_images_included: Literal[False] = False
    face_templates_included: Literal[False] = False
    subject_identifiers_included: Literal[False] = False
    individual_profiles_included: Literal[False] = False

    @model_validator(mode="after")
    def validate_aggregate_metrics(self) -> "GlobalLearningAggregate":
        for name, value in self.aggregate_metrics.items():
            if isinstance(value, bool) or not isfinite(value) or not name.strip() or not 0 <= value <= 1:
                raise ValueError("aggregate metrics must be finite, named numeric values in [0, 1]")
        return self


class AppearanceCorrectionPlan(DSIContract):
    operation: CorrectionOperation
    model_evidence: ModelEvidence
    consent: PurposeConsent
    identity_preservation_required: Literal[True] = True
    facial_geometry_change_allowed: Literal[False] = False
    diagnostic_claims_allowed: Literal[False] = False
    public_media_output_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_correction_scope(self) -> "AppearanceCorrectionPlan":
        if self.model_evidence.task != ModelTask.APPEARANCE_CORRECTION:
            raise ValueError("appearance correction requires appearance_correction model evidence")
        if self.consent.purpose != ConsentPurpose.APPEARANCE_CORRECTION:
            raise ValueError("appearance correction requires its own explicit consent purpose")
        now = datetime.now(timezone.utc)
        if not self.consent.verified_by_privacy_service:
            raise ValueError("appearance correction consent must be verified by the privacy service")
        if not self.consent.active or self.consent.revoked:
            raise ValueError("appearance correction consent must be active and not revoked")
        if now < self.consent.issued_at or now >= self.consent.expires_at:
            raise ValueError("appearance correction consent must be currently valid")
        return self
