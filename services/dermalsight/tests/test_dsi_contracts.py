from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.dsi.contracts import (
    AppearanceCorrectionPlan,
    BodyRegion,
    BodyToneAlignment,
    CIELABEstimate,
    CaptureEvidence,
    CaptureKind,
    CaptureQuality,
    ConsentPurpose,
    CorrectionOperation,
    DermalSightProfile,
    FaceShape,
    FacialGeometry,
    GlobalLearningAggregate,
    HairlineShape,
    IntervalEstimate,
    LightingProfile,
    ModelEvidence,
    ModelTask,
    PurposeConsent,
    ToneMeasurementStatus,
    ToneObservation,
)
from app.dsi.governance import ConsentNotAuthorized, require_purpose_consent
from app.dsi.readiness import dsi_capabilities


def model_evidence(task: ModelTask) -> ModelEvidence:
    return ModelEvidence(
        task=task,
        model_name="validated-test-model",
        model_version="1.0.0",
        artifact_sha256="a" * 64,
        validation_report_sha256="b" * 64,
        validation_report_ref="validation-report:sample-001",
        evaluation_dataset_version="heldout-v1",
        evaluated_population_slices=[
            "skin_tone", "lighting", "device", "body_region",
            "pose", "occlusion", "camera", "geometry_preservation",
        ],
        validation_decision="approved",
    )


def capture(*, quality: CaptureQuality = CaptureQuality.ACCEPTED) -> CaptureEvidence:
    return CaptureEvidence(
        capture_ref="cap_abcdefghijkl",
        capture_session_ref="ses_abcdefghijkl",
        kind=CaptureKind.STILL,
        quality=quality,
        lighting=LightingProfile.CONTROLLED if quality == CaptureQuality.ACCEPTED else LightingProfile.UNCONTROLLED,
        white_balance_locked=quality == CaptureQuality.ACCEPTED,
        exposure_locked=quality == CaptureQuality.ACCEPTED,
        color_reference_id="color-chart-v1" if quality == CaptureQuality.ACCEPTED else None,
        quality_report_ref="quality-report:sample-001",
        quality_assessor_version="quality-1.0",
    )


def consent(
    *,
    purpose: ConsentPurpose = ConsentPurpose.APPEARANCE_CORRECTION,
    verified: bool = True,
    active: bool = True,
    revoked: bool = False,
) -> PurposeConsent:
    now = datetime.now(timezone.utc)
    return PurposeConsent(
        receipt_ref="consent_abcdefghijkl",
        subject_binding_ref="hmac-sha256:" + "c" * 64,
        purpose=purpose,
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=30),
        active=active,
        revoked=revoked,
        verified_by_privacy_service=verified,
        verification_ref="privacy-verification:sample-001",
    )


def tone_observation(region: BodyRegion) -> ToneObservation:
    return ToneObservation(
        region=region,
        capture=capture(),
        status=ToneMeasurementStatus.CALIBRATED,
        cielab=CIELABEstimate(
            l_star=52.0,
            a_star=12.0,
            b_star=18.0,
            delta_e_uncertainty=2.0,
            color_reference_id="color-chart-v1",
            calibration_report_ref="calibration-report:sample-001",
        ),
    )


def test_absolute_tone_requires_controlled_capture_and_color_reference():
    with pytest.raises(ValidationError, match="accepted capture requires controlled lighting"):
        CaptureEvidence(
            capture_ref="cap_abcdefghijkl",
            capture_session_ref="ses_abcdefghijkl",
            kind=CaptureKind.STILL,
            quality=CaptureQuality.ACCEPTED,
            lighting=LightingProfile.UNCONTROLLED,
            white_balance_locked=True,
            exposure_locked=True,
            color_reference_id="color-chart-v1",
            quality_report_ref="quality-report:sample-001",
            quality_assessor_version="quality-1.0",
        )


