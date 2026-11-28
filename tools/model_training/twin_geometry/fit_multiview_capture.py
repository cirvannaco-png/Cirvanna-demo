#!/usr/bin/env python3
"""Fit the Cirvanna parametric body basis to calibrated multi-view 2D body landmarks."""
from __future__ import annotations
import argparse, hashlib, json, os, sys, tempfile
from pathlib import Path
from typing import Any
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.model_training.twin_geometry.parametric_body import reconstruct_mesh, export_mesh_only_glb
from tools.model_evaluation.fashion_retrieval.data_rights import load_and_validate_data_rights_manifest
from tools.model_evaluation.fashion_retrieval.private_artifacts import write_private_text

SHA256_LENGTH=64

def validate_capture(capture:Any,rights_path:Path,model:dict[str,np.ndarray])->list[dict[str,Any]]:
    if not isinstance(capture,dict) or capture.get("schema_version")!="1.0":
        raise ValueError("capture schema_version must be 1.0")
    for key in ("capture_id","capture_protocol_id","camera_calibration_evidence_ref"):
        if not isinstance(capture.get(key),str) or not capture[key].strip():
            raise ValueError(f"{key} is required")
    if capture.get("face_masked_before_inference") is not True:
        raise ValueError("face masking must precede keypoint and silhouette inference")
    preprocessing_digest=capture.get("preprocessing_manifest_sha256")
    if not isinstance(preprocessing_digest,str) or len(preprocessing_digest)!=SHA256_LENGTH or any(c not in "0123456789abcdef" for c in preprocessing_digest):
        raise ValueError("preprocessing manifest digest is invalid")
    for model_key in ("keypoint_model","silhouette_model"):
        model_ref=capture.get(model_key)
        if not isinstance(model_ref,dict) or not isinstance(model_ref.get("model_id"),str) or not model_ref["model_id"].strip():
            raise ValueError(f"{model_key} provenance is required")
        revision=model_ref.get("source_revision")
        weights=model_ref.get("weights_sha256")
        if not isinstance(revision,str) or len(revision)!=40 or any(c not in "0123456789abcdef" for c in revision):
            raise ValueError(f"{model_key} source revision must be pinned to a full commit SHA")
        if not isinstance(weights,str) or len(weights)!=64 or any(c not in "0123456789abcdef" for c in weights):
            raise ValueError(f"{model_key} weights digest is invalid")
    views=capture.get("views")
    if not isinstance(views,list) or len(views)<2:
        raise ValueError("at least two calibrated views are required for this reconstruction mode")
    rights=load_and_validate_data_rights_manifest(rights_path,expected_scope="twin_geometry_inference")
    if rights.get("contains_personal_images") is not True or rights.get("depicted_person_consent_status")!="verified":
        raise ValueError("photo-based Twin inference requires verified subject consent")
    if capture.get("rights_manifest_sha256")!=rights["manifest_sha256"]:
        raise ValueError("capture rights manifest digest mismatch")
    landmark_names=[str(name) for name in model["landmark_names"].tolist()]
    seen=set()
    validated=[]
    for index,view in enumerate(views):
        if not isinstance(view,dict): raise ValueError(f"view {index} must be an object")
        view_id=view.get("view_id")
        if not isinstance(view_id,str) or not view_id.strip() or view_id in seen:
            raise ValueError("view IDs must be non-empty and unique")
        seen.add(view_id)
        digest=view.get("image_sha256")
        if not isinstance(digest,str) or len(digest)!=SHA256_LENGTH or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"view {view_id} image_sha256 is invalid")
        width,height=view.get("image_width"),view.get("image_height")
        if not isinstance(width,int) or not isinstance(height,int) or min(width,height)<256:
            raise ValueError(f"view {view_id} dimensions are invalid")
        camera=np.asarray(view.get("camera_matrix"),dtype=np.float64)
        if camera.shape!=(3,4) or not np.isfinite(camera).all() or np.linalg.matrix_rank(camera)<3:
            raise ValueError(f"view {view_id} camera matrix must be a finite rank-3 3x4 projection")
        silhouette_digest=view.get("silhouette_mask_sha256")
        if not isinstance(silhouette_digest,str) or len(silhouette_digest)!=SHA256_LENGTH or any(c not in "0123456789abcdef" for c in silhouette_digest):
            raise ValueError(f"view {view_id} silhouette mask digest is invalid")
        silhouette_bbox=view.get("silhouette_bbox")
        if not isinstance(silhouette_bbox,list) or len(silhouette_bbox)!=4:
            raise ValueError(f"view {view_id} requires a normalized silhouette bounding box")
        sx1,sy1,sx2,sy2=(float(v) for v in silhouette_bbox)
        if not np.isfinite([sx1,sy1,sx2,sy2]).all() or not 0<=sx1<sx2<=1 or not 0<=sy1<sy2<=1:
            raise ValueError(f"view {view_id} silhouette bounding box is invalid")
        silhouette_confidence=float(view.get("silhouette_confidence",0))
        if not np.isfinite(silhouette_confidence) or not 0<silhouette_confidence<=1:
            raise ValueError(f"view {view_id} silhouette confidence is invalid")
        points=view.get("keypoints")
        if not isinstance(points,dict) or not set(landmark_names).issubset(points):
            raise ValueError(f"view {view_id} is missing required body keypoints")
        normalized={}
        for name in landmark_names:
            value=points[name]
            if not isinstance(value,list) or len(value)!=3:
                raise ValueError(f"view {view_id} keypoint {name} must be [x,y,confidence]")
            x,y,confidence=(float(v) for v in value)
            if not np.isfinite([x,y,confidence]).all() or not 0<=x<=1 or not 0<=y<=1 or not 0<=confidence<=1:
                raise ValueError(f"view {view_id} keypoint {name} is outside normalized bounds")
            normalized[name]=(x,y,confidence)
        validated.append({"view_id":view_id,"image_sha256":digest,"image_width":width,"image_height":height,"camera_matrix":camera,"keypoints":normalized,"silhouette_mask_sha256":silhouette_digest,"silhouette_bbox":(sx1,sy1,sx2,sy2),"silhouette_confidence":silhouette_confidence})
    return validated

