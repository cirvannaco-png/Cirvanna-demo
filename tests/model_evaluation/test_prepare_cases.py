import unittest

from tools.model_evaluation.fashion_retrieval.prepare_cases import prepare


def catalog():
    return [
        {"variant_id": "variant-a", "search_text": "Fashion or beauty marketplace product. Navy shirt"},
        {"variant_id": "variant-b", "search_text": "Fashion or beauty marketplace product. Red dress"},
    ]


def query():
    return {
        "schema_version": "1.0",
        "query_id": "query-001",
        "cluster_id": "source-cluster-001",
        "task_id": "text_to_catalog_text",
        "split": "test",
        "query_text": "  navy   shirt  ",
        "candidate_ids": ["variant-a", "variant-b"],
        "qrels": {"variant-a": 4, "variant-b": 0},
        "excluded_product_ids": [],
        "subgroups": {"query_type": "keyword"},
    }


class PrepareCasesTests(unittest.TestCase):
    def test_joins_exact_snapshot_offer_text_to_fixed_candidate_ids(self):
        result = prepare(catalog(), [query()])
        self.assertEqual(result[0]["candidate_texts"]["variant-a"], catalog()[0]["search_text"])
        self.assertEqual(result[0]["query_text"], "navy shirt")
        self.assertEqual(result[0]["candidate_ids"], ["variant-a", "variant-b"])

    def test_rejects_unknown_variant_id(self):
        row = query()
        row["candidate_ids"] = ["variant-a", "missing"]
        row["qrels"] = {"variant-a": 4}
        with self.assertRaisesRegex(ValueError, "not in the frozen eligible offer snapshot"):
            prepare(catalog(), [row])

    def test_rejects_candidate_order_that_differs_from_frozen_commerce_order(self):
        row = query()
        row["candidate_ids"] = ["variant-b", "variant-a"]
        row["qrels"] = {"variant-a": 4, "variant-b": 0}
        with self.assertRaisesRegex(ValueError, "preserve their frozen Commerce offer order"):
            prepare(catalog(), [row])

    def test_requires_a_grade_for_every_candidate(self):
        row = query()
        row["qrels"] = {"variant-a": 4}
        with self.assertRaisesRegex(ValueError, "explicit grade for every candidate"):
            prepare(catalog(), [row])

    def test_preserves_human_adjudicated_violation_ids(self):
        row = query()
        row["human_exclusion_violation_ids"] = ["variant-b"]
        prepared = prepare(catalog(), [row])
        self.assertEqual(prepared[0]["human_exclusion_violation_ids"], ["variant-b"])

    def test_rejects_qrels_with_no_positive_relevance(self):
        row = query()
        row["qrels"] = {"variant-a": 0, "variant-b": 0}
        with self.assertRaisesRegex(ValueError, "positive relevance"):
            prepare(catalog(), [row])

    def test_rejects_duplicate_catalog_ids(self):
        rows = catalog() + [catalog()[0]]
        with self.assertRaisesRegex(ValueError, "duplicate variant_id"):
            prepare(rows, [query()])

    def test_rejects_non_unique_query_ids(self):
        with self.assertRaisesRegex(ValueError, "duplicate query_id"):
            prepare(catalog(), [query(), query()])

    def test_image_queries_require_relative_media_path_field(self):
        row = query()
        row.pop("query_text")
        row["task_id"] = "image_to_catalog_text"
        row["query_image_path"] = "queries/look-001.jpg"
        self.assertIn("query_image_path", prepare(catalog(), [row])[0])
        row.pop("query_image_path")
        with self.assertRaisesRegex(ValueError, "query_image_path"):
            prepare(catalog(), [row])


if __name__ == "__main__":
    unittest.main()