def test_calibrated_tone_reference_must_match_capture_reference():
    with pytest.raises(ValidationError, match="must match the capture reference"):
        ToneObservation(
            region=BodyRegion.FACE,
            capture=capture(),
            status=ToneMeasurementStatus.CALIBRATED,
            cielab=CIELABEstimate(
                l_star=52.0,
                a_star=12.0,
                b_star=18.0,
                delta_e_uncertainty=2.0,
                color_reference_id="different-chart",
                calibration_report_ref="calibration-report:sample-001",
            ),
        )


def test_review_required_capture_cannot_emit_tone_values():
    with pytest.raises(ValidationError, match="cannot produce a tone measurement"):
        ToneObservation(
            region=BodyRegion.FACE,
            capture=capture(quality=CaptureQuality.REVIEW_REQUIRED),
            status=ToneMeasurementStatus.CALIBRATED,
            cielab=CIELABEstimate(
                l_star=52.0,
                a_star=12.0,
                b_star=18.0,
                delta_e_uncertainty=2.0,
                color_reference_id="color-chart-v1",
                calibration_report_ref="calibration-report:sample-001",
            ),
        )


def test_body_tone_requires_unique_regions_and_both_models():
    observation = tone_observation(BodyRegion.FACE)
    with pytest.raises(ValidationError, match="unique body regions"):
        BodyToneAlignment(
            observations=[observation, observation],
            model_evidence=[
                model_evidence(ModelTask.SKIN_TONE_ESTIMATION),
                model_evidence(ModelTask.BODY_REGION_SEGMENTATION),
            ],
        )
    with pytest.raises(ValidationError, match="requires tone-estimation and region-segmentation"):
        BodyToneAlignment(
            observations=[observation, tone_observation(BodyRegion.NECK)],
            model_evidence=[
                model_evidence(ModelTask.SKIN_TONE_ESTIMATION),
                model_evidence(ModelTask.FACIAL_GEOMETRY),
            ],
        )


def test_facial_geometry_requires_task_specific_evidence():
    with pytest.raises(ValidationError, match="requires facial_geometry model evidence"):
        FacialGeometry(
            face_shape=FaceShape.OVAL,
            hairline_shape=HairlineShape.ROUNDED,
            face_width_to_height=IntervalEstimate(point=0.8, lower=0.7, upper=0.9),
            jaw_to_cheek_width=IntervalEstimate(point=0.85, lower=0.8, upper=0.9),
            forehead_to_cheek_width=IntervalEstimate(point=0.9, lower=0.8, upper=1.0),
            landmark_coverage=0.95,
            model_evidence=model_evidence(ModelTask.SKIN_TONE_ESTIMATION),
        )


def test_uncertainty_interval_must_contain_point_estimate():
    with pytest.raises(ValidationError, match="point must lie within"):
        IntervalEstimate(point=1.2, lower=0.1, upper=1.0)


def test_profile_rejects_empty_measurements_and_extra_identity_payload():
    with pytest.raises(ValidationError, match="at least one validated assessment"):
        DermalSightProfile(profile_id=uuid4(), created_at=datetime.now(timezone.utc))
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DermalSightProfile(
            profile_id=uuid4(),
            created_at=datetime.now(timezone.utc),
            facial_embedding=[0.1, 0.2, 0.3],
        )


def test_global_learning_record_is_aggregate_only_and_has_cohort_floor():
    data = {
        "task": ModelTask.SKIN_TONE_ESTIMATION,
        "dataset_version": "dataset-v1",
        "consented_dataset_receipt_ref": "dataset-consent:sample-001",
        "purpose_consent_registry_ref": "training-consent-registry:sample-001",
        "training_consent_scope": "global_model_training",
        "independent_review_ref": "independent-review:sample-001",
        "distinct_contributors": 30,
        "aggregate_metrics": {"repeatability": 0.91, "coverage": 0.88},
    }
    assert GlobalLearningAggregate(**data).source_images_included is False
    with pytest.raises(ValidationError):
        GlobalLearningAggregate(**{**data, "distinct_contributors": 29})
    with pytest.raises(ValidationError):
        GlobalLearningAggregate(**{**data, "raw_images": ["image-ref"]})


