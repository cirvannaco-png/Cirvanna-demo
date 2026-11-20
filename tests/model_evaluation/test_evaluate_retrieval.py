import json
import tempfile
import unittest
from pathlib import Path
from tools.model_evaluation.fashion_retrieval.evaluate_retrieval import _validate_record, evaluate, read_cases


def make_case(query_id, cluster_id, baseline, challenger):
    return {
        "schema_version": "1.0", "query_id": query_id, "cluster_id": cluster_id,
        "task_id": "image_to_catalog_text", "split": "test",
        "candidate_ids": ["p1", "p2", "p3", "p4"],
        "qrels": {"p1": 4, "p2": 2, "p3": 0},
        "rankings": {"cirvanna-fashion-clip": baseline, "challenger": challenger},
        "excluded_product_ids": ["p4"],
        "subgroups": {"source_type": "street", "query_type": "image"},
    }


class RetrievalEvaluationTests(unittest.TestCase):
    def test_metrics_paired_deltas_and_exclusion_gate(self):
        cases = [
            make_case("query-001", "cluster-001", ["p3", "p4", "p1"], ["p1", "p2", "p3"]),
            make_case("query-002", "cluster-002", ["p2", "p3"], ["p2", "p1"]),
        ]
        report = evaluate(cases, baseline_model_id="cirvanna-fashion-clip", k=2,
                          primary_metric="ndcg_at_k", bootstrap_samples=100)
        self.assertEqual(report["status"], "evaluated_rankings_only")
        self.assertGreater(report["systems"]["challenger"]["metrics"]["ndcg_at_k"],
                           report["systems"]["cirvanna-fashion-clip"]["metrics"]["ndcg_at_k"])
        self.assertGreater(report["paired_vs_baseline"]["challenger"]["delta_vs_baseline"]["ndcg_at_k"], 0)
        self.assertFalse(report["hard_exclusion_gate_passed"]["cirvanna-fashion-clip"])
        self.assertTrue(report["hard_exclusion_gate_passed"]["challenger"])
        self.assertIn("source_type", report["subgroups"])

    def test_candidate_ids_are_shared_and_rankings_cannot_escape_pool(self):
        row = make_case("query-001", "cluster-001", ["p1"], ["p2"])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.jsonl"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            self.assertEqual(len(read_cases(path)), 1)
            row["rankings"]["challenger"] = ["unknown-product"]
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside candidate_ids"):
                read_cases(path)

    def test_rejects_mixed_tasks_and_model_sets(self):
        a = make_case("query-001", "cluster-001", ["p1"], ["p2"])
        b = make_case("query-002", "cluster-002", ["p1"], ["p2"])
        b["task_id"] = "text_to_catalog_text"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.jsonl"
            path.write_text("\n".join(json.dumps(x) for x in [a, b]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "do not mix retrieval tasks"):
                read_cases(path)
            b["task_id"] = a["task_id"]
            b["rankings"] = {"cirvanna-fashion-clip": ["p1"], "other": ["p2"]}
            path.write_text("\n".join(json.dumps(x) for x in [a, b]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "same model IDs"):
                read_cases(path)

    def test_one_cluster_does_not_claim_confidence_interval(self):
        case = make_case("query-001", "single-cluster", ["p1"], ["p2"])
        report = evaluate([case], baseline_model_id="cirvanna-fashion-clip", k=2,
                          primary_metric="ndcg_at_k", bootstrap_samples=100)
        self.assertIsNone(report["systems"]["challenger"]["confidence_intervals_95"]["ndcg_at_k"])

    def test_requires_positive_human_relevance_and_valid_exclusion_ids(self):
        row = make_case("query-001", "cluster-001", ["p1"], ["p2"])
        row["qrels"] = {"p3": 0}
        with self.assertRaisesRegex(ValueError, "positive relevance"):
            _validate_record(row, 1)
        row = make_case("query-001", "cluster-001", ["p1"], ["p2"])
        row["excluded_product_ids"] = ["unknown"]
        with self.assertRaisesRegex(ValueError, "excluded_product_ids"):
            _validate_record(row, 1)


if __name__ == "__main__":
    unittest.main()
