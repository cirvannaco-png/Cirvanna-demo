import unittest
from tools.model_evaluation.fashion_retrieval.validate_preregistration import validate_registration


def valid_registration():
    return {
        "schema_version": "1.0",
        "experiment_id": "test-run-001",
        "status": "locked",
        "registered_at_utc": "2026-11-21T06:00:00Z",
        "task_id": "image_to_catalog_text",
        "split": "test",
        "primary_metric": "ndcg_at_k",
        "k": 10,
        "minimum_practically_important_delta": 0.03,
        "minimum_query_count": 100,
        "minimum_independent_clusters": 50,
        "candidate_pool_sizes": [100, 500, 1000],
        "bootstrap_samples": 2000,
        "bootstrap_seed": 20261121,
        "baseline": {
            "model_id": "cirvanna-fashion-clip",
            "revision": "afacf5e5851d5979ab030e228eab60e2c95a912c",
        },
        "challengers": {
            "marqo-fashionclip": "44f4c655124ed71e90cbf528d82f508d69d8a81b"
        },
        "data_manifest_sha256": "a" * 64,
        "qrels_manifest_sha256": "b" * 64,
        "dependency_lock_sha256": "c" * 64,
    }


class PreregistrationTests(unittest.TestCase):
    def test_accepts_complete_locked_registration(self):
        self.assertEqual(validate_registration(valid_registration())["status"], "locked")

    def test_rejects_unlocked_template(self):
        row = valid_registration()
        row["status"] = "draft"
        with self.assertRaisesRegex(ValueError, "status must be 'locked'"):
            validate_registration(row)

    def test_rejects_post_hoc_primary_metric_change(self):
        row = valid_registration()
        row["primary_metric"] = "mrr_at_k"
        with self.assertRaisesRegex(ValueError, "fixed as ndcg_at_k"):
            validate_registration(row)

    def test_requires_full_catalogue_candidate_pool(self):
        row = valid_registration()
        row["candidate_pool_sizes"] = [100, 500]
        with self.assertRaisesRegex(ValueError, "must include 1000"):
            validate_registration(row)

    def test_rejects_missing_independent_cluster_power_plan(self):
        row = valid_registration()
        row["minimum_independent_clusters"] = 1
        with self.assertRaisesRegex(ValueError, "minimum_independent_clusters"):
            validate_registration(row)

    def test_rejects_floating_model_revision(self):
        row = valid_registration()
        row["challengers"]["marqo-fashionclip"] = "main"
        with self.assertRaisesRegex(ValueError, "full 40-character"):
            validate_registration(row)

    def test_rejects_invalid_provenance_digest(self):
        row = valid_registration()
        row["data_manifest_sha256"] = "unknown"
        with self.assertRaisesRegex(ValueError, "data_manifest_sha256"):
            validate_registration(row)


if __name__ == "__main__":
    unittest.main()
