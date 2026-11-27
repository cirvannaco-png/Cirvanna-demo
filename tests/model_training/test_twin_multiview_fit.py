import sys, unittest, tempfile, json, hashlib, datetime
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.model_training.twin_geometry.train_shape_model import fit_shape_basis
from tools.model_training.twin_geometry.parametric_body import reconstruct_mesh
from tools.model_training.twin_geometry.fit_multiview_capture import fit_coefficients, validate_capture

LANDMARK_INDICES={"head_top":0,"left_shoulder":1,"left_hip":2,"left_ankle":3,"right_ankle":4,"right_hip":5,"right_shoulder":6}

def synthetic_mesh(width,height,depth):
    outline=np.asarray([[0,height,0],[-width,height*.82,0],[-width*.7,height*.5,0],[-width*.25,0,0],[width*.25,0,0],[width*.7,height*.5,0],[width,height*.82,0]],dtype=float)
    front=np.vstack([outline,[0,height*.45,0]])
    back=front.copy(); back[:,2]=depth
    vertices=np.vstack([front,back])
    faces=[]
    for i in range(7):
        j=(i+1)%7
        faces.extend([[7,i,j],[15,8+j,8+i],[i,j,8+j],[i,8+j,8+i]])
    return vertices,np.asarray(faces,dtype=np.int64)

def make_view(view_id,camera,vertices):
    width=height=2000
    homogeneous=np.column_stack([vertices,np.ones(len(vertices))])
    projected=(camera@homogeneous.T).T
    px=projected[:,0]/projected[:,2]/width
    py=projected[:,1]/projected[:,2]/height
    keypoints={}
    for name,index in LANDMARK_INDICES.items():
        keypoints[name]=[float(px[index]),float(py[index]),1.0]
    return {
        "view_id":view_id,"image_sha256":"a"*64,"image_width":width,"image_height":height,
        "camera_matrix":camera.tolist(),"keypoints":keypoints,
        "silhouette_mask_sha256":"b"*64,
        "silhouette_bbox":[float(px.min()),float(py.min()),float(px.max()),float(py.max())],
        "silhouette_confidence":1.0
    }

class TwinMultiviewFitTests(unittest.TestCase):
    def setUp(self):
        scans=[synthetic_mesh(240+i*8,1700+(i**2)*4,140+(i%2)*10)[0] for i in range(3)]
        self.mean,self.basis,self.explained=fit_shape_basis(scans,components=2)
        coefficients=np.asarray([(scan-self.mean).reshape(-1)@self.basis.reshape(2,-1).T for scan in scans])
        self.coefficient_std=np.maximum(coefficients.std(axis=0),1e-6)
        self.faces=synthetic_mesh(240,1700,140)[1]
        self.target=np.asarray([0.35,-0.25])*self.coefficient_std
        self.target_vertices,_=reconstruct_mesh(self.mean,self.basis,self.target,self.faces)
        self.landmark_names=list(LANDMARK_INDICES)
        self.landmark_indices=np.asarray([LANDMARK_INDICES[name] for name in self.landmark_names])
        self.views=[
            make_view("front",np.asarray([[1,0,0,1000],[0,-1,0,1800],[0,0,0,1]],dtype=float),self.target_vertices),
            make_view("side",np.asarray([[0,0,1,1000],[0,-1,0,1800],[0,0,0,1]],dtype=float),self.target_vertices)
        ]

    def test_fits_shape_coefficients_from_two_calibrated_views_and_silhouettes(self):
        result=fit_coefficients(self.mean,self.basis,self.coefficient_std,self.faces,self.landmark_indices,self.landmark_names,self.views,prior_strength=0.01,max_iterations=200)
        self.assertTrue(np.allclose(result["coefficients"],self.target,atol=1.0))
        self.assertLess(result["reprojection_rmse_pixels"],0.01)
        self.assertEqual(result["vertices"].shape,self.mean.shape)

    def test_capture_validation_requires_consent_and_valid_silhouette_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            evidence=root/"consent.txt"; evidence.write_text("verified participant consent")
            rights={
                "schema_version":"1.0","approval_status":"approved","scope":"twin_geometry_inference",
                "reviewed_by":"reviewer-1","reviewer_role":"privacy-owner",
                "reviewed_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "source_provenance":"controlled capture test","evidence_path":str(evidence),
                "evidence_sha256":hashlib.sha256(evidence.read_bytes()).hexdigest(),
                "commercial_evaluation_permitted":True,"human_review_permitted":True,
                "retention_until":(datetime.date.today()+datetime.timedelta(days=10)).isoformat(),
                "contains_personal_images":True,"depicted_person_consent_status":"verified"
            }
            rights_path=root/"rights.json"; rights_path.write_text(json.dumps(rights))
            rights_digest=hashlib.sha256(rights_path.read_bytes()).hexdigest()
            model={"landmark_names":np.asarray(self.landmark_names)}
            invalid=dict(self.views[0]); invalid["silhouette_bbox"]=[0.8,0.1,0.2,0.9]
            capture={"schema_version":"1.0","capture_id":"capture-1","capture_protocol_id":"front-side-v1","camera_calibration_evidence_ref":"calibration:fixture","rights_manifest_sha256":rights_digest,"face_masked_before_inference":True,"preprocessing_manifest_sha256":"c"*64,"keypoint_model":{"model_id":"cvi-pose","source_revision":"d"*40,"weights_sha256":"e"*64},"silhouette_model":{"model_id":"cvi-silhouette","source_revision":"f"*40,"weights_sha256":"1"*64},"views":[invalid,self.views[1]]}
            with self.assertRaisesRegex(ValueError,"silhouette bounding box is invalid"):
                validate_capture(capture,rights_path,model)

    def test_requires_multiple_views_and_valid_silhouette(self):
        model={"landmark_names":np.asarray(self.landmark_names)}
        capture={"schema_version":"1.0","capture_id":"capture-1","capture_protocol_id":"front-side-v1","camera_calibration_evidence_ref":"calibration:fixture","face_masked_before_inference":True,"preprocessing_manifest_sha256":"c"*64,"keypoint_model":{"model_id":"cvi-pose","source_revision":"d"*40,"weights_sha256":"e"*64},"silhouette_model":{"model_id":"cvi-silhouette","source_revision":"f"*40,"weights_sha256":"1"*64},"views":[self.views[0]]}
        with self.assertRaisesRegex(ValueError,"at least two"):
            validate_capture(capture,Path("unused"),model)

    def test_exports_closed_texture_free_glb_candidate(self):
        from tools.model_training.twin_geometry.parametric_body import export_mesh_only_glb
        data,quality=export_mesh_only_glb(self.target_vertices,self.faces)
        self.assertTrue(data.startswith(b"glTF"))
        self.assertTrue(quality["watertight"])
        self.assertTrue(quality["winding_consistent"])
        self.assertFalse(quality["embedded_textures"])
        import importlib.util
        validator_path=Path(__file__).resolve().parents[2]/"services/twin-mesh-validator/app/main.py"
        spec=importlib.util.spec_from_file_location("cvi_twin_mesh_validator",validator_path)
        validator=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        independent=validator.inspect_glb(data)
        self.assertTrue(independent["geometry_finite"])
        self.assertTrue(independent["degenerate_triangles_absent"])
        self.assertTrue(independent["nonmanifold_edges_absent"])
        self.assertEqual(independent["boundary_edge_count"],0)

if __name__=="__main__": unittest.main()