def project_landmarks(vertices:np.ndarray,indices:np.ndarray,views:list[dict[str,Any]],landmark_names:list[str])->np.ndarray:
    points=vertices[indices]
    residuals=[]
    homogeneous=np.column_stack([vertices,np.ones(len(vertices))])
    for view in views:
        camera=view["camera_matrix"]
        for name,index in zip(landmark_names,range(len(indices))):
            point=np.append(points[index],1.0)
            projected=camera@point
            if abs(projected[2])<1e-8: raise ValueError("camera projection produced a point at infinity")
            x=projected[0]/projected[2]/view["image_width"]
            y=projected[1]/projected[2]/view["image_height"]
            observed_x,observed_y,confidence=view["keypoints"][name]
            scale=np.sqrt(confidence)
            residuals.extend([(x-observed_x)*view["image_width"]*scale,(y-observed_y)*view["image_height"]*scale])
        projected_mesh=(camera@homogeneous.T).T
        if np.any(np.abs(projected_mesh[:,2])<1e-8): raise ValueError("silhouette projection produced a point at infinity")
        normalized_x=projected_mesh[:,0]/projected_mesh[:,2]/view["image_width"]
        normalized_y=projected_mesh[:,1]/projected_mesh[:,2]/view["image_height"]
        predicted_bbox=(normalized_x.min(),normalized_y.min(),normalized_x.max(),normalized_y.max())
        silhouette_scale=np.sqrt(view["silhouette_confidence"])
        residuals.extend([(predicted-observed)*view["image_width"]*silhouette_scale if index in (0,2) else (predicted-observed)*view["image_height"]*silhouette_scale for index,(predicted,observed) in enumerate(zip(predicted_bbox,view["silhouette_bbox"]))])
    return np.asarray(residuals,dtype=np.float64)

