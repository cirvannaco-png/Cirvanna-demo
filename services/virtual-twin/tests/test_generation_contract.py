from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.generation_contract import (
    GenerationContractError,
    MeshValidationReceipt,
    TwinGenerationCommand,
    TwinGenerationResult,
    assert_generation_transition,
    validate_generation_bundle,
)

SOURCE_IDS = ["source-image-001", "source-image-002"]
MODEL_VERSION = "cirvanna-body-model@sha256:" + ("a" * 64)
ARTIFACT_SHA256 = "b" * 64


def bundle(*, source_ids=None, receipt_overrides=None, result_overrides=None):
    sources = SOURCE_IDS if source_ids is None else source_ids
    command = TwinGenerationCommand(
        subject_id="subject-001",
        twin_id="twin-001",
        consent_id="consent-receipt-001",
        consent_version="privacy-v1",
        idempotency_key="generate-twin-001",
        source_image_asset_ids=sources,
    )
    result_data = {
        "subject_id": "subject-001",
        "twin_id": "twin-001",
        "provider_id": "body-provider",
        "provider_job_id": "provider-job-001",
        "representation_type": "full_body_mesh",
        "artifact_asset_id": "private-mesh-001",
        "source_image_asset_ids": sources,
        "model_version": MODEL_VERSION,
        "artifact_sha256": ARTIFACT_SHA256,
    }
    result_data.update(result_overrides or {})
    result = TwinGenerationResult(**result_data)
    receipt_data = {
        "validator_id": "independent-mesh-validator",
        "receipt_id": "validation-receipt-001",
        "validated": True,
        "consent_id": "consent-receipt-001",
        "consent_version": "privacy-v1",
        "subject_id": "subject-001",
        "twin_id": "twin-001",
        "representation_type": "full_body_mesh",
        "artifact_asset_id": "private-mesh-001",
        "artifact_sha256": ARTIFACT_SHA256,
        "source_image_asset_ids": sources,
        "model_version": MODEL_VERSION,
        "checks": {
            "artifact_readable": True,
            "geometry_finite": True,
            "topology_valid": True,
            "body_coverage_valid": True,
            "scale_within_bounds": True,
            "privacy_scan_passed": True,
            "source_photo_not_embedded": True,
        },
    }
    receipt_data.update(receipt_overrides or {})
    receipt = MeshValidationReceipt(**receipt_data)
    return command, result, receipt


def test_exact_generation_and_independent_validation_bundle_is_accepted():
    command, result, receipt = bundle()
    assert validate_generation_bundle(command, result, receipt) is None


def test_result_cannot_change_subject_or_twin():
    command, result, receipt = bundle(
        result_overrides={"subject_id": "subject-999"}
    )
    with pytest.raises(GenerationContractError, match="TWIN_GENERATION_SCOPE_MISMATCH"):
        validate_generation_bundle(command, result, receipt)


def test_generation_must_use_exact_authorized_source_asset_set():
    command, result, receipt = bundle(
        result_overrides={"source_image_asset_ids": ["source-image-001", "source-image-999"]}
    )
    with pytest.raises(GenerationContractError, match="TWIN_GENERATION_SOURCE_SET_MISMATCH"):
        validate_generation_bundle(command, result, receipt)


def test_derived_artifact_must_not_alias_a_source_image():
    command, result, receipt = bundle(
        result_overrides={"artifact_asset_id": "source-image-001"}
    )
    with pytest.raises(GenerationContractError, match="TWIN_GENERATION_ARTIFACT_IS_SOURCE"):
        validate_generation_bundle(command, result, receipt)


def test_validator_must_attest_to_exact_artifact_digest():
    command, result, receipt = bundle(
        receipt_overrides={"artifact_sha256": "c" * 64}
    )
    with pytest.raises(GenerationContractError, match="TWIN_VALIDATION_DIGEST_MISMATCH"):
        validate_generation_bundle(command, result, receipt)


def test_validator_must_attest_to_exact_model_revision():
    other_model = "cirvanna-body-model@sha256:" + ("d" * 64)
    command, result, receipt = bundle(
        receipt_overrides={"model_version": other_model}
    )
    with pytest.raises(GenerationContractError, match="TWIN_VALIDATION_MODEL_MISMATCH"):
        validate_generation_bundle(command, result, receipt)


