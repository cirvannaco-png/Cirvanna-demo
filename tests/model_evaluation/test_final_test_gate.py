import unittest

from tools.model_evaluation.fashion_retrieval.evaluate_retrieval import (
    validate_final_test_registration,
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


if __name__ == "__main__":
    unittest.main()
