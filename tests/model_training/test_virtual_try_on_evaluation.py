import unittest
import numpy as np

from tools.model_evaluation.virtual_try_on.evaluate import compute_image_metrics, aggregate, METRIC_KEYS


class VirtualTryOnEvaluationTests(unittest.TestCase):
    def test_perfect_render_has_zero_error_and_perfect_masks(self):
        target = np.full((8, 8, 3), 0.4, dtype=np.float64)
        mask = np.zeros((8, 8), dtype=np.float64)
        mask[2:6, 2:6] = 1.0
        metrics = compute_image_metrics(target, target, mask, mask, mask)
        self.assertEqual(metrics["image_mae"], 0.0)
        self.assertEqual(metrics["psnr_db"], 100.0)
        self.assertAlmostEqual(metrics["ssim_global"], 1.0)
        self.assertEqual(metrics["garment_region_mae"], 0.0)
        self.assertEqual(metrics["alpha_mask_iou"], 1.0)
        self.assertEqual(metrics["warped_garment_mask_iou"], 1.0)

    def test_garment_region_error_is_isolated_to_target_garment_mask(self):
        target = np.zeros((8, 8, 3), dtype=np.float64)
        prediction = np.zeros_like(target)
        prediction[2:6, 2:6] = 0.5
        mask = np.zeros((8, 8), dtype=np.float64)
        mask[2:6, 2:6] = 1.0
        metrics = compute_image_metrics(prediction, target, mask, mask, mask)
        self.assertAlmostEqual(metrics["image_mae"], 0.125)
        self.assertAlmostEqual(metrics["garment_region_mae"], 0.5)
        self.assertLess(metrics["psnr_db"], 20.0)

    def test_rejects_shape_mismatch_nonfinite_and_unnormalized_inputs(self):
        target = np.zeros((4, 4, 3), dtype=np.float64)
        mask = np.zeros((4, 4), dtype=np.float64)
        with self.assertRaisesRegex(ValueError, "identical"):
            compute_image_metrics(np.zeros((5, 4, 3)), target, mask, mask, mask)
        invalid = target.copy()
        invalid[0, 0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            compute_image_metrics(invalid, target, mask, mask, mask)
        invalid[0, 0, 0] = 2.0
        with self.assertRaisesRegex(ValueError, "normalized"):
            compute_image_metrics(invalid, target, mask, mask, mask)

    def test_aggregation_uses_per_sample_means_and_rejects_empty(self):
        first = {key: 1.0 for key in METRIC_KEYS}
        second = {key: 3.0 for key in METRIC_KEYS}
        result = aggregate([first, second])
        self.assertTrue(all(value == 2.0 for value in result.values()))
        with self.assertRaisesRegex(ValueError, "empty"):
            aggregate([])

    def test_trainer_does_not_construct_or_evaluate_a_test_loader(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[2] / "tools/model_training/virtual_try_on/train_warp_net.py").read_text()
        self.assertIn('test_rows=[row for row in rows if row["split"]=="test"]', source)
        self.assertIn('"status":"reserved_for_independent_evaluation"', source)
        self.assertNotIn('TryOnDataset("test")', source)
        self.assertNotIn("test_loader", source)
        self.assertNotIn("evaluate(test", source)


if __name__ == "__main__":
    unittest.main()
