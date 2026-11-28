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

    def test_end_to_end_evaluator_binds_frozen_model_and_held_out_split(self):
        import hashlib
        import json
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        from tools.model_evaluation.twin_geometry import evaluate as evaluator

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mesh_root = root / "meshes"
            mesh_root.mkdir()
            mesh_path = mesh_root / "held-out.npz"
            vertices = np.array([
                [0., 1800., 0.], [-120., 1500., 0.], [120., 1500., 0.],
                [-100., 1000., 0.], [100., 1000., 0.], [-80., 100., 0.],
                [80., 100., 0.]
            ])
            faces = np.array([[0,1,2],[1,3,4],[3,5,6],[1,2,4]], dtype=np.int64)
            np.savez_compressed(mesh_path, vertices=vertices, faces=faces)
            mesh_sha = hashlib.sha256(mesh_path.read_bytes()).hexdigest()
            landmark_names = [
                "head_top", "left_shoulder", "right_shoulder", "left_hip",
                "right_hip", "left_ankle", "right_ankle"
            ]
            landmark_map = dict(zip(landmark_names, range(7)))
            measurements = {
                "height_mm": 1800., "chest_circumference_mm": 950.,
                "waist_circumference_mm": 800., "hip_circumference_mm": 980.,
                "inseam_mm": 820.
            }
            annotation = {
                "sample_id": "held-out-001", "subject_cluster_id": "subject-001",
                "split": "test", "mesh_path": "held-out.npz", "mesh_sha256": mesh_sha,
                "measurements_mm": measurements, "subgroups": {"body_type": "group-a"}
            }
            annotations_path = root / "annotations.jsonl"
            annotations_path.write_text(json.dumps(annotation) + "\n")
            manifest_path = root / "dataset.manifest.json"
            manifest_path.write_text('{"dataset_id":"fixture"}')
            model_path = root / "model.npz"
            calibration = np.zeros((2, 5), dtype=np.float64)
            calibration[0] = list(measurements.values())
            np.savez_compressed(
                model_path, mean_vertices=vertices, shape_basis=np.ones((1,7,3))*0.001,
                coefficient_std=np.ones(1), faces=faces,
                measurement_calibration=calibration,
                measurement_names=np.asarray(list(measurements)),
                landmark_names=np.asarray(landmark_names),
                landmark_vertex_indices=np.arange(7, dtype=np.int64)
            )
            report_path = root / "training-report.json"
            manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            report_path.write_text(json.dumps({
                "model_id": evaluator.MODEL_ID, "architecture": evaluator.ARCHITECTURE,
                "source_revision": "a"*40,
                "artifact_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                "dataset": {
                    "dataset_manifest_sha256": manifest_sha,
                    "annotations_sha256": "b"*64, "split_manifest_sha256": "c"*64,
                    "rights_manifest_sha256": "d"*64
                },
                "held_out_test": {"status": "reserved_for_independent_evaluation", "sample_count": 1}
            }))
            dataset = {
                "annotations_sha256": "b"*64, "split_manifest_sha256": "c"*64,
                "rights_manifest_sha256": "d"*64, "topology_sha256": evaluator.topology_digest(faces, len(vertices)),
                "landmark_vertex_indices": landmark_map
            }
            args = SimpleNamespace(
                model=model_path, training_report=report_path, manifest=manifest_path,
                annotations=annotations_path, mesh_root=mesh_root, rights_manifest=root/"rights.json"
            )
            with patch.object(evaluator, "require_clean_source_revision", return_value="a"*40), \
                 patch.object(evaluator, "validate_dataset", return_value=dataset), \
                 patch.object(evaluator, "safe_mesh_path", return_value=mesh_path):
                result = evaluator.run(args)
            self.assertEqual(result["sample_count"], 1)
            self.assertTrue(result["held_out_measurement_accuracy_gate"]["passed"])
            self.assertEqual(result["measurements"]["height_mm"]["mape_percent"], 0.0)
            self.assertEqual(result["subgroups"]["body_type=group-a"]["sample_count"], 1)

    def test_end_to_end_evaluator_rejects_wrong_landmark_binding(self):
        # The model's anatomical landmark map must match the validated manifest.
        import hashlib
        import json
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        from tools.model_evaluation.twin_geometry import evaluate as evaluator

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mesh_root = root / "meshes"
            mesh_root.mkdir()
            mesh_path = mesh_root / "held-out.npz"
            vertices = np.arange(21, dtype=np.float64).reshape(7,3)
            faces = np.array([[0,1,2],[1,3,4],[3,5,6],[1,2,4]], dtype=np.int64)
            np.savez_compressed(mesh_path, vertices=vertices, faces=faces)
            mesh_sha = hashlib.sha256(mesh_path.read_bytes()).hexdigest()
            names = ["head_top","left_shoulder","right_shoulder","left_hip","right_hip","left_ankle","right_ankle"]
            measurement_names = ["height_mm","chest_circumference_mm","waist_circumference_mm","hip_circumference_mm","inseam_mm"]
            row = {"sample_id":"s1","subject_cluster_id":"c1","split":"test","mesh_path":"held-out.npz","mesh_sha256":mesh_sha,
                   "measurements_mm":dict.fromkeys(measurement_names,800),"subgroups":{"cohort":"a"}}
            annotations=root/"annotations.jsonl"; annotations.write_text(json.dumps(row)+"\n")
            manifest=root/"manifest.json"; manifest.write_text("{}")
            model=root/"model.npz"
            np.savez_compressed(model,mean_vertices=vertices,shape_basis=np.ones((1,7,3)),coefficient_std=np.ones(1),
                faces=faces,measurement_calibration=np.ones((2,5)),measurement_names=np.asarray(measurement_names),
                landmark_names=np.asarray(names),landmark_vertex_indices=np.arange(7))
            report=root/"training.json"
            report.write_text(json.dumps({"model_id":evaluator.MODEL_ID,"architecture":evaluator.ARCHITECTURE,
                "source_revision":"a"*40,"artifact_sha256":hashlib.sha256(model.read_bytes()).hexdigest(),
                "dataset":{"dataset_manifest_sha256":hashlib.sha256(manifest.read_bytes()).hexdigest(),
                    "annotations_sha256":"b"*64,"split_manifest_sha256":"c"*64,"rights_manifest_sha256":"d"*64},
                "held_out_test":{"status":"reserved_for_independent_evaluation","sample_count":1}}))
            dataset={"annotations_sha256":"b"*64,"split_manifest_sha256":"c"*64,"rights_manifest_sha256":"d"*64,
                "topology_sha256":evaluator.topology_digest(faces,len(vertices)),
                "landmark_vertex_indices":dict(zip(names,[1,0,2,3,4,5,6]))}
            args=SimpleNamespace(model=model,training_report=report,manifest=manifest,annotations=annotations,
                mesh_root=mesh_root,rights_manifest=root/"rights.json")
            with patch.object(evaluator,"require_clean_source_revision",return_value="a"*40), \
                 patch.object(evaluator,"validate_dataset",return_value=dataset), \
                 patch.object(evaluator,"safe_mesh_path",return_value=mesh_path):
                with self.assertRaisesRegex(ValueError,"landmark map differs"):
                    evaluator.run(args)

if __name__ == "__main__":
    unittest.main()
