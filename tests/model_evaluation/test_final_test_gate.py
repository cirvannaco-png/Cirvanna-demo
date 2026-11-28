import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.model_evaluation.fashion_retrieval.evaluate_retrieval import (
    evaluate_preregistered_challenger_gates,
    validate_final_test_registration,
    validate_private_artifact_manifests,
    validate_run_manifest,
)
from test_preregistration import valid_registration


def make_cases(query_count=100, cluster_count=50, pool_size=100):
    cases = []
    for i in range(query_count):
        cases.append({
            "task_id": "image_to_catalog_text",
            "cluster_id": f"cluster-{i % cluster_count}",
            "candidate_ids": [f"p{j}" for j in range(pool_size)],
            "rankings": {
                "cirvanna-fashion-clip": [],
                "marqo-fashionclip": [],
            },
        })
    return cases


class FinalTestGateTests(unittest.TestCase):
    def test_accepts_evaluation_matching_locked_registration(self):
        validate_final_test_registration(
            make_cases(), valid_registration(),
            baseline_model_id="cirvanna-fashion-clip", k=10,
            primary_metric="ndcg_at_k", bootstrap_samples=2000, seed=20261121,
        )

    def test_rejects_metric_drift(self):
        with self.assertRaisesRegex(ValueError, "metric/k differs"):
            validate_final_test_registration(
                make_cases(), valid_registration(),
                baseline_model_id="cirvanna-fashion-clip", k=10,
                primary_metric="mrr_at_k", bootstrap_samples=2000, seed=20261121,
            )

    def test_rejects_underpowered_final_sample(self):
        with self.assertRaisesRegex(ValueError, "query count is below"):
            validate_final_test_registration(
                make_cases(query_count=99), valid_registration(),
                baseline_model_id="cirvanna-fashion-clip", k=10,
                primary_metric="ndcg_at_k", bootstrap_samples=2000, seed=20261121,
            )

    def test_rejects_model_set_drift(self):
        cases = make_cases()
        cases[0]["rankings"]["unregistered-model"] = []
        with self.assertRaisesRegex(ValueError, "model IDs differ"):
            validate_final_test_registration(
                cases, valid_registration(),
                baseline_model_id="cirvanna-fashion-clip", k=10,
                primary_metric="ndcg_at_k", bootstrap_samples=2000, seed=20261121,
            )

    def test_rejects_candidate_pool_drift(self):
        cases = make_cases(pool_size=75)
        with self.assertRaisesRegex(ValueError, "candidate pool sizes differ"):
            validate_final_test_registration(
                cases, valid_registration(),
                baseline_model_id="cirvanna-fashion-clip", k=10,
                primary_metric="ndcg_at_k", bootstrap_samples=2000, seed=20261121,
            )



    def test_rejects_runner_revision_drift(self):
        registration = valid_registration()
        manifest = {
            "schema_version": "1.0",
            "data_rights": {"manifest_sha256": registration["rights_manifest_sha256"]},
            "model_revisions": {
                "cirvanna-fashion-clip": registration["baseline"]["revision"],
                "marqo-fashionclip": "d" * 40,
            },
            "rankings_output_sha256": "a" * 64,
            "input_sha256": "b" * 64,
            "split": "test",
            "task_id": "image_to_catalog_text",
        }
        with tempfile.TemporaryDirectory() as tmp:
            rankings = Path(tmp) / "rankings.jsonl"
            rankings.write_text("{}\\n", encoding="utf-8")
            manifest["rankings_output_sha256"] = hashlib.sha256(rankings.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "model revisions differ"):
                validate_run_manifest(manifest, registration, rankings, {"output_sha256": "b" * 64})

    def test_accepts_matching_runner_manifest_and_artifact_digests(self):
        registration = valid_registration()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data.json"
            qrels = root / "qrels.json"
            lock = root / "requirements.lock"
            rights_evidence = root / "rights-approval.txt"
            rights_evidence.write_text("approved by designated reviewer", encoding="utf-8")
            rights = root / "data-rights.json"
            rights.write_text(json.dumps({
                "schema_version": "1.0", "approval_status": "approved",
                "scope": "fashion_retrieval_evaluation", "reviewed_by": "reviewer",
                "reviewer_role": "data-rights-owner", "reviewed_at_utc": "2026-11-21T06:00:00Z",
                "source_provenance": "documented source records",
                "evidence_path": str(rights_evidence),
                "evidence_sha256": hashlib.sha256(rights_evidence.read_bytes()).hexdigest(),
                "commercial_evaluation_permitted": True, "human_review_permitted": True,
                "retention_until": "2027-12-31", "contains_personal_images": False,
                "depicted_person_consent_status": "not_applicable"
            }), encoding="utf-8")
            qrels.write_text(json.dumps({
                "output_sha256": "e" * 64,
                "data_rights": {"manifest_sha256": hashlib.sha256(rights.read_bytes()).hexdigest()},
            }), encoding="utf-8")
            data.write_text(json.dumps({
                "output_sha256": "b" * 64, "query_count": 100, "candidate_pool_sizes": [100],
                "data_rights": {"manifest_sha256": hashlib.sha256(rights.read_bytes()).hexdigest()},
                "qrels_manifest_sha256": hashlib.sha256(qrels.read_bytes()).hexdigest(),
                "query_cases_sha256": "e" * 64,
            }), encoding="utf-8")
            lock.write_text("fully-pinned-dependencies", encoding="utf-8")
            registration.update({
                "data_manifest_path": str(data),
                "qrels_manifest_path": str(qrels),
                "dependency_lock_path": str(lock),
                "rights_manifest_path": str(rights),
                "rights_manifest_sha256": hashlib.sha256(rights.read_bytes()).hexdigest(),
                "data_manifest_sha256": hashlib.sha256(data.read_bytes()).hexdigest(),
                "qrels_manifest_sha256": hashlib.sha256(qrels.read_bytes()).hexdigest(),
                "dependency_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
            })
            artifacts = validate_private_artifact_manifests(registration)
            rankings = root / "rankings.jsonl"
            rankings.write_text("{}\\n", encoding="utf-8")
            manifest = {
                "schema_version": "1.0",
                "data_rights": {"manifest_sha256": registration["rights_manifest_sha256"]},
                "model_revisions": {
                    "cirvanna-fashion-clip": registration["baseline"]["revision"],
                    **registration["challengers"],
                },
                "rankings_output_sha256": hashlib.sha256(rankings.read_bytes()).hexdigest(),
                "input_sha256": "b" * 64,
                "query_count": 100,
                "candidate_pool_sizes": [100],
                "split": "test",
                "task_id": "image_to_catalog_text",
            }
            validate_run_manifest(manifest, registration, rankings, artifacts["data"])

    def test_rejects_data_or_qrels_manifest_bound_to_different_rights(self):
        registration = valid_registration()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "rights.txt"
            evidence.write_text("approved", encoding="utf-8")
            rights = root / "rights.json"
            rights.write_text(json.dumps({
                "schema_version": "1.0", "approval_status": "approved",
                "scope": "fashion_retrieval_evaluation", "reviewed_by": "reviewer",
                "reviewer_role": "rights-owner", "reviewed_at_utc": "2026-11-21T06:00:00Z",
                "source_provenance": "approved source register", "evidence_path": str(evidence),
                "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                "commercial_evaluation_permitted": True, "human_review_permitted": True,
                "retention_until": "2027-12-31", "contains_personal_images": False,
                "depicted_person_consent_status": "not_applicable",
            }), encoding="utf-8")
            data = root / "data.json"
            qrels = root / "qrels.json"
            lock = root / "lock.txt"
            rights_digest = hashlib.sha256(rights.read_bytes()).hexdigest()
            qrels.write_text(json.dumps({"data_rights": {"manifest_sha256": rights_digest}, "output_sha256": "1" * 64}), encoding="utf-8")
            data.write_text(json.dumps({
                "data_rights": {"manifest_sha256": "f" * 64},
                "qrels_manifest_sha256": hashlib.sha256(qrels.read_bytes()).hexdigest(),
                "query_cases_sha256": "1" * 64,
            }), encoding="utf-8")
            lock.write_text("lock", encoding="utf-8")
            registration.update({
                "rights_manifest_path": str(rights), "rights_manifest_sha256": rights_digest,
                "data_manifest_path": str(data), "data_manifest_sha256": hashlib.sha256(data.read_bytes()).hexdigest(),
                "qrels_manifest_path": str(qrels), "qrels_manifest_sha256": hashlib.sha256(qrels.read_bytes()).hexdigest(),
                "dependency_lock_path": str(lock), "dependency_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
            })
            with self.assertRaisesRegex(ValueError, "data manifest is not bound"):
                validate_private_artifact_manifests(registration)

    def test_practical_improvement_requires_threshold_and_positive_ci(self):
        registration = valid_registration()
        report = {
            "paired_vs_baseline": {
                "marqo-fashionclip": {
                    "delta_vs_baseline": {"ndcg_at_k": 0.04},
                    "delta_confidence_intervals_95": {"ndcg_at_k": [0.01, 0.07]},
                }
            },
            "hard_exclusion_gate_passed": {"marqo-fashionclip": True},
        }
        self.assertTrue(evaluate_preregistered_challenger_gates(report, registration)["marqo-fashionclip"]["overall_passed"])
        report["paired_vs_baseline"]["marqo-fashionclip"]["delta_vs_baseline"]["ndcg_at_k"] = 0.02
        self.assertFalse(evaluate_preregistered_challenger_gates(report, registration)["marqo-fashionclip"]["overall_passed"])

    def test_hard_exclusion_violation_blocks_challenger_even_if_relevance_wins(self):
        registration = valid_registration()
        report = {
            "paired_vs_baseline": {
                "marqo-fashionclip": {
                    "delta_vs_baseline": {"ndcg_at_k": 0.10},
                    "delta_confidence_intervals_95": {"ndcg_at_k": [0.05, 0.15]},
                }
            },
            "hard_exclusion_gate_passed": {"marqo-fashionclip": False},
        }
        self.assertFalse(evaluate_preregistered_challenger_gates(report, registration)["marqo-fashionclip"]["overall_passed"])

    def test_image_to_image_final_gate_requires_exact_masking_manifest_digest(self):
        registration = valid_registration()
        registration["task_id"] = "image_to_catalog_image"
        registration["privacy_preprocessing_manifest_sha256"] = "f" * 64
        registration["privacy_preprocessing_manifest_path"] = "/private/clickit-masking.json"
        rankings = Path(tempfile.gettempdir()) / "cirvanna-clickit-final-rankings.jsonl"
        rankings.write_text("{}\\n", encoding="utf-8")
        manifest = {
            "schema_version": "1.0",
            "data_rights": {"manifest_sha256": registration["rights_manifest_sha256"]},
            "model_revisions": {
                "cirvanna-fashion-clip": registration["baseline"]["revision"],
                **registration["challengers"],
            },
            "rankings_output_sha256": hashlib.sha256(rankings.read_bytes()).hexdigest(),
            "input_sha256": "b" * 64,
            "query_count": 100,
            "candidate_pool_sizes": [100],
            "split": "test",
            "task_id": "image_to_catalog_image",
            "privacy_preprocessing": {
                "manifest_sha256": "f" * 64,
                "face_masked_before_inference": True,
                "face_recognition": False,
            },
        }
        validate_run_manifest(manifest, registration, rankings, {
            "output_sha256": "b" * 64,
            "query_count": 100,
            "candidate_pool_sizes": [100],
        })
        manifest["privacy_preprocessing"]["manifest_sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "locked masking manifest"):
            validate_run_manifest(manifest, registration, rankings, {
                "output_sha256": "b" * 64,
                "query_count": 100,
                "candidate_pool_sizes": [100],
            })
        rankings.unlink()


if __name__ == "__main__":
    unittest.main()
