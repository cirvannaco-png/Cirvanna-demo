from packages.cirvanna_visual_intelligence.contracts import Capability, DatasetManifest, EvaluationEvidence, InferenceResourceProfile, ModelReleaseManifest, decide_qualification
H = "a" * 64
G = "b" * 40

def dataset():
    return DatasetManifest("cirvanna-consented-fashion-v1", H, "documented subject consent and catalogue license", "evidence:dataset-rights-v1", ("training", "evaluation"), True, "evidence:consent-v1", H, "subject_id and source_session_id", "policy:dataset-retention-v1")

def resource_profile():
    return InferenceResourceProfile(1, 4, 30.0, 15 * 1024 * 1024, 20_000_000, 4096, 16.0, 512)

def release():
    return ModelReleaseManifest(Capability.LOOK_IT_DECOMPOSITION, "cirvanna-lookit-decomposer-v0", "https://github.com/cirvannaco-png/Cirvanna-demo", G, H, f"sha256:{H}", True, "Apache-2.0", "evidence:license-review-v1", (dataset(),), H, "review:independent-v1", "review:privacy-v1", "lookit-image-v1", "lookit-components-v1", resource_profile())

def evaluation():
    return EvaluationEvidence(H, H, "review:independent-v1", 120, ("skin-tone-range", "body-occlusion", "garment-category"), ("skin-tone-range", "body-occlusion", "garment-category"), True, "report:deletion-drill-v1", "report:resource-profile-v1")

def test_complete_bound_evidence_still_requires_trusted_attestation():
    result = decide_qualification(release(), evaluation(), expected_capability=Capability.LOOK_IT_DECOMPOSITION)
    assert not result.qualified
    assert result.evidence_complete
    assert result.status == "evidence_complete_pending_trusted_attestation"
    assert result.blockers == ()

def test_unlicensed_or_unpinned_release_fails_closed():
    candidate = release()
    candidate = ModelReleaseManifest(**{**candidate.__dict__, "commercial_use": False, "source_revision": "main"})
    result = decide_qualification(candidate, evaluation(), expected_capability=Capability.LOOK_IT_DECOMPOSITION)
    assert not result.qualified and not result.evidence_complete
    assert "commercial_use_not_cleared" in result.blockers
    assert "source_revision_not_pinned" in result.blockers

def test_missing_dataset_rights_and_subgroup_evidence_block():
    candidate = release()
    bad_dataset = DatasetManifest(**{**dataset().__dict__, "rights_evidence_ref": ""})
    candidate = ModelReleaseManifest(**{**candidate.__dict__, "training_datasets": (bad_dataset,)})
    evidence = EvaluationEvidence(**{**evaluation().__dict__, "subgroup_slices": ("garment-category",)})
    result = decide_qualification(candidate, evidence, expected_capability=Capability.LOOK_IT_DECOMPOSITION)
    assert not result.qualified and not result.evidence_complete
    assert any("dataset_rights_evidence_missing" in item for item in result.blockers)
    assert any(item.startswith("evaluation_subgroups_missing:") for item in result.blockers)

def test_capability_and_evaluation_binding_are_exact():
    evidence = EvaluationEvidence(**{**evaluation().__dict__, "report_sha256": "c" * 64})
    result = decide_qualification(release(), evidence, expected_capability=Capability.CLICK_IT_RETRIEVAL)
    assert not result.qualified and not result.evidence_complete
    assert "capability_scope_mismatch" in result.blockers
    assert "evaluation_report_binding_mismatch" in result.blockers


def test_unsafe_resource_profile_blocks_release():
    candidate = release()
    profile = InferenceResourceProfile(0, 5000, 0.01, 512, 100, 128, 300, 1)
    candidate = ModelReleaseManifest(**{**candidate.__dict__, "resource_profile": profile})
    result = decide_qualification(candidate, evaluation(), expected_capability=Capability.LOOK_IT_DECOMPOSITION)
    assert not result.qualified and not result.evidence_complete
    assert "resource_max_concurrency_out_of_range" in result.blockers
    assert "resource_gpu_vram_out_of_range" in result.blockers
