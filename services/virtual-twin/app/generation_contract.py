"""Provider-neutral, fail-closed contract for persistent Twin generation.

This module validates a generation result against the original command and an
independent mesh-validation receipt. It does not call a provider, persist an
asset, register a Twin, or enable generation. Those actions require configured
consent, private-asset, database, and commercially approved provider adapters.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{2,159}$")
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,79}$")
MODEL_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_REQUIRED_MESH_CHECKS = (
    "artifact_readable",
    "geometry_finite",
    "topology_valid",
    "body_coverage_valid",
    "scale_within_bounds",
    "privacy_scan_passed",
    "source_photo_not_embedded",
)


class StrictContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _opaque_identifier(value: str) -> str:
    value = value.strip()
    if (
        not IDENTIFIER_RE.fullmatch(value)
        or "://" in value
        or "/" in value
        or "\\" in value
    ):
        raise ValueError("Expected an opaque internal identifier, not a URL or path.")
    return value


def _model_id(value: str) -> str:
    value = value.strip()
    if not MODEL_ID_RE.fullmatch(value):
        raise ValueError("Expected a canonical provider model identifier.")
    return value


def _model_revision(value: str) -> str:
    value = value.strip().lower()
    if not MODEL_REVISION_RE.fullmatch(value):
        raise ValueError("Model revision must be a pinned 40-character lowercase commit digest.")
    return value


def _sha256(value: str) -> str:
    value = value.strip().lower()
    if not SHA256_RE.fullmatch(value):
        raise ValueError("Expected a lowercase SHA-256 hex digest.")
    return value


class TwinGenerationCommand(StrictContractModel):
    """Trusted server-side intent; source IDs must already be owner-authorized."""

    subject_id: str = Field(min_length=3, max_length=128)
    twin_id: str = Field(min_length=3, max_length=128)
    consent_id: str = Field(min_length=8, max_length=160)
    consent_version: str = Field(min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=160)
    source_image_asset_ids: list[str] = Field(min_length=1, max_length=6)

    @field_validator("subject_id", "twin_id", "consent_id", "consent_version", "idempotency_key")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        return _opaque_identifier(value)

    @field_validator("source_image_asset_ids")
    @classmethod
    def validate_source_assets(cls, values: list[str]) -> list[str]:
        normalized = [_opaque_identifier(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Source image asset IDs must be unique.")
        return normalized


class TwinGenerationResult(StrictContractModel):
    """Provider result; it may reference only an already-private stored artifact."""

    subject_id: str = Field(min_length=3, max_length=128)
    twin_id: str = Field(min_length=3, max_length=128)
    provider_id: str = Field(min_length=3, max_length=80)
    provider_job_id: str = Field(min_length=3, max_length=160)
    representation_type: Literal["full_body_mesh"]
    artifact_content_type: Literal["model/gltf-binary"]
    artifact_asset_id: str = Field(min_length=3, max_length=160)
    source_image_asset_ids: list[str] = Field(min_length=1, max_length=6)
    model_id: str = Field(min_length=3, max_length=80)
    model_revision: str = Field(min_length=40, max_length=40)
    model_release_sha256: str = Field(min_length=64, max_length=64)
    artifact_sha256: str = Field(min_length=64, max_length=64)

    @field_validator("subject_id", "twin_id", "provider_id", "provider_job_id", "artifact_asset_id")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        return _opaque_identifier(value)

    @field_validator("source_image_asset_ids")
    @classmethod
    def validate_source_assets(cls, values: list[str]) -> list[str]:
        normalized = [_opaque_identifier(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Source image asset IDs must be unique.")
        return normalized

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        return _model_id(value)

    @field_validator("model_revision")
    @classmethod
    def validate_model_revision(cls, value: str) -> str:
        return _model_revision(value)

    @field_validator("model_release_sha256", "artifact_sha256")
    @classmethod
    def validate_sha256_digest(cls, value: str) -> str:
        return _sha256(value)


class MeshValidationChecks(StrictContractModel):
    """Minimum independent checks; every check must pass for registration."""

    artifact_readable: StrictBool
    geometry_finite: StrictBool
    topology_valid: StrictBool
    body_coverage_valid: StrictBool
    scale_within_bounds: StrictBool
    privacy_scan_passed: StrictBool
    source_photo_not_embedded: StrictBool


class MeshValidationReceipt(StrictContractModel):
    """Validator attestation bound to the exact generated bytes and source set."""

    validator_id: str = Field(min_length=3, max_length=80)
    receipt_id: str = Field(min_length=8, max_length=160)
    validated: StrictBool
    consent_id: str = Field(min_length=8, max_length=160)
    consent_version: str = Field(min_length=1, max_length=80)
    subject_id: str = Field(min_length=3, max_length=128)
    twin_id: str = Field(min_length=3, max_length=128)
    representation_type: Literal["full_body_mesh"]
    artifact_content_type: Literal["model/gltf-binary"]
    artifact_asset_id: str = Field(min_length=3, max_length=160)
    artifact_sha256: str = Field(min_length=64, max_length=64)
    source_image_asset_ids: list[str] = Field(min_length=1, max_length=6)
    model_id: str = Field(min_length=3, max_length=80)
    model_revision: str = Field(min_length=40, max_length=40)
    model_release_sha256: str = Field(min_length=64, max_length=64)
    checks: MeshValidationChecks

    @field_validator("validator_id", "receipt_id", "consent_id", "consent_version", "subject_id", "twin_id", "artifact_asset_id")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        return _opaque_identifier(value)

    @field_validator("artifact_sha256")
    @classmethod
    def validate_artifact_digest(cls, value: str) -> str:
        return _sha256(value)

    @field_validator("source_image_asset_ids")
    @classmethod
    def validate_source_assets(cls, values: list[str]) -> list[str]:
        normalized = [_opaque_identifier(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Source image asset IDs must be unique.")
        return normalized

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        return _model_id(value)

    @field_validator("model_revision")
    @classmethod
    def validate_model_revision(cls, value: str) -> str:
        return _model_revision(value)

    @field_validator("model_release_sha256")
    @classmethod
    def validate_model_release_digest(cls, value: str) -> str:
        return _sha256(value)


class GenerationContractError(ValueError):
    """Stable, safe error code for a rejected generation bundle."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def validate_generation_bundle(
    command: TwinGenerationCommand,
    result: TwinGenerationResult,
    receipt: MeshValidationReceipt,
) -> None:
    """Verify exact command/result/attestation binding before registry access.

    The independent validator must attest to the exact artifact digest, model
    revision, owner, Twin, and source set. A successful provider response alone
    is never sufficient to make a Twin persistent or visible.
    """
    if result.subject_id != command.subject_id or result.twin_id != command.twin_id:
        raise GenerationContractError("TWIN_GENERATION_SCOPE_MISMATCH")
    if set(result.source_image_asset_ids) != set(command.source_image_asset_ids):
        raise GenerationContractError("TWIN_GENERATION_SOURCE_SET_MISMATCH")
    if result.artifact_asset_id in command.source_image_asset_ids:
        raise GenerationContractError("TWIN_GENERATION_ARTIFACT_IS_SOURCE")

    if receipt.validator_id == result.provider_id:
        raise GenerationContractError("TWIN_VALIDATOR_NOT_INDEPENDENT")
    if receipt.validated is not True:
        raise GenerationContractError("TWIN_MESH_NOT_VALIDATED")
    if receipt.subject_id != command.subject_id or receipt.twin_id != command.twin_id:
        raise GenerationContractError("TWIN_VALIDATION_SCOPE_MISMATCH")
    if receipt.consent_id != command.consent_id or receipt.consent_version != command.consent_version:
        raise GenerationContractError("TWIN_VALIDATION_CONSENT_MISMATCH")
    if receipt.representation_type != result.representation_type:
        raise GenerationContractError("TWIN_VALIDATION_REPRESENTATION_MISMATCH")
    if receipt.artifact_content_type != result.artifact_content_type:
        raise GenerationContractError("TWIN_VALIDATION_CONTENT_TYPE_MISMATCH")
    if receipt.artifact_asset_id != result.artifact_asset_id:
        raise GenerationContractError("TWIN_VALIDATION_ASSET_MISMATCH")
    if receipt.artifact_sha256 != result.artifact_sha256:
        raise GenerationContractError("TWIN_VALIDATION_DIGEST_MISMATCH")
    if (
        receipt.model_id != result.model_id
        or receipt.model_revision != result.model_revision
        or receipt.model_release_sha256 != result.model_release_sha256
    ):
        raise GenerationContractError("TWIN_VALIDATION_MODEL_MISMATCH")
    if set(receipt.source_image_asset_ids) != set(command.source_image_asset_ids):
        raise GenerationContractError("TWIN_VALIDATION_SOURCE_SET_MISMATCH")
    failed_checks = [
        name for name in _REQUIRED_MESH_CHECKS
        if getattr(receipt.checks, name) is not True
    ]
    if failed_checks:
        raise GenerationContractError("TWIN_MESH_QUALITY_CHECK_FAILED")


