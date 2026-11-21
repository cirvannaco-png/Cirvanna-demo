import unittest

from tools.model_evaluation.fashion_retrieval.build_qrels import aggregate
from tools.model_evaluation.fashion_retrieval.prepare_cases import prepare
from tools.model_evaluation.fashion_retrieval.run_retrieval import validate_case


class RetrievalDataPipelineTests(unittest.TestCase):
    def test_reviews_to_qrels_to_catalog_join_to_runner_contract(self):
        queries = [{
            "schema_version": "1.0",
            "query_id": "query-000001",
            "cluster_id": "source-cluster-01",
            "task_id": "text_to_catalog_text",
            "split": "pilot",
            "query_text": "navy cotton shirt",
            "candidate_ids": ["variant-001", "variant-002"],
            "excluded_product_ids": [],
            "subgroups": {"query_type": "keyword", "source_type": "synthetic_fixture"},
            # This must not appear in the approved benchmark export.
            "customer_email": "not-for-export@example.invalid",
        }]
        reviews = [
            {"query_id": "query-000001", "candidate_id": "variant-001",
             "reviewer_key": "reviewer-a", "relevance": 4, "exclusion_violation": False},
            {"query_id": "query-000001", "candidate_id": "variant-001",
             "reviewer_key": "reviewer-b", "relevance": 4, "exclusion_violation": False},
            {"query_id": "query-000001", "candidate_id": "variant-002",
             "reviewer_key": "reviewer-a", "relevance": 0, "exclusion_violation": True},
            {"query_id": "query-000001", "candidate_id": "variant-002",
             "reviewer_key": "reviewer-b", "relevance": 2, "exclusion_violation": True},
        ]
        adjudications = [{
            "query_id": "query-000001",
            "candidate_id": "variant-002",
            "adjudicator_key": "reviewer-c",
            "relevance": 1,
            "exclusion_violation": True,
        }]

        reviewed, summary = aggregate(queries, reviews, adjudications)
        self.assertEqual(summary["adjudicated_pair_count"], 1)
        self.assertEqual(reviewed[0]["qrels"], {"variant-001": 4, "variant-002": 1})
        self.assertEqual(reviewed[0]["human_exclusion_violation_ids"], ["variant-002"])
        self.assertNotIn("customer_email", reviewed[0])

        catalog_snapshot = [
            {"variant_id": "variant-001",
             "search_text": "Fashion or beauty marketplace product. Navy cotton shirt"},
            {"variant_id": "variant-002",
             "search_text": "Fashion or beauty marketplace product. Red wool coat"},
        ]
        prepared = prepare(catalog_snapshot, reviewed)
        runner_case = validate_case(prepared[0], 1)

        self.assertEqual(runner_case["candidate_ids"], ["variant-001", "variant-002"])
        self.assertEqual(runner_case["candidate_texts"]["variant-001"], catalog_snapshot[0]["search_text"])
        self.assertEqual(runner_case["qrels"], reviewed[0]["qrels"])
        self.assertEqual(runner_case["human_exclusion_violation_ids"], ["variant-002"])
        self.assertEqual(runner_case["query_text"], "navy cotton shirt")


if __name__ == "__main__":
    unittest.main()
