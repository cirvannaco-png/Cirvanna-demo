import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.model_evaluation.fashion_retrieval.run_retrieval import (
    MODEL_SPECS,
    parse_revisions,
    rank_candidates,
    build_text_query,
    candidate_text_for_embedding,
    prepare_open_clip_local_dir,
    resolve_media_path,
    sha256_file,
    validate_case,
    validate_privacy_preprocessing_manifest,
)


def make_case():
    return {
        "schema_version": "1.0",
        "query_id": "query-0001",
        "cluster_id": "cluster-0001",
        "task_id": "text_to_catalog_text",
        "split": "test",
        "query_text": "blue cotton shirt",
        "candidate_ids": ["p1", "p2"],
        "candidate_texts": {"p1": "blue cotton shirt", "p2": "red wool coat"},
        "qrels": {"p1": 4, "p2": 0},
        "excluded_product_ids": [],
        "subgroups": {"query_type": "short"},
    }


def make_image_case():
    row = make_case()
    row["task_id"] = "image_to_catalog_image"
    row.pop("query_text")
    row.pop("candidate_texts")
    row["query_image_path"] = "queries/q1.jpg"
    row["candidate_image_paths"] = {
        "p1": "catalog/p1-front.jpg",
        "p2": "catalog/p2-front.jpg",
    }
    return row


