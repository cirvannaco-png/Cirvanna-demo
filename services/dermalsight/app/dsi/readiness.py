"""Truthful DSI capability reporting. No feature is enabled by configuration flags."""
from __future__ import annotations


def dsi_capabilities() -> dict[str, object]:
    """Return implemented capability state without implying model readiness."""
    return {
        "service": "cirvanna-dermalsight",
        "dsi_contract_version": "1",
        "overall_state": "contract_only",
        "features": {
            "skin_tone_intelligence": {
                "state": "blocked",
                "reason": "No DSI-specific calibrated tone model and signed evaluation report are configured.",
                "required_evidence": [
                    "controlled-capture protocol",
                    "color-reference calibration",
                    "held-out evaluation across skin-tone, device and lighting slices",
                    "measurement uncertainty and repeatability report",
                ],
            },
            "facial_geometry": {
                "state": "blocked",
                "reason": "No validated facial-landmark and geometry model is configured.",
                "required_evidence": [
                    "licensed and hash-pinned landmark model",
                    "landmark and shape agreement evaluation",
                    "pose, occlusion, hairline and camera-condition failure analysis",
                    "privacy and biometric-data review",
                ],
            },
            "body_tone_alignment": {
                "state": "blocked",
                "reason": "No validated body-region segmentation and cross-region calibration pipeline is configured.",
                "required_evidence": [
                    "body-region segmentation model",
                    "region-specific calibration evidence",
                    "same-session comparison and uncertainty validation",
                    "coverage and occlusion evaluation",
                ],
            },
            "shared_intelligence_api": {
                "state": "contract_only",
                "reason": "Typed profile contracts exist; service-to-service identity, subject scoping and authorization are not integrated.",
                "required_evidence": [
                    "authenticated service identities and purpose-bound authorization",
                    "subject-scoped read policies",
                    "revocation, export, correction and deletion propagation",
                    "consumer contract tests for each enabled Cirvanna service",
                ],
            },
            "global_learning": {
                "state": "blocked",
                "reason": "No consent-verified dataset registry, independent evaluation pipeline or approved training workflow is connected.",
                "required_evidence": [
                    "separate opt-in for global model training",
                    "rights and consent provenance for every dataset contribution",
                    "privacy-preserving aggregate reporting and minimum cohort controls",
                    "independent held-out and subgroup validation",
                    "model rollback and deletion/retraining procedures",
                ],
            },
            "appearance_corrector": {
                "state": "blocked",
                "reason": "No licensed cosmetic rendering model or identity-preservation validation report is configured.",
                "required_evidence": [
                    "licensed, immutable renderer and model artifacts",
                    "explicit appearance-correction consent",
                    "identity-preservation and geometry-drift evaluation",
                    "artifact-level provenance and private output lifecycle",
                ],
            },
        },
        "privacy_invariants": {
            "raw_media_persistence": False,
            "face_recognition": False,
            "identity_matching": False,
            "age_estimation": False,
            "medical_diagnosis": False,
            "global_training_by_default": False,
            "public_media_output": False,
        },
        "inference_enabled": False,
        "profile_read_api_enabled": False,
        "global_training_enabled": False,
        "appearance_correction_enabled": False,
        "user_autonomy": {
            "discovery_available_without_dsi": True,
            "prior_preferences_are_advisory": True,
            "user_direction_can_override_prior_preferences": True,
            "dsi_can_veto_aesthetic_choices": False,
            "automatic_preference_updates": False,
            "explicit_save_required_for_preference_updates": True,
            "optional_analysis_failure_blocks_discovery": False,
        },
    }
