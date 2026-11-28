from __future__ import annotations
import re
from dataclasses import dataclass
from enum import Enum

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$")

class Capability(str, Enum):
    TWIN_GEOMETRY = "twin_geometry"
    TWIN_APPEARANCE = "twin_appearance"
    VIRTUAL_TRY_ON = "virtual_try_on"
    CLICK_IT_RETRIEVAL = "click_it_retrieval"
    LOOK_IT_DECOMPOSITION = "look_it_decomposition"

@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    content_sha256: str
    rights_basis: str
    rights_evidence_ref: str
    permitted_purposes: tuple[str, ...]
    subject_consent_required: bool
    subject_consent_evidence_ref: str | None
    split_manifest_sha256: str
    leakage_grouping: str
    retention_policy_ref: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not _SAFE_REF.fullmatch(self.dataset_id): errors.append("dataset_id_invalid")
        if not _SHA256.fullmatch(self.content_sha256): errors.append("dataset_digest_invalid")
        if not self.rights_basis.strip(): errors.append("dataset_rights_basis_missing")
        if not _SAFE_REF.fullmatch(self.rights_evidence_ref): errors.append("dataset_rights_evidence_missing")
        if not self.permitted_purposes: errors.append("dataset_purposes_missing")
        if self.subject_consent_required and not _SAFE_REF.fullmatch(self.subject_consent_evidence_ref or ""): errors.append("subject_consent_evidence_missing")
        if not _SHA256.fullmatch(self.split_manifest_sha256): errors.append("dataset_split_manifest_invalid")
        if not self.leakage_grouping.strip(): errors.append("dataset_leakage_grouping_missing")
        if not _SAFE_REF.fullmatch(self.retention_policy_ref): errors.append("dataset_retention_policy_missing")
        return errors

@dataclass(frozen=True)
class InferenceResourceProfile:
    max_concurrency: int
    max_queue_depth: int
    timeout_seconds: float
    max_input_bytes: int
    max_image_pixels: int
    max_cpu_memory_mib: int
    max_gpu_vram_gib: float
    ephemeral_storage_mib: int

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not 1 <= self.max_concurrency <= 64: errors.append("resource_max_concurrency_out_of_range")
        if not 0 <= self.max_queue_depth <= 4096: errors.append("resource_queue_depth_out_of_range")
        if not 0.1 <= self.timeout_seconds <= 600: errors.append("resource_timeout_out_of_range")
        if not 1024 <= self.max_input_bytes <= 100 * 1024 * 1024: errors.append("resource_input_bytes_out_of_range")
        if not 4096 <= self.max_image_pixels <= 100_000_000: errors.append("resource_image_pixels_out_of_range")
        if not 256 <= self.max_cpu_memory_mib <= 262144: errors.append("resource_cpu_memory_out_of_range")
        if not 0 <= self.max_gpu_vram_gib <= 256: errors.append("resource_gpu_vram_out_of_range")
        if not 64 <= self.ephemeral_storage_mib <= 1048576: errors.append("resource_ephemeral_storage_out_of_range")
        return errors


@dataclass(frozen=True)
class ModelReleaseManifest:
    capability: Capability
    model_id: str
    source_repository: str
    source_revision: str
    weights_sha256: str
    runtime_image_digest: str
    commercial_use: bool
    license_identifier: str
    license_evidence_ref: str
    training_datasets: tuple[DatasetManifest, ...]
    evaluation_report_sha256: str
    independent_review_ref: str
    privacy_review_ref: str
    input_contract_version: str
    output_contract_version: str
    resource_profile: InferenceResourceProfile

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not _SAFE_REF.fullmatch(self.model_id): errors.append("model_id_invalid")
        if not self.source_repository.startswith(("https://", "git+https://")): errors.append("source_repository_invalid")
        if not _GIT_SHA.fullmatch(self.source_revision): errors.append("source_revision_not_pinned")
        if not _SHA256.fullmatch(self.weights_sha256): errors.append("weights_digest_invalid")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.runtime_image_digest): errors.append("runtime_image_not_digest_pinned")
        if not self.commercial_use: errors.append("commercial_use_not_cleared")
        if not self.license_identifier.strip(): errors.append("license_identifier_missing")
        if not _SAFE_REF.fullmatch(self.license_evidence_ref): errors.append("license_evidence_missing")
        if not self.training_datasets: errors.append("training_dataset_provenance_missing")
        for dataset in self.training_datasets:
            errors.extend(f"{dataset.dataset_id}:{error}" for error in dataset.validate())
        if not _SHA256.fullmatch(self.evaluation_report_sha256): errors.append("evaluation_report_missing_or_unpinned")
        if not _SAFE_REF.fullmatch(self.independent_review_ref): errors.append("independent_review_missing")
        if not _SAFE_REF.fullmatch(self.privacy_review_ref): errors.append("privacy_review_missing")
        if not self.input_contract_version.strip() or not self.output_contract_version.strip(): errors.append("model_io_contract_version_missing")
        errors.extend(self.resource_profile.validate())
        return errors

@dataclass(frozen=True)
class EvaluationEvidence:
    report_sha256: str
    preregistration_sha256: str
    independent_reviewer_ref: str
    sample_count: int
    subgroup_slices: tuple[str, ...]
    required_subgroup_slices: tuple[str, ...]
    failure_modes_reported: bool
    deletion_drill_report_ref: str | None
    resource_profile_report_ref: str | None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not _SHA256.fullmatch(self.report_sha256): errors.append("evaluation_report_digest_invalid")
        if not _SHA256.fullmatch(self.preregistration_sha256): errors.append("evaluation_preregistration_missing")
        if not _SAFE_REF.fullmatch(self.independent_reviewer_ref): errors.append("independent_reviewer_missing")
        if self.sample_count <= 0: errors.append("evaluation_sample_count_missing")
        missing = sorted(set(self.required_subgroup_slices) - set(self.subgroup_slices))
        if missing: errors.append("evaluation_subgroups_missing:" + ",".join(missing))
        if not self.failure_modes_reported: errors.append("failure_modes_not_reported")
        if not _SAFE_REF.fullmatch(self.deletion_drill_report_ref or ""): errors.append("deletion_drill_evidence_missing")
        if not _SAFE_REF.fullmatch(self.resource_profile_report_ref or ""): errors.append("resource_profile_evidence_missing")
        return errors

@dataclass(frozen=True)
class QualificationDecision:
    qualified: bool
    status: str
    blockers: tuple[str, ...]
    evidence_complete: bool

def decide_qualification(release: ModelReleaseManifest, evaluation: EvaluationEvidence, *, expected_capability: Capability) -> QualificationDecision:
    """Fail-closed gate; a model cannot self-assert commercial or quality approval."""
    blockers = release.validate() + evaluation.validate()
    if release.capability != expected_capability: blockers.append("capability_scope_mismatch")
    if release.evaluation_report_sha256 != evaluation.report_sha256: blockers.append("evaluation_report_binding_mismatch")
    if release.independent_review_ref != evaluation.independent_reviewer_ref: blockers.append("independent_review_binding_mismatch")
    unique = tuple(dict.fromkeys(blockers))
    # This package validates evidence shape and binding only. It has no trusted
    # signature verifier or independent approver identity, so it must never
    # promote a model to qualified on metadata references alone.
    return QualificationDecision(
        qualified=False,
        status="evidence_complete_pending_trusted_attestation" if not unique else "review_required",
        blockers=unique,
        evidence_complete=not unique,
    )
