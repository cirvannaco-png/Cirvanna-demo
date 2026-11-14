"""User-directed capture guidance; this module never accepts or processes media.

Capture plans are advisory instructions for a future client capture experience.
They do not grant consent, authorize inference, persist preferences or enable
image/video ingestion.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import BodyRegion


class AssessmentSelection(str, Enum):
    SKIN_TONE = "skin_tone"
    FACIAL_GEOMETRY = "facial_geometry"
    BODY_TONE_ALIGNMENT = "body_tone_alignment"


class ToneCaptureMode(str, Enum):
    CALIBRATED_CIELAB = "calibrated_cielab"
    RELATIVE_SAME_SESSION = "relative_same_session"


class CapturePlanRequest(BaseModel):
    """A user-selected capture scope. No media is attached to this request."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    assessments: list[AssessmentSelection] = Field(min_length=1, max_length=3)
    tone_capture_mode: ToneCaptureMode = ToneCaptureMode.RELATIVE_SAME_SESSION
    color_reference_available: bool = False
    body_regions: list[BodyRegion] = Field(default_factory=list, max_length=14)
    video_guidance_requested: bool = False

    @model_validator(mode="after")
    def validate_selected_scope(self) -> "CapturePlanRequest":
        if len(self.assessments) != len(set(self.assessments)):
            raise ValueError("assessment selections must be unique")
        if self.tone_capture_mode == ToneCaptureMode.CALIBRATED_CIELAB:
            if not self.color_reference_available:
                raise ValueError(
                    "calibrated CIELAB capture requires a supported physical colour reference"
                )
            if not (
                AssessmentSelection.SKIN_TONE in self.assessments
                or AssessmentSelection.BODY_TONE_ALIGNMENT in self.assessments
            ):
                raise ValueError("tone calibration is only relevant to tone assessments")
        if AssessmentSelection.BODY_TONE_ALIGNMENT in self.assessments:
            if len(self.body_regions) < 2:
                raise ValueError(
                    "body-tone alignment requires at least two user-selected regions"
                )
            if len(self.body_regions) != len(set(self.body_regions)):
                raise ValueError("body regions must be unique")
            if BodyRegion.OTHER in self.body_regions:
                raise ValueError("select a named body region rather than other")
        elif self.body_regions:
            raise ValueError("body regions can only be selected for body-tone alignment")
        return self


class CaptureStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str
    title: str
    instructions: list[str]
    required: bool
    applies_to: list[AssessmentSelection]


class CapturePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_version: Literal["1"] = "1"
    selected_assessments: list[AssessmentSelection]
    tone_capture_mode: ToneCaptureMode
    selected_body_regions: list[BodyRegion]
    steps: list[CaptureStep]
    video_guidance_requested: bool
    video_processing_enabled: Literal[False] = False
    image_processing_enabled: Literal[False] = False
    raw_media_retention_enabled: Literal[False] = False
    global_training_consent_included: Literal[False] = False
    optional_analysis_may_be_skipped: Literal[True] = True
    discovery_must_continue_without_dsi: Literal[True] = True
    notes: list[str]


def build_capture_plan(request: CapturePlanRequest) -> CapturePlan:
    """Build non-binding capture instructions from the user's explicit selection."""
    selected = set(request.assessments)
    steps: list[CaptureStep] = []

    if AssessmentSelection.SKIN_TONE in selected or AssessmentSelection.BODY_TONE_ALIGNMENT in selected:
        tone_assessments = [
            item for item in (
                AssessmentSelection.SKIN_TONE,
                AssessmentSelection.BODY_TONE_ALIGNMENT,
            ) if item in selected
        ]
        if request.tone_capture_mode == ToneCaptureMode.CALIBRATED_CIELAB:
            steps.append(
                CaptureStep(
                    step_id="tone_reference",
                    title="Prepare the colour reference",
                    instructions=[
                        "Use only a supported physical colour-reference card with a documented profile.",
                        "Place the reference beside the skin region in the same lighting and capture frame.",
                        "Keep the reference visible and unobstructed; do not substitute a screen image or guessed white balance.",
                    ],
                    required=True,
                    applies_to=tone_assessments,
                )
            )
        steps.append(
            CaptureStep(
                step_id="tone_stills",
                title="Capture skin regions",
                instructions=[
                    "Use diffuse, even light; avoid direct sun, coloured lights, beauty filters and strong shadows.",
                    "Keep the camera exposure and white balance locked for all compared regions.",
                    "Capture each selected region separately and keep the same camera, lighting and session where possible.",
                    "Do not apply makeup, tanning products or colour-altering filters for a measurement capture.",
                    "If the capture is uncomfortable or inconvenient, skip it; ordinary Cirvanna discovery remains available.",
                ],
                required=True,
                applies_to=tone_assessments,
            )
        )

    if AssessmentSelection.FACIAL_GEOMETRY in selected:
        steps.append(
            CaptureStep(
                step_id="facial_geometry_stills",
                title="Capture facial geometry views",
                instructions=[
                    "Capture one relaxed, front-facing still with the full face visible.",
                    "If comfortable, add left and right three-quarter views; these improve geometry coverage but are optional.",
                    "Keep hair away from the forehead only if you are comfortable doing so; never force a hairstyle change.",
                    "Remove beauty filters and avoid wide-angle close-ups that distort proportions.",
                    "No identity recognition, face matching or age estimation is part of this assessment.",
                ],
                required=True,
                applies_to=[AssessmentSelection.FACIAL_GEOMETRY],
            )
        )

    if AssessmentSelection.BODY_TONE_ALIGNMENT in selected:
        steps.append(
            CaptureStep(
                step_id="body_region_stills",
                title="Choose and capture body regions",
                instructions=[
                    "Only capture the regions you selected; full-body exposure is not required.",
                    "Keep each region naturally positioned and comfortably covered outside the selected area.",
                    "Use the same lighting, camera and session for regional comparisons.",
                    "Regional pigmentation differences are preserved, not treated as defects.",
                ],
                required=True,
                applies_to=[AssessmentSelection.BODY_TONE_ALIGNMENT],
            )
        )

    if request.video_guidance_requested:
        steps.append(
            CaptureStep(
                step_id="optional_video_guidance",
                title="Optional video guidance",
                instructions=[
                    "Video is optional; still photographs remain the primary capture path.",
                    "If you choose to record a clip, keep it short, steady and silent, and avoid including other people.",
                    "For facial geometry, slowly turn from front to left three-quarter and then right three-quarter without changing expression.",
                    "For tone comparisons, keep the same lighting and avoid moving between differently lit areas.",
                    "Do not upload the clip to this endpoint; video ingestion and frame extraction are not enabled.",
                ],
                required=False,
                applies_to=list(request.assessments),
            )
        )

    notes = [
        "This is capture guidance only. The endpoint does not accept, inspect, store or transmit photographs or video.",
        "Each analysis purpose requires its own verified, current consent before any future media processing.",
        "A colour-reference card is required for calibrated CIELAB claims; relative same-session comparison is not an absolute skin-tone measurement.",
        "Video is optional guidance only. Video ingestion and frame extraction are not enabled in this release.",
        "You may change the selected assessments, skip optional views or leave DSI entirely without losing access to self-discovery.",
        "Consent for analysis does not grant global model-training permission.",
    ]
    return CapturePlan(
        selected_assessments=list(request.assessments),
        tone_capture_mode=request.tone_capture_mode,
        selected_body_regions=list(request.body_regions),
        steps=steps,
        video_guidance_requested=request.video_guidance_requested,
        notes=notes,
    )
