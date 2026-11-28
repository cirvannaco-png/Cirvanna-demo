import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.model_evaluation.virtual_try_on.evaluate import mean_metrics

class VirtualTryOnEvaluationTests(unittest.TestCase):
    def test_macro_metrics_average_each_test_sample_equally(self):
        result = mean_metrics([
            {"image_mae": 0.1, "ssim_global": 0.8},
            {"image_mae": 0.3, "ssim_global": 0.6},
        ])
        self.assertAlmostEqual(result["image_mae"], 0.2)
        self.assertAlmostEqual(result["ssim_global"], 0.7)

    def test_empty_test_metrics_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            mean_metrics([])

if __name__ == "__main__":
    unittest.main()
