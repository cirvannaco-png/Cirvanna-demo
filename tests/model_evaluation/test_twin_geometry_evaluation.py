import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.model_evaluation.twin_geometry.evaluate import measurement_metrics, surface_metrics, mean_dict

class TwinGeometryEvaluationTests(unittest.TestCase):
    def test_measurement_metrics_are_computed_over_all_held_out_samples(self):
        result = measurement_metrics(np.array([100.0, 110.0, 120.0]), np.array([102.0, 100.0, 132.0]))
        self.assertEqual(result["sample_count"], 3)
        self.assertAlmostEqual(result["mae_mm"], 8.0)
        self.assertAlmostEqual(result["median_absolute_error_mm"], 10.0)
        self.assertAlmostEqual(result["bias_mm"], 4.0 / 3.0)

    def test_surface_metrics_use_corresponding_registered_vertices(self):
        actual = np.array([[0.0,0.0,0.0],[0.0,0.0,3.0]])
        predicted = np.array([[0.0,0.0,1.0],[0.0,0.0,5.0]])
        result = surface_metrics(actual,predicted)
        self.assertAlmostEqual(result["mean_vertex_error_mm"], 1.5)
        self.assertAlmostEqual(result["max_vertex_error_mm"], 2.0)

    def test_rejects_incompatible_registered_meshes(self):
        with self.assertRaisesRegex(ValueError,"identical Nx3"):
            surface_metrics(np.zeros((3,3)),np.zeros((4,3)))

    def test_macro_surface_metrics_require_nonempty_samples(self):
        with self.assertRaisesRegex(ValueError,"empty"):
            mean_dict([])

if __name__ == "__main__":
    unittest.main()