def test_failed_validator_receipt_never_passes():
    command, result, receipt = bundle(receipt_overrides={"validated": False})
    with pytest.raises(GenerationContractError, match="TWIN_MESH_NOT_VALIDATED"):
        validate_generation_bundle(command, result, receipt)


def test_any_failed_independent_mesh_quality_check_blocks_registration():
    command, result, receipt = bundle(
        receipt_overrides={
            "checks": {
                "artifact_readable": True,
                "geometry_finite": True,
                "topology_valid": True,
                "body_coverage_valid": False,
                "scale_within_bounds": True,
                "privacy_scan_passed": True,
                "source_photo_not_embedded": True,
            }
        }
    )
    with pytest.raises(GenerationContractError, match="TWIN_MESH_QUALITY_CHECK_FAILED"):
        validate_generation_bundle(command, result, receipt)


@pytest.mark.parametrize(
    "field,value",
    [
        ("subject_id", "https://example.test/user"),
        ("twin_id", "../twin"),
        ("consent_id", "/tmp/consent"),
        ("idempotency_key", "file:///private/key"),
    ],
)
def test_command_rejects_urls_and_paths(field, value):
    payload = {
        "subject_id": "subject-001",
        "twin_id": "twin-001",
        "consent_id": "consent-receipt-001",
        "consent_version": "privacy-v1",
        "idempotency_key": "generate-twin-001",
        "source_image_asset_ids": SOURCE_IDS,
    }
    payload[field] = value
    with pytest.raises(ValidationError):
        TwinGenerationCommand(**payload)


def test_provider_result_requires_digest_pinned_model_version():
    with pytest.raises(ValidationError):
        bundle(result_overrides={"model_version": "latest"})


def test_generation_lifecycle_accepts_only_the_ordered_happy_path():
    transitions = [
        ("queued", "generating"),
        ("generating", "validating"),
        ("validating", "persisting"),
        ("persisting", "active"),
    ]
    for current, target in transitions:
        assert_generation_transition(current, target)


@pytest.mark.parametrize(
    "current,target",
    [
        ("queued", "active"),
        ("generating", "active"),
        ("validating", "active"),
        ("persisting", "generating"),
        ("failed", "queued"),
        ("revoked", "active"),
        ("active", "persisting"),
    ],
)
def test_generation_lifecycle_rejects_skipped_or_terminal_transitions(current, target):
    with pytest.raises(
        GenerationContractError,
        match="TWIN_GENERATION_INVALID_STATE_TRANSITION",
    ):
        assert_generation_transition(current, target)


def test_every_nonterminal_stage_can_be_revoked():
    for stage in ("queued", "generating", "validating", "persisting", "active"):
        assert_generation_transition(stage, "revoked")


def test_mesh_validator_must_be_a_separate_integration_from_generator():
    command, result, receipt = bundle(
        receipt_overrides={"validator_id": "body-provider"}
    )
    with pytest.raises(
        GenerationContractError,
        match="TWIN_VALIDATOR_NOT_INDEPENDENT",
    ):
        validate_generation_bundle(command, result, receipt)


def test_validator_receipt_must_bind_to_the_same_consent_version():
    command, result, receipt = bundle(
        receipt_overrides={"consent_version": "privacy-v2"}
    )
    with pytest.raises(
        GenerationContractError,
        match="TWIN_VALIDATION_CONSENT_MISMATCH",
    ):
        validate_generation_bundle(command, result, receipt)


def test_validator_source_asset_set_must_match_command():
    command, result, receipt = bundle(
        receipt_overrides={"source_image_asset_ids": ["source-image-001", "source-image-999"]}
    )
    with pytest.raises(
        GenerationContractError,
        match="TWIN_VALIDATION_SOURCE_SET_MISMATCH",
    ):
        validate_generation_bundle(command, result, receipt)


def test_generation_lifecycle_rejects_unknown_states_without_key_error():
    with pytest.raises(
        GenerationContractError,
        match="TWIN_GENERATION_INVALID_STATE_TRANSITION",
    ):
        assert_generation_transition("unexpected", "active")  # type: ignore[arg-type]