GenerationStatus = Literal[
    "queued", "generating", "validating", "persisting", "active", "failed", "revoked"
]

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"generating", "failed", "revoked"}),
    "generating": frozenset({"validating", "failed", "revoked"}),
    "validating": frozenset({"persisting", "failed", "revoked"}),
    "persisting": frozenset({"active", "failed", "revoked"}),
    "active": frozenset({"revoked"}),
    "failed": frozenset(),
    "revoked": frozenset(),
}


def assert_generation_transition(current: GenerationStatus, target: GenerationStatus) -> None:
    """Reject skipped, reversed, or post-terminal lifecycle transitions."""
    allowed = _ALLOWED_TRANSITIONS.get(current)
    if allowed is None or target not in allowed:
        raise GenerationContractError("TWIN_GENERATION_INVALID_STATE_TRANSITION")


def registry_registration_payload(
    command: TwinGenerationCommand,
    result: TwinGenerationResult,
    receipt: MeshValidationReceipt,
    *,
    validation_attestation_hmac: str,
) -> dict[str, object]:
    """Build the exact Registry request using a signature issued by the independent validator.

    This orchestration contract deliberately has no signing secret and cannot
    mint a Registry attestation. Twin Registry verifies the validator-issued
    HMAC independently, then rechecks resource-bound consent and private asset
    ownership before persisting the Twin.
    """
    validate_generation_bundle(command, result, receipt)
    signature = validation_attestation_hmac.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", signature):
        raise GenerationContractError("TWIN_VALIDATION_ATTESTATION_INVALID_FORMAT")

    # Asset Service identifiers are UUIDs; the registry deliberately accepts
    # no URL, object key, or arbitrary provider path.
    import uuid

    try:
        uuid.UUID(result.artifact_asset_id)
        for asset_id in command.source_image_asset_ids:
            uuid.UUID(asset_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise GenerationContractError("TWIN_GENERATION_ASSET_ID_INVALID") from exc

    canonical_receipt = json.dumps(
        receipt.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    validation_report_sha256 = hashlib.sha256(
        canonical_receipt.encode("utf-8")
    ).hexdigest()
    body = {
        "twin_id": command.twin_id,
        "subject_id": command.subject_id,
        "mesh_asset_id": result.artifact_asset_id,
        "source_image_asset_ids": sorted(command.source_image_asset_ids),
        "consent_id": command.consent_id,
        "model_id": result.model_id,
        "model_revision": result.model_revision,
        "model_release_sha256": result.model_release_sha256,
        "validation_report_sha256": validation_report_sha256,
        "representation_type": "full_body_mesh",
    }
    return {
        **body,
        "validation_attestation_hmac": signature,
    }
