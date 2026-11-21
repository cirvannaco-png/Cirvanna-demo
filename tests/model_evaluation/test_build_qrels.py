import unittest

from tools.model_evaluation.fashion_retrieval.build_qrels import aggregate


def queries():
    return [{
        "schema_version": "1.0",
        "query_id": "query-0001",
        "cluster_id": "cluster-0001",
        "task_id": "text_to_catalog_text",
        "split": "test",
        "query_text": "navy shirt",
        "candidate_ids": ["variant-a", "variant-b"],
        "excluded_product_ids": [],
        "subgroups": {"query_type": "keyword"},
    }]


def reviews():
    return [
        {"query_id": "query-0001", "candidate_id": "variant-a", "reviewer_key": "reviewer-a",
         "relevance": 4, "exclusion_violation": False},
        {"query_id": "query-0001", "candidate_id": "variant-a", "reviewer_key": "reviewer-b",
         "relevance": 4, "exclusion_violation": False},
        {"query_id": "query-0001", "candidate_id": "variant-b", "reviewer_key": "reviewer-a",
         "relevance": 0, "exclusion_violation": True},
        {"query_id": "query-0001", "candidate_id": "variant-b", "reviewer_key": "reviewer-b",
         "relevance": 2, "exclusion_violation": True},
    ]


class BuildQrelsTests(unittest.TestCase):
    def test_builds_complete_qrels_and_human_violation_ids(self):
        adjudication = [{
            "query_id": "query-0001", "candidate_id": "variant-b", "adjudicator_key": "reviewer-c",
            "relevance": 1, "exclusion_violation": True,
        }]
        rows, summary = aggregate(queries(), reviews(), adjudication)
        self.assertEqual(rows[0]["qrels"], {"variant-a": 4, "variant-b": 1})
        self.assertEqual(rows[0]["human_exclusion_violation_ids"], ["variant-b"])
        self.assertEqual(summary["candidate_review_pair_count"], 2)
        self.assertEqual(summary["adjudicated_pair_count"], 1)
        self.assertEqual(summary["exact_reviewer_agreement_rate"], 0.5)

    def test_export_drops_unapproved_fields_and_reviewer_identifiers(self):
        query = queries()[0]
        query["query_text"] = "navy shirt"
        query["user_email"] = "private@example.invalid"
        query["account_id"] = "account-123"
        rows, _ = aggregate([query], reviews(), [{
            "query_id": "query-0001", "candidate_id": "variant-b", "adjudicator_key": "reviewer-c",
            "relevance": 1, "exclusion_violation": True,
        }])
        self.assertNotIn("user_email", rows[0])
        self.assertNotIn("account_id", rows[0])
        self.assertNotIn("human_reviews", rows[0])
        self.assertEqual(rows[0]["query_text"], "navy shirt")

    def test_image_query_export_requires_relative_path_and_drops_unknown_metadata(self):
        query = queries()[0]
        query["task_id"] = "image_to_catalog_text"
        query["query_image_path"] = "queries/query-0001.jpg"
        query["owner_name"] = "should-not-be-exported"
        rows, _ = aggregate([query], reviews(), [{
            "query_id": "query-0001", "candidate_id": "variant-b", "adjudicator_key": "reviewer-c",
            "relevance": 1, "exclusion_violation": True,
        }])
        self.assertEqual(rows[0]["query_image_path"], "queries/query-0001.jpg")
        self.assertNotIn("owner_name", rows[0])
        query["query_image_path"] = "/private/query.jpg"
        with self.assertRaisesRegex(ValueError, "relative path"):
            aggregate([query], reviews(), [{
                "query_id": "query-0001", "candidate_id": "variant-b", "adjudicator_key": "reviewer-c",
                "relevance": 1, "exclusion_violation": True,
            }])

    def test_requires_two_distinct_reviews_for_every_candidate(self):
        with self.assertRaisesRegex(ValueError, "exactly two distinct independent reviewer records"):
            aggregate(queries(), reviews()[:-1], [])

    def test_requires_independent_adjudication_when_labels_disagree(self):
        with self.assertRaisesRegex(ValueError, "requires adjudication"):
            aggregate(queries(), reviews(), [])
        adjudication = [{
            "query_id": "query-0001", "candidate_id": "variant-b", "adjudicator_key": "reviewer-a",
            "relevance": 1, "exclusion_violation": True,
        }]
        with self.assertRaisesRegex(ValueError, "adjudicator must be independent"):
            aggregate(queries(), reviews(), adjudication)

    def test_rejects_duplicate_reviewers(self):
        items = reviews()
        items[1]["reviewer_key"] = "reviewer-a"
        with self.assertRaisesRegex(ValueError, "exactly two distinct independent reviewer records"):
            aggregate(queries(), items, [])

    def test_rejects_extra_or_duplicate_adjudications(self):
        first = {"query_id": "query-0001", "candidate_id": "variant-b",
                 "adjudicator_key": "reviewer-c", "relevance": 1, "exclusion_violation": True}
        second = {**first, "adjudicator_key": "reviewer-d"}
        with self.assertRaisesRegex(ValueError, "duplicate adjudication"):
            aggregate(queries(), reviews(), [first, second])

    def test_requires_boolean_violation_and_valid_grade(self):
        items = reviews()
        items[0]["exclusion_violation"] = "false"
        with self.assertRaisesRegex(ValueError, "exclusion_violation must be boolean"):
            aggregate(queries(), items, [])


if __name__ == "__main__":
    unittest.main()
