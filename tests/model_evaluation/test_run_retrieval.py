import unittest

from tools.model_evaluation.fashion_retrieval.run_retrieval import (
    MODEL_SPECS,
    parse_revisions,
    rank_candidates,
    resolve_media_path,
    validate_case,
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


class RetrievalRunnerTests(unittest.TestCase):
    def test_known_model_registry_uses_expected_loader_families(self):
        self.assertEqual(MODEL_SPECS["cirvanna-fashion-clip"]["loader"], "transformers_clip")
        self.assertEqual(MODEL_SPECS["marqo-fashionclip"]["loader"], "open_clip")
        self.assertEqual(MODEL_SPECS["marqo-fashionsiglip"]["loader"], "open_clip")
        self.assertEqual(MODEL_SPECS["zooclaw-fashionsiglip2"]["loader"], "transformers_auto")

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

    def test_image_task_requires_query_image_path(self):
        row = make_case()
        row["task_id"] = "image_to_catalog_text"
        row.pop("query_text")
        row["query_image_path"] = "queries/q1.jpg"
        validate_case(row, 1)
        row.pop("query_image_path")
        with self.assertRaisesRegex(ValueError, "query_image_path"):
            validate_case(row, 1)

    def test_media_path_cannot_escape_root(self):
        with self.assertRaisesRegex(ValueError, "inside --media-root"):
            resolve_media_path("/tmp/cirvanna-media", "../secret.jpg")


if __name__ == "__main__":
    unittest.main()
