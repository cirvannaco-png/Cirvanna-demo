import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.model_training.twin_geometry import train_shape_model as trainer


class TwinShapeTrainingSealingTests(unittest.TestCase):
    def test_trainer_never_opens_held_out_test_meshes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mesh_root = root / "meshes"
            mesh_root.mkdir()
            faces = np.array([[0,1,2],[1,3,4],[3,5,6],[1,2,4]], dtype=np.int64)
            base = np.array([
                [0.,1800.,0.],[-120.,1500.,0.],[120.,1500.,0.],
                [-100.,1000.,0.],[100.,1000.,0.],[-80.,100.,0.],[80.,100.,0.]
            ])
            rows = []
            for index, split in enumerate(("train", "train", "validation", "test")):
                sample_id = f"{split}-{index}"
                relative = f"{sample_id}.npz"
                if split != "test":
                    vertices = base.copy()
                    vertices[:,0] += index * np.linspace(-5, 5, len(vertices))
                    np.savez_compressed(mesh_root / relative, vertices=vertices, faces=faces)
                rows.append({
                    "sample_id": sample_id, "subject_cluster_id": f"cluster-{index}",
                    "split": split, "mesh_path": relative,
                    "measurements_mm": {
                        "height_mm": 1800 + index, "chest_circumference_mm": 950 + index,
                        "waist_circumference_mm": 800 + index, "hip_circumference_mm": 980 + index,
                        "inseam_mm": 820 + index
                    }
                })
            annotations = root / "annotations.jsonl"
            annotations.write_text("".join(json.dumps(row) + "\n" for row in rows))
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "landmark_vertex_indices": {
                    "head_top":0,"left_shoulder":1,"right_shoulder":2,"left_hip":3,
                    "right_hip":4,"left_ankle":5,"right_ankle":6
                }
            }))
            rights = root / "rights.json"
            rights.write_text("{}")
            output = root / "model-output"
            opened = []

            def safe_path(_root, relative):
                opened.append(relative)
                if relative.endswith("test-3.npz"):
                    raise AssertionError("trainer attempted to open held-out test mesh")
                return mesh_root / relative

            argv = [
                "train_shape_model.py", "--manifest", str(manifest),
                "--annotations", str(annotations), "--mesh-root", str(mesh_root),
                "--rights-manifest", str(rights), "--output-dir", str(output),
                "--components", "1", "--ridge-alpha", "1.0"
            ]
            dataset = {"annotations_sha256":"a"*64,"split_manifest_sha256":"b"*64,"rights_manifest_sha256":"c"*64}
            with patch.object(trainer, "require_clean_source_revision", return_value="d"*40), \
                 patch.object(trainer, "validate_dataset", return_value=dataset), \
                 patch.object(trainer, "safe_mesh_path", side_effect=safe_path), \
                 patch.object(sys, "argv", argv):
                self.assertEqual(trainer.main(), 0)

            report = json.loads((output / "training-report.json").read_text())
            self.assertEqual(report["held_out_test"], {
                "status": "reserved_for_independent_evaluation", "sample_count": 1
            })
            self.assertEqual(set(opened), {"train-0.npz", "train-1.npz", "validation-2.npz"})
            self.assertTrue(all("test-" not in value for value in opened))


if __name__ == "__main__":
    unittest.main()