def fit_coefficients(mean:np.ndarray,basis:np.ndarray,coefficient_std:np.ndarray,faces:np.ndarray,landmark_indices:np.ndarray,landmark_names:list[str],views:list[dict[str,Any]],*,prior_strength:float=0.15,max_iterations:int=100)->dict[str,Any]:
    if prior_strength<0 or max_iterations<1: raise ValueError("invalid optimizer configuration")
    count=len(basis)
    if coefficient_std.shape!=(count,) or np.any(coefficient_std<=0): raise ValueError("coefficient standard deviations are invalid")
    coeff=np.zeros(count,dtype=np.float64)
    damping=1e-2
    def residual(value):
        vertices,_=reconstruct_mesh(mean,basis,value,faces)
        image_error=project_landmarks(vertices,landmark_indices,views,landmark_names)
        prior=(value/coefficient_std)*prior_strength
        return np.concatenate([image_error,prior])
    current=residual(coeff)
    for iteration in range(max_iterations):
        jacobian=np.empty((len(current),count),dtype=np.float64)
        for column in range(count):
            step=max(1e-3,coefficient_std[column]*1e-4)
            shifted=coeff.copy(); shifted[column]+=step
            jacobian[:,column]=(residual(shifted)-current)/step
        normal=jacobian.T@jacobian+damping*np.eye(count)
        gradient=jacobian.T@current
        try: delta=np.linalg.solve(normal,-gradient)
        except np.linalg.LinAlgError as exc: raise RuntimeError("shape fitting normal matrix is singular") from exc
        candidate=np.clip(coeff+delta,-3*coefficient_std,3*coefficient_std)
        candidate_residual=residual(candidate)
        if float(candidate_residual@candidate_residual)<float(current@current):
            coeff=candidate; current=candidate_residual; damping=max(damping*0.5,1e-7)
            if np.linalg.norm(delta)<1e-5: break
        else:
            damping=min(damping*4,1e8)
    vertices,_=reconstruct_mesh(mean,basis,coeff,faces)
    image_residual=project_landmarks(vertices,landmark_indices,views,landmark_names)
    rms=float(np.sqrt(np.mean(image_residual**2)))
    return {"coefficients":coeff,"vertices":vertices,"iterations":iteration+1,"reprojection_rmse_pixels":rms,"objective":float(current@current)}

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model",required=True,type=Path)
    parser.add_argument("--capture",required=True,type=Path)
    parser.add_argument("--rights-manifest",required=True,type=Path)
    parser.add_argument("--output-dir",required=True,type=Path)
    parser.add_argument("--prior-strength",type=float,default=0.15)
    parser.add_argument("--max-iterations",type=int,default=100)
    args=parser.parse_args()
    with np.load(args.model,allow_pickle=False) as archive:
        model={key:np.asarray(archive[key]) for key in archive.files}
    required={"mean_vertices","shape_basis","coefficient_std","faces","measurement_calibration","measurement_names","landmark_names","landmark_vertex_indices"}
    if not required.issubset(model): raise ValueError("shape model artifact is missing required arrays")
    capture=json.loads(args.capture.read_text(encoding="utf-8"))
    views=validate_capture(capture,args.rights_manifest,model)
    result=fit_coefficients(
        model["mean_vertices"],model["shape_basis"],model["coefficient_std"],model["faces"],
        model["landmark_vertex_indices"].astype(np.int64),model["landmark_names"].astype(str).tolist(),views,
        prior_strength=args.prior_strength,max_iterations=args.max_iterations
    )
    feature=np.concatenate(([1.0],result["coefficients"]))
    measurement_predictions=feature@model["measurement_calibration"]
    measurements={str(name):round(float(value),3) for name,value in zip(model["measurement_names"].tolist(),measurement_predictions)}
    args.output_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name=="posix" and args.output_dir.stat().st_mode&0o077: raise PermissionError("output directory must be owner-only (0700)")
    mesh_path=args.output_dir/"twin-geometry-candidate.npz"
    if mesh_path.exists() or mesh_path.is_symlink(): raise FileExistsError("refusing to overwrite Twin geometry asset")
    fd,temp_name=tempfile.mkstemp(prefix=".twin-geometry-",suffix=".tmp",dir=args.output_dir)
    temp=Path(temp_name)
    try:
        with os.fdopen(fd,"wb") as stream:
            np.savez_compressed(stream,vertices=result["vertices"],faces=model["faces"])
            stream.flush(); os.fsync(stream.fileno())
        os.link(temp,mesh_path); temp.unlink()
        if os.name=="posix": os.chmod(mesh_path,0o600)
    except Exception:
        temp.unlink(missing_ok=True); raise
    digest=hashlib.sha256(mesh_path.read_bytes()).hexdigest()
    glb_bytes,mesh_quality=export_mesh_only_glb(result["vertices"],model["faces"])
    glb_path=args.output_dir/"twin-geometry-candidate.glb"
    if glb_path.exists() or glb_path.is_symlink(): raise FileExistsError("refusing to overwrite Twin GLB asset")
    glb_fd,glb_temp_name=tempfile.mkstemp(prefix=".twin-glb-",suffix=".tmp",dir=args.output_dir)
    glb_temp=Path(glb_temp_name)
    try:
        with os.fdopen(glb_fd,"wb") as stream:
            stream.write(glb_bytes); stream.flush(); os.fsync(stream.fileno())
        os.link(glb_temp,glb_path); glb_temp.unlink()
        if os.name=="posix": os.chmod(glb_path,0o600)
    except Exception:
        glb_temp.unlink(missing_ok=True); raise
    glb_digest=hashlib.sha256(glb_bytes).hexdigest()
    report={
        "schema_version":"1.0","capture_id":capture["capture_id"],"model_id":"cirvanna-parametric-body-shape-v0",
        "geometry_asset_sha256":digest,"glb_asset_sha256":glb_digest,"mesh_quality":mesh_quality,"shape_coefficients":result["coefficients"].tolist(),
        "measurement_estimates_mm":measurements,"optimizer":{"iterations":result["iterations"],"reprojection_rmse_pixels":result["reprojection_rmse_pixels"],"objective":result["objective"]},
        "input_view_count":len(views),"input_image_sha256":[view["image_sha256"] for view in views],
        "status":"multi_view_geometry_candidate_not_a_validated_virtual_twin",
        "limitations":["Uses supplied 2D landmarks; it does not detect landmarks from raw photographs.","Requires calibrated multi-view capture and canonical pose; arbitrary single photographs are unsupported.","No dense silhouette or garment/appearance reconstruction is performed.","Measurement estimates inherit the scan cohort's calibration uncertainty and are not approved for fit or sizing.","This candidate is not yet persisted in the Twin Registry."]
    }
    write_private_text(args.output_dir/"capture-fit-report.json",json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":report["status"],"geometry_asset_sha256":digest,"glb_asset_sha256":glb_digest,"output_dir":str(args.output_dir)}))
    return 0

if __name__=="__main__": raise SystemExit(main())
