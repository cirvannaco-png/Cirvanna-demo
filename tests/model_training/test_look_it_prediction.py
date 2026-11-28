import unittest

from tools.model_evaluation.look_it_decomposition.predict import (
    build_prediction_record,
    normalize_box,
)


class LookItPredictionTests(unittest.TestCase):
    def test_normalize_box_clips_to_image_bounds(self):
        self.assertEqual(
            normalize_box([-10, 10, 110, 120], 100, 100),
            [0.0, 0.1, 1.0, 1.0],
        )

    def test_normalize_box_rejects_degenerate_boxes(self):
        self.assertIsNone(normalize_box([10, 10, 10, 20], 100, 100))

    def test_prediction_record_filters_background_low_score_and_invalid_area(self):
        row = {
            "sample_id": "sample-1",
            "cluster_id": "cluster-1",
            "width": 100,
            "height": 100,
            "split": "test",
            "subgroups": {"garment_style": "casual"},
            "components": [
                {"category": "top", "bbox": [0.1, 0.1, 0.8, 0.8], "product_id": "sku-1"}
            ],
        }
        record = build_prediction_record(
            row,
            boxes=[
                [-10, 10, 110, 90],
                [10, 10, 10, 20],
                [5, 5, 25, 25],
                [30, 30, 50, 50],
            ],
            labels=[1, 1, 0, 2],
            scores=[0.9, 0.99, 0.99, 0.1],
            categories=["background", "top", "pants"],
            score_threshold=0.25,
        )
        self.assertEqual(record["split"], "test")
        self.assertEqual(len(record["predicted_components"]), 1)
        self.assertEqual(record["predicted_components"][0]["category"], "top")
        self.assertEqual(record["predicted_components"][0]["bbox"], [0.0, 0.1, 1.0, 0.9])
        self.assertEqual(record["ground_truth_components"][0]["product_id"], "sku-1")

    def test_prediction_record_rejects_mismatched_detector_arrays(self):
        row = {
            "sample_id": "sample-1", "cluster_id": "cluster-1",
            "width": 100, "height": 100, "subgroups": {"group": "a"},
            "components": [],
        }
        with self.assertRaisesRegex(ValueError, "matching lengths"):
            build_prediction_record(row, [[1, 1, 5, 5]], [1], [], ["background", "top"], 0.2)


if __name__ == "__main__":
    unittest.main()
