import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.model_evaluation.look_it_decomposition.evaluate import evaluate, validate_record

class LookItDecompositionEvaluationTests(unittest.TestCase):
    def row(self):
        return {"sample_id":"sample-1","cluster_id":"person-session-1","split":"pilot","subgroups":{"lighting":"indoor","occlusion":"low"},
          "ground_truth_components":[{"component_id":"gt-top","category":"upper_body","bbox":[0.1,0.1,0.6,0.6]},{"component_id":"gt-bottom","category":"lower_body","bbox":[0.2,0.5,0.7,0.9]}],
          "predicted_components":[{"component_id":"pred-top","category":"upper_body","bbox":[0.1,0.1,0.6,0.6]},{"component_id":"pred-bag","category":"accessory","bbox":[0.7,0.2,0.9,0.5]}]}
    def test_scores_component_localization_and_category_errors(self):
        result=evaluate([validate_record(self.row(),1)])
        self.assertEqual(result["overall"]["tp"],1); self.assertEqual(result["overall"]["fp"],1); self.assertEqual(result["overall"]["fn"],1)
        self.assertEqual(result["per_category"]["upper_body"]["f1"],1.0)
        self.assertEqual(result["exact_component_count_accuracy"],1.0)
    def test_matching_maximizes_cardinality_before_iou(self):
        gt = [
            {"component_id":"g1","category":"upper_body","bbox":[0.0,0.0,0.8,0.8]},
            {"component_id":"g2","category":"upper_body","bbox":[0.0,0.0,0.5,0.5]},
        ]
        pred = [
            {"component_id":"p1","category":"upper_body","bbox":[0.0,0.0,0.8,0.8]},
            {"component_id":"p2","category":"upper_body","bbox":[0.2,0.2,1.0,1.0]},
        ]
        from tools.model_evaluation.look_it_decomposition.evaluate import match_components
        self.assertEqual(len(match_components(gt, pred, 0.2)), 2)

    def test_rejects_duplicate_sample_and_invalid_box(self):
        row=self.row(); row["predicted_components"][0]["bbox"]=[-0.1,0.1,0.6,0.6]
        with self.assertRaisesRegex(ValueError,"normalized"): validate_record(row,1)
        with self.assertRaisesRegex(ValueError,"unique"): evaluate([validate_record(self.row(),1),validate_record(self.row(),2)])
    def test_rejects_empty_or_invalid_iou_threshold(self):
        with self.assertRaisesRegex(ValueError,"empty"): evaluate([])
        with self.assertRaisesRegex(ValueError,"IoU"): evaluate([validate_record(self.row(),1)],0)
if __name__=="__main__": unittest.main()

def test_scores_component_product_retrieval_when_ground_truth_and_rankings_are_bound():
    row = {
        "sample_id": "sample-product-1",
        "cluster_id": "person-session-product-1",
        "split": "test",
        "subgroups": {"lighting": "studio"},
        "ground_truth_components": [
            {"component_id": "gt-top", "category": "upper_body", "bbox": [0.1, 0.1, 0.6, 0.6], "product_id": "catalog-top-1"}
        ],
        "predicted_components": [
            {"component_id": "pred-top", "category": "upper_body", "bbox": [0.1, 0.1, 0.6, 0.6], "retrieved_product_ids": ["catalog-top-1", "catalog-top-2"]}
        ],
    }
    result = evaluate([validate_record(row, 1)])
    assert result["product_matching"]["status"] == "scored_from_component_retrieval_evidence"
    assert result["product_matching"]["metrics"]["top1_accuracy"] == 1.0
    assert result["product_matching"]["metrics"]["mrr"] == 1.0

def test_product_matching_is_not_claimed_without_product_evidence():
    result = evaluate([validate_record(LookItDecompositionEvaluationTests().row(), 1)])
    assert result["product_matching"]["metrics"] is None
    assert result["product_matching"]["status"].startswith("not_scored")

def test_detector_confidence_produces_per_category_map_at_iou_threshold():
    row = LookItDecompositionEvaluationTests().row()
    row["predicted_components"][0]["confidence"] = 0.95
    row["predicted_components"][1]["confidence"] = 0.40
    result = evaluate([validate_record(row, 1)])
    assert result["average_precision_iou50_per_category"]["upper_body"] == 1.0
    assert result["average_precision_iou50_per_category"]["lower_body"] == 0.0
    assert result["map_iou50"] == 0.5


def test_detector_confidence_must_be_finite_and_bounded():
    row = LookItDecompositionEvaluationTests().row()
    row["predicted_components"][0]["confidence"] = 1.5
    with unittest.TestCase().assertRaisesRegex(ValueError, "confidence"):
        validate_record(row, 1)


def test_model_provenance_must_be_identical_across_evaluation_records():
    first = LookItDecompositionEvaluationTests().row()
    first.update({
        "model_id": "cirvanna-lookit-fasterrcnn-v0",
        "model_checkpoint_sha256": "a" * 64,
        "training_report_sha256": "b" * 64,
        "source_revision": "c" * 40,
    })
    second = LookItDecompositionEvaluationTests().row()
    second["sample_id"] = "sample-2"
    second.update(first)
    second["sample_id"] = "sample-2"
    second["model_checkpoint_sha256"] = "d" * 64
    with unittest.TestCase().assertRaisesRegex(ValueError, "provenance"):
        evaluate([validate_record(first, 1), validate_record(second, 2)])


def test_average_precision_is_not_claimed_without_confidence_scores():
    result = evaluate([validate_record(LookItDecompositionEvaluationTests().row(), 1)])
    assert result["average_precision_iou50_per_category"] is None
    assert result["map_iou50"] is None
