import datetime, hashlib, json, sys, tempfile, unittest
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.model_training.twin_geometry.validate_dataset import validate_dataset, topology_digest, split_manifest_digest
from tools.model_training.twin_geometry.train_shape_model import fit_shape_basis
from tools.model_training.twin_geometry.parametric_body import reconstruct_mesh

LANDMARK_INDICES={"head_top":0,"left_shoulder":1,"left_hip":2,"left_ankle":3,"right_ankle":4,"right_hip":5,"right_shoulder":6}

def synthetic_mesh(width,height,depth):
    outline=np.asarray([
        [0,height,0],[-width,height*0.82,0],[-width*0.7,height*0.5,0],
        [-width*0.25,0,0],[width*0.25,0,0],[width*0.7,height*0.5,0],
        [width,height*0.82,0]
    ],dtype=np.float64)
    front=np.vstack([outline,[0,height*0.45,0]])
    back=front.copy(); back[:,2]=depth
    vertices=np.vstack([front,back])
    faces=[]
    for i in range(7):
        j=(i+1)%7
        faces.extend([[7,i,j],[15,8+j,8+i],[i,j,8+j],[i,8+j,8+i]])
    return vertices,np.asarray(faces,dtype=np.int64)

class TwinGeometryDatasetTests(unittest.TestCase):
    def _fixture(self,root:Path,*,cluster_leak=False,topology_mismatch=False):
        mesh_root=root/"meshes"; mesh_root.mkdir()
        rows=[]; vertices_by_split={}
        splits=("train","train","train","validation","validation","test","test")
        for index,split in enumerate(splits):
            width=240+index*8
            height=1700+(index**2)*4
            depth=140+(index%2)*10
            vertices,faces=synthetic_mesh(width,height,depth)
            if topology_mismatch and index==6:
                faces=faces.copy(); faces[0]=[7,0,2]
            mesh_path=mesh_root/f"scan-{index}.npz"
            np.savez_compressed(mesh_path,vertices=vertices,faces=faces)
            digest=hashlib.sha256(mesh_path.read_bytes()).hexdigest()
            cluster="same-subject" if cluster_leak and index in {0,3} else f"subject-{index}"
            landmarks={name:vertices[vertex].tolist() for name,vertex in LANDMARK_INDICES.items()}
            measurements={
                "height_mm":height,"chest_circumference_mm":900+index*5,
                "waist_circumference_mm":780+index*4,"hip_circumference_mm":960+index*6,
                "inseam_mm":800+index*3
            }
            rows.append({
                "sample_id":f"scan-{index}","subject_cluster_id":cluster,"split":split,
                "mesh_path":mesh_path.name,"mesh_sha256":digest,"alignment_protocol_id":"registered-scan-v1",
                "landmarks_mm":landmarks,"measurements_mm":measurements,"subgroups":{"body_shape":"synthetic"}
            })
            vertices_by_split.setdefault(split,[]).append(vertices)
        annotations=root/"annotations.jsonl"
        annotations.write_text("".join(json.dumps(row,sort_keys=True)+"\n" for row in rows))
        evidence=root/"consent-evidence.txt"; evidence.write_text("verified consent for synthetic fixture")
        rights={
            "schema_version":"1.0","approval_status":"approved","scope":"twin_geometry_training",
            "reviewed_by":"reviewer-1","reviewer_role":"data-rights-owner",
            "reviewed_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source_provenance":"consented 3D scan fixture","evidence_path":str(evidence),
            "evidence_sha256":hashlib.sha256(evidence.read_bytes()).hexdigest(),
            "commercial_evaluation_permitted":True,"human_review_permitted":True,
            "retention_until":(datetime.date.today()+datetime.timedelta(days=30)).isoformat(),
            "contains_personal_images":True,"depicted_person_consent_status":"verified"
        }
        rights_path=root/"rights.json"; rights_path.write_text(json.dumps(rights))
        manifest={
            "schema_version":"1.0","dataset_id":"twin-geometry-synthetic",
            "rights_manifest_sha256":hashlib.sha256(rights_path.read_bytes()).hexdigest(),
            "annotations_sha256":hashlib.sha256(annotations.read_bytes()).hexdigest(),
            "sample_count":len(rows),"units":"millimetres",
            "coordinate_frame":"right_handed_x_right_y_up_z_forward",
            "alignment_protocol_id":"registered-scan-v1",
            "measurement_protocol_id":"anthropometrist-tape-v1",
            "landmark_vertex_indices":LANDMARK_INDICES,
            "template_topology_sha256":topology_digest(synthetic_mesh(240,1700,140)[1],16),
            "split_manifest_sha256":split_manifest_digest(rows)
        }
        manifest_path=root/"dataset.json"; manifest_path.write_text(json.dumps(manifest))
        result=validate_dataset(manifest_path,annotations,mesh_root,rights_path)
        return result,vertices_by_split,synthetic_mesh(width,height,depth)[1]

    def test_validates_consent_bound_registered_scan_cohort(self):
        with tempfile.TemporaryDirectory() as temp:
            result,_,_=self._fixture(Path(temp))
            self.assertEqual(result["status"],"validated_for_shape_model_training_only")
            self.assertEqual(result["split_counts"],{"test":2,"train":3,"validation":2})

    def test_rejects_subject_split_leakage(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"subject clusters leak"):
                self._fixture(Path(temp),cluster_leak=True)

    def test_rejects_topology_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"identical vertex topology"):
                self._fixture(Path(temp),topology_mismatch=True)

    def test_fits_and_reconstructs_parametric_shape_basis(self):
        with tempfile.TemporaryDirectory() as temp:
            _,vertices,faces=self._fixture(Path(temp))
            mean,basis,explained=fit_shape_basis(vertices["train"],components=2)
            reconstructed,output_faces=reconstruct_mesh(mean,basis,np.zeros(len(basis)),faces)
            self.assertEqual(reconstructed.shape,(16,3))
            self.assertEqual(output_faces.shape,faces.shape)
            self.assertEqual(basis.shape,(2,16,3))
            self.assertTrue(np.isfinite(explained).all())
            self.assertTrue(np.all(explained>=0))
            coeff=(vertices["train"][0]-mean).reshape(-1)@basis.reshape(len(basis),-1).T
            restored,_=reconstruct_mesh(mean,basis,coeff,faces)
            self.assertTrue(np.allclose(restored,vertices["train"][0],atol=1e-6))

    def test_rejects_invalid_shape_basis_dimensions(self):
        with self.assertRaisesRegex(ValueError,"at least two"):
            fit_shape_basis([np.zeros((8,3))],1)

if __name__=="__main__": unittest.main()