class RetrievalRunnerTests(unittest.TestCase):
    def test_known_model_registry_uses_expected_loader_families(self):
        self.assertEqual(MODEL_SPECS["cirvanna-fashion-clip"]["loader"], "transformers_clip")
        self.assertEqual(MODEL_SPECS["marqo-fashionclip"]["loader"], "open_clip")
        self.assertEqual(MODEL_SPECS["marqo-fashionsiglip"]["loader"], "open_clip")
        self.assertEqual(MODEL_SPECS["zooclaw-fashionsiglip2"]["loader"], "transformers_auto")
        self.assertEqual(MODEL_SPECS["marqo-fashionclip"]["default_revision"],
                         "44f4c655124ed71e90cbf528d82f508d69d8a81b")
        self.assertEqual(MODEL_SPECS["marqo-fashionsiglip"]["default_revision"],
                         "c56244cc94f92419e8369fa71efdaf403b124ce8")
        self.assertIsNone(MODEL_SPECS["zooclaw-fashionsiglip2"]["default_revision"])

    def test_research_requirements_pin_compatible_openclip_and_torch(self):
        requirements = Path("tools/model_evaluation/fashion_retrieval/requirements-research.txt")
        content = requirements.read_text(encoding="utf-8")
        self.assertIn("open_clip_torch==4.2.2", content)
        self.assertIn("torch>=2.6,<3", content)
        self.assertIn("timm>=1.0.30,<2", content)

    def test_revision_pin_requires_full_commit_sha(self):
        with self.assertRaisesRegex(ValueError, "40-character"):
            parse_revisions(["marqo-fashionclip=44f4c65"])
        parsed = parse_revisions(["marqo-fashionclip=" + "a" * 40])
        self.assertEqual(parsed["marqo-fashionclip"], "a" * 40)

    def test_ranker_sorts_cosine_scores_deterministically(self):
        ranking, scores = rank_candidates(
            [1.0, 0.0],
            {"p2": [0.0, 1.0], "p1": [1.0, 0.0], "p3": [0.8, 0.6]},
        )
        self.assertEqual(ranking, ["p1", "p3", "p2"])
        self.assertAlmostEqual(scores["p1"], 1.0)
        self.assertAlmostEqual(scores["p3"], 0.8)

    def test_ranker_preserves_frozen_candidate_order_for_exact_ties(self):
        ranking, scores = rank_candidates(
            [1.0, 0.0],
            {"variant-z": [1.0, 0.0], "variant-a": [1.0, 0.0], "variant-m": [0.0, 1.0]},
        )
        self.assertEqual(ranking, ["variant-z", "variant-a", "variant-m"])
        self.assertEqual(scores["variant-z"], scores["variant-a"])

    def test_text_and_candidate_preprocessing_match_the_vision_service_contract(self):
        self.assertEqual(
            build_text_query("  blue   cotton shirt  "),
            "A marketplace product matching this description: blue cotton shirt",
        )
        self.assertEqual(len(build_text_query("x" * 1100)), 1000)
        long_offer = "Fashion or beauty marketplace product. " + ("description " * 150)
        self.assertEqual(candidate_text_for_embedding(long_offer), long_offer[:1000])

    def test_ranker_rejects_dimension_and_non_finite_errors(self):
        with self.assertRaisesRegex(ValueError, "dimension mismatch"):
            rank_candidates([1, 0], {"p1": [1, 0, 0]})
        with self.assertRaisesRegex(ValueError, "non-finite"):
            rank_candidates([float("nan"), 0], {"p1": [1, 0]})

    def test_case_contract_requires_exact_candidate_metadata(self):
        row = make_case()
        self.assertEqual(validate_case(row, 1)["candidate_ids"], ["p1", "p2"])
        row["candidate_texts"].pop("p2")
        with self.assertRaisesRegex(ValueError, "every candidate_id exactly once"):
            validate_case(row, 1)

    def test_case_contract_requires_complete_human_qrels(self):
        row = make_case()
        row["qrels"].pop("p2")
        with self.assertRaisesRegex(ValueError, "explicit grade for every candidate"):
            validate_case(row, 1)

    def test_case_contract_normalizes_human_violation_ids(self):
        row = make_case()
        row["human_exclusion_violation_ids"] = ["p2"]
        validated = validate_case(row, 1)
        self.assertEqual(validated["human_exclusion_violation_ids"], ["p2"])
        row.pop("human_exclusion_violation_ids")
        validated = validate_case(row, 1)
        self.assertEqual(validated["human_exclusion_violation_ids"], [])

    def test_image_task_requires_query_image_path(self):
        row = make_case()
        row["task_id"] = "image_to_catalog_text"
        row.pop("query_text")
        row["query_image_path"] = "queries/q1.jpg"
        validate_case(row, 1)
        row.pop("query_image_path")
        with self.assertRaisesRegex(ValueError, "query_image_path"):
            validate_case(row, 1)

    def test_image_to_image_case_requires_one_catalog_image_per_candidate(self):
        row = make_image_case()
        validated = validate_case(row, 1)
        self.assertEqual(
            validated["candidate_image_paths"],
            {"p1": "catalog/p1-front.jpg", "p2": "catalog/p2-front.jpg"},
        )
        row["candidate_image_paths"].pop("p2")
        with self.assertRaisesRegex(ValueError, "candidate_image_paths must map every candidate_id"):
            validate_case(row, 1)

    def test_image_to_image_case_rejects_mixed_candidate_text(self):
        row = make_image_case()
        row["candidate_texts"] = {"p1": "shirt", "p2": "coat"}
        with self.assertRaisesRegex(ValueError, "must not supply candidate_texts"):
            validate_case(row, 1)

    def test_candidate_image_paths_cannot_escape_approved_media_root(self):
        with self.assertRaisesRegex(ValueError, "inside --media-root"):
            resolve_media_path("/tmp/cirvanna-media", "../private-catalog/secret.jpg")

    def test_image_to_image_requires_reviewed_face_masking_manifest_bound_to_image_digests(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            media = root / "media"
            media.mkdir()
            (media / "query.jpg").write_bytes(b"masked-query-image")
            (media / "candidate.jpg").write_bytes(b"masked-catalog-image")
            evidence = root / "privacy-review.txt"
            evidence.write_text("independent privacy preprocessing review", encoding="utf-8")
            cases = [{
                **make_image_case(),
                "query_image_path": "query.jpg",
                "candidate_image_paths": {"p1": "candidate.jpg", "p2": "candidate.jpg"},
            }]
            manifest = {
                "schema_version": "1.0",
                "approval_status": "approved",
                "scope": "click_it_image_to_image_benchmark",
                "reviewed_by": "privacy-reviewer",
                "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
                "evidence_path": "privacy-review.txt",
                "evidence_sha256": sha256_file(evidence),
                "face_masked_before_inference": True,
                "face_recognition": False,
                "detector_model_id": "cirvanna-face-masker",
                "detector_source_revision": "a" * 40,
                "detector_weights_sha256": "b" * 64,
                "images": {
                    "query.jpg": {
                        "processed_image_sha256": sha256_file(media / "query.jpg"),
                        "faces_masked": 1,
                    },
                    "candidate.jpg": {
                        "processed_image_sha256": sha256_file(media / "candidate.jpg"),
                        "faces_masked": 2,
                    },
                },
            }
            manifest_path = root / "privacy-preprocessing.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = validate_privacy_preprocessing_manifest(manifest_path, cases, media)
            self.assertEqual(result["image_count"], 2)
            self.assertEqual(result["faces_masked_total"], 3)
            self.assertTrue(result["face_masked_before_inference"])
            self.assertFalse(result["face_recognition"])
            manifest["images"]["candidate.jpg"]["processed_image_sha256"] = "c" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                validate_privacy_preprocessing_manifest(manifest_path, cases, media)

    def test_image_to_image_privacy_manifest_rejects_face_recognition(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = root / "privacy-preprocessing.json"
            manifest.write_text(json.dumps({
                "schema_version": "1.0",
                "approval_status": "approved",
                "scope": "click_it_image_to_image_benchmark",
                "reviewed_by": "reviewer",
                "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
                "evidence_path": "missing.txt",
                "evidence_sha256": "b" * 64,
                "face_masked_before_inference": True,
                "face_recognition": True,
                "detector_model_id": "detector",
                "detector_source_revision": "a" * 40,
                "detector_weights_sha256": "b" * 64,
                "images": {},
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "prohibits face recognition"):
                validate_privacy_preprocessing_manifest(manifest, [make_image_case()], root)

    def test_openclip_tokenizer_is_repointed_to_the_pinned_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot = root / "snapshot"
            overlay = root / "overlay"
            snapshot.mkdir()
            (snapshot / "open_clip_config.json").write_text(json.dumps({
                "model_cfg": {"text_cfg": {"hf_tokenizer_name": "timm/ViT-B-16-SigLIP"}}
            }), encoding="utf-8")
            (snapshot / "tokenizer.json").write_text("{}", encoding="utf-8")
            (snapshot / "tokenizer_config.json").write_text("{}", encoding="utf-8")
            uri, overrides = prepare_open_clip_local_dir(snapshot, overlay)
            patched = json.loads((overlay / "open_clip_config.json").read_text(encoding="utf-8"))
            self.assertTrue(uri.startswith("local-dir:"))
            self.assertEqual(patched["model_cfg"]["text_cfg"]["hf_tokenizer_name"], str(snapshot.resolve()))
            self.assertEqual(overrides["hf_tokenizer_name"], "local files from the exact model snapshot")
            self.assertTrue((overlay / "tokenizer.json").is_symlink())

    def test_media_path_cannot_escape_root(self):
        with self.assertRaisesRegex(ValueError, "inside --media-root"):
            resolve_media_path("/tmp/cirvanna-media", "../secret.jpg")


if __name__ == "__main__":
    unittest.main()
