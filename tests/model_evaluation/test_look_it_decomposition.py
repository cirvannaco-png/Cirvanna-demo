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
