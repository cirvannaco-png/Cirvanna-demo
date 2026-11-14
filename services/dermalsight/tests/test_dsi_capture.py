from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.dsi.capture import (
    AssessmentSelection,
    CapturePlanRequest,
    ToneCaptureMode,
    build_capture_plan,
)
from app.dsi.contracts import BodyRegion


def test_face_only_capture_plan_does_not_require_body_or_video():
    plan = build_capture_plan(
        CapturePlanRequest(assessments=[AssessmentSelection.FACIAL_GEOMETRY])
    )
    assert [step.step_id for step in plan.steps] == ["facial_geometry_stills"]
    assert plan.image_processing_enabled is False
    assert plan.video_processing_enabled is False
    assert plan.raw_media_retention_enabled is False
    assert plan.discovery_must_continue_without_dsi is True


def test_user_can_select_only_some_body_regions():
    plan = build_capture_plan(
        CapturePlanRequest(
            assessments=[AssessmentSelection.BODY_TONE_ALIGNMENT],
            body_regions=[BodyRegion.FACE, BodyRegion.NECK],
        )
    )
    assert plan.selected_body_regions == [BodyRegion.FACE, BodyRegion.NECK]
    assert "full-body exposure is not required" in plan.steps[-1].instructions[0]


def test_body_alignment_requires_two_regions():
    with pytest.raises(ValidationError, match="at least two user-selected regions"):
        CapturePlanRequest(
            assessments=[AssessmentSelection.BODY_TONE_ALIGNMENT],
            body_regions=[BodyRegion.FACE],
        )


def test_calibrated_tone_requires_a_supported_colour_reference():
    with pytest.raises(ValidationError, match="physical colour-reference"):
        CapturePlanRequest(
            assessments=[AssessmentSelection.SKIN_TONE],
            tone_capture_mode=ToneCaptureMode.CALIBRATED_CIELAB,
            color_reference_available=False,
        )


def test_calibrated_tone_plan_explains_reference_capture():
    plan = build_capture_plan(
        CapturePlanRequest(
            assessments=[AssessmentSelection.SKIN_TONE],
            tone_capture_mode=ToneCaptureMode.CALIBRATED_CIELAB,
            color_reference_available=True,
        )
    )
    assert plan.steps[0].step_id == "tone_reference"
    assert plan.steps[0].required is True
    assert plan.tone_capture_mode == ToneCaptureMode.CALIBRATED_CIELAB


def test_video_is_optional_guidance_not_processing():
    plan = build_capture_plan(
        CapturePlanRequest(
            assessments=[AssessmentSelection.FACIAL_GEOMETRY],
            video_guidance_requested=True,
        )
    )
    assert plan.video_guidance_requested is True
    assert plan.video_processing_enabled is False
    video_step = next(step for step in plan.steps if step.step_id == "optional_video_guidance")
    assert video_step.required is False
    assert any("Do not upload the clip" in instruction for instruction in video_step.instructions)
    assert any("Video ingestion" in note for note in plan.notes)


def test_global_training_consent_is_never_in_capture_plan():
    plan = build_capture_plan(
        CapturePlanRequest(assessments=[AssessmentSelection.SKIN_TONE])
    )
    assert plan.global_training_consent_included is False


def test_duplicate_or_unselected_body_regions_are_rejected():
    with pytest.raises(ValidationError, match="unique"):
        CapturePlanRequest(
            assessments=[AssessmentSelection.BODY_TONE_ALIGNMENT],
            body_regions=[BodyRegion.FACE, BodyRegion.FACE],
        )
    with pytest.raises(ValidationError, match="only be selected"):
        CapturePlanRequest(
            assessments=[AssessmentSelection.FACIAL_GEOMETRY],
            body_regions=[BodyRegion.FACE, BodyRegion.NECK],
        )