def test_consent_is_exact_purpose_bound_and_fail_closed():
    receipt = consent()
    require_purpose_consent(
        receipt, ConsentPurpose.APPEARANCE_CORRECTION, now=datetime.now(timezone.utc)
    )
    with pytest.raises(ConsentNotAuthorized, match="does not grant"):
        require_purpose_consent(receipt, ConsentPurpose.GLOBAL_MODEL_TRAINING)
    with pytest.raises(ConsentNotAuthorized, match="not been verified"):
        require_purpose_consent(
            consent(verified=False), ConsentPurpose.APPEARANCE_CORRECTION
        )
    with pytest.raises(ConsentNotAuthorized, match="inactive or revoked"):
        require_purpose_consent(
            consent(revoked=True), ConsentPurpose.APPEARANCE_CORRECTION
        )


def test_appearance_corrector_requires_specific_consent_and_approved_task():
    with pytest.raises(ValidationError, match="requires its own explicit consent purpose"):
        AppearanceCorrectionPlan(
            operation=CorrectionOperation.MAKEUP_PLACEMENT_PREVIEW,
            model_evidence=model_evidence(ModelTask.APPEARANCE_CORRECTION),
            consent=consent(purpose=ConsentPurpose.COSMETIC_SKIN_ANALYSIS),
        )
    with pytest.raises(ValidationError, match="requires appearance_correction model evidence"):
        AppearanceCorrectionPlan(
            operation=CorrectionOperation.HAIRSTYLE_PREVIEW,
            model_evidence=model_evidence(ModelTask.FACIAL_GEOMETRY),
            consent=consent(),
        )


def test_dsi_capabilities_report_all_model_work_as_blocked():
    payload = dsi_capabilities()
    assert payload["overall_state"] == "contract_only"
    assert payload["inference_enabled"] is False
    assert payload["global_training_enabled"] is False
    assert payload["appearance_correction_enabled"] is False
    assert payload["features"]["shared_intelligence_api"]["state"] == "contract_only"
    assert all(
        payload["features"][name]["state"] == "blocked"
        for name in (
            "skin_tone_intelligence",
            "facial_geometry",
            "body_tone_alignment",
            "global_learning",
            "appearance_corrector",
        )
    )
    assert payload["privacy_invariants"]["face_recognition"] is False


def test_dsi_api_is_capability_only_and_has_no_profile_or_inference_route():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/dsi/capabilities")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["overall_state"] == "contract_only"
    assert client.post("/api/v1/dsi/analyze").status_code == 404
    assert client.get("/api/v1/dsi/profiles/sample").status_code == 404

def test_valid_profile_combines_body_tone_and_facial_geometry():
    alignment = BodyToneAlignment(
        observations=[
            tone_observation(BodyRegion.FACE),
            tone_observation(BodyRegion.NECK),
        ],
        model_evidence=[
            model_evidence(ModelTask.SKIN_TONE_ESTIMATION),
            model_evidence(ModelTask.BODY_REGION_SEGMENTATION),
        ],
    )
    geometry = FacialGeometry(
        face_shape=FaceShape.OVAL,
        hairline_shape=HairlineShape.ROUNDED,
        face_width_to_height=IntervalEstimate(point=0.82, lower=0.78, upper=0.86),
        jaw_to_cheek_width=IntervalEstimate(point=0.84, lower=0.80, upper=0.88),
        forehead_to_cheek_width=IntervalEstimate(point=0.91, lower=0.87, upper=0.95),
        landmark_coverage=0.96,
        model_evidence=model_evidence(ModelTask.FACIAL_GEOMETRY),
    )
    profile = DermalSightProfile(
        profile_id=uuid4(),
        created_at=datetime.now(timezone.utc),
        body_tone=alignment,
        facial_geometry=geometry,
    )
    assert profile.media_retained is False
    assert profile.identity_recognition_performed is False
    assert len(profile.body_tone.observations) == 2
