#!/usr/bin/env python3
"""Fit a Cirvanna parametric body shape basis and tape-measure calibration from registered scans."""
from __future__ import annotations
import argparse, hashlib, json, os, sys, tempfile
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.model_training.twin_geometry.validate_dataset import validate_dataset,safe_mesh_path
from tools.model_training.twin_geometry.parametric_body import reconstruct_mesh
from tools.model_evaluation.fashion_retrieval.private_artifacts import write_private_text
from tools.model_training.provenance import require_clean_source_revision

MEASUREMENTS=("height_mm","chest_circumference_mm","waist_circumference_mm","hip_circumference_mm","inseam_mm")

def load_mesh(path:Path):
    with np.load(path,allow_pickle=False) as archive:
        return np.asarray(archive["vertices"],dtype=np.float64),np.asarray(archive["faces"],dtype=np.int64)

def fit_shape_basis(train_vertices:list[np.ndarray],components:int):
    if len(train_vertices)<2: raise ValueError("at least two registered training scans are required")
    shape=train_vertices[0].shape
    if any(vertices.shape!=shape for vertices in train_vertices): raise ValueError("all training meshes must share vertex dimensions")
    matrix=np.stack([vertices.reshape(-1) for vertices in train_vertices])
    mean=matrix.mean(axis=0)
    centered=matrix-mean
    gram=(centered@centered.T)/max(1,len(matrix)-1)
    eigenvalues,eigenvectors=np.linalg.eigh(gram)
    order=np.argsort(eigenvalues)[::-1]
    eigenvalues=eigenvalues[order]
    eigenvectors=eigenvectors[:,order]
    valid=np.where(eigenvalues>1e-10)[0]
    count=min(components,len(valid),len(train_vertices)-1)
    if count<1: raise ValueError("training scans have no non-zero shape variation")
    selected=eigenvalues[:count]
    basis=(eigenvectors[:,:count].T@centered)/np.sqrt((len(matrix)-1)*selected[:,None])
    explained=selected/max(float(eigenvalues[valid].sum()),1e-12)
    return mean.reshape(shape),basis.reshape((count,*shape)),explained

def ridge_fit(features:np.ndarray,targets:np.ndarray,alpha:float):
    regularizer=np.eye(features.shape[1])*alpha
    regularizer[0,0]=0.0
    return np.linalg.solve(features.T@features+regularizer,features.T@targets)

def metric_summary(actual:np.ndarray,predicted:np.ndarray)->dict[str,float]:
    error=predicted-actual
    absolute=np.abs(error)
    return {
        "sample_count":int(len(actual)),
        "mae_mm":round(float(absolute.mean()),4),
        "median_absolute_error_mm":round(float(np.median(absolute)),4),
        "p95_absolute_error_mm":round(float(np.percentile(absolute,95)),4),
        "bias_mm":round(float(error.mean()),4),
        "mape_percent":round(float((absolute/np.maximum(actual,1e-6)).mean()*100),4),
    }

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",required=True,type=Path)
    parser.add_argument("--annotations",required=True,type=Path)
    parser.add_argument("--mesh-root",required=True,type=Path)
    parser.add_argument("--rights-manifest",required=True,type=Path)
    parser.add_argument("--output-dir",required=True,type=Path)
    parser.add_argument("--components",type=int,default=20)
    parser.add_argument("--ridge-alpha",type=float,default=1.0)
    args=parser.parse_args()
    if args.components<1 or args.ridge_alpha<0: raise ValueError("invalid shape model configuration")
    source_revision=require_clean_source_revision(ROOT)
    dataset=validate_dataset(args.manifest,args.annotations,args.mesh_root,args.rights_manifest)
    dataset["dataset_manifest_sha256"]=hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    rows=[json.loads(line) for line in args.annotations.read_text(encoding="utf-8").splitlines() if line.strip()]
    train=[row for row in rows if row["split"]=="train"]
    validation=[row for row in rows if row["split"]=="validation"]
    test_rows=[row for row in rows if row["split"]=="test"]
    train_vertices=[]; train_faces=[]
    for row in train:
        vertices,faces=load_mesh(safe_mesh_path(args.mesh_root,row["mesh_path"]))
        train_vertices.append(vertices); train_faces.append(faces)
    mean,basis,explained=fit_shape_basis(train_vertices,args.components)
    def project(row):
        vertices,_=load_mesh(safe_mesh_path(args.mesh_root,row["mesh_path"]))
        coeff=(vertices-mean).reshape(-1)@basis.reshape(len(basis),-1).T
        return coeff,vertices
    train_features=[]; train_targets=[]
    for row in train:
        coeff,_=project(row); train_features.append(np.concatenate(([1.0],coeff)))
        train_targets.append([float(row["measurements_mm"][name]) for name in MEASUREMENTS])
    train_features=np.asarray(train_features); train_targets=np.asarray(train_targets)
    calibration=ridge_fit(train_features,train_targets,args.ridge_alpha)
    coefficient_std=np.std(train_features[:,1:],axis=0)
    coefficient_std=np.maximum(coefficient_std,1e-6)
    manifest_value=json.loads(args.manifest.read_text(encoding="utf-8"))
    landmark_vertex_indices=manifest_value["landmark_vertex_indices"]
    def evaluate_split(split_rows):
        errors=[]; actual=[]; predicted=[]
        for row in split_rows:
            coeff,vertices=project(row)
            reconstructed,_=reconstruct_mesh(mean,basis,coeff,train_faces[0])
            errors.append(np.linalg.norm(reconstructed-vertices,axis=1))
            actual.append([float(row["measurements_mm"][name]) for name in MEASUREMENTS])
            predicted.append(np.concatenate(([1.0],coeff))@calibration)
        error_matrix=np.concatenate(errors)
        actual=np.asarray(actual); predicted=np.asarray(predicted)
        return {
            "surface_vertex_error_mm":{"mean":round(float(error_matrix.mean()),4),"p95":round(float(np.percentile(error_matrix,95)),4),"max":round(float(error_matrix.max()),4)},
            "measurements":{name:metric_summary(actual[:,i],predicted[:,i]) for i,name in enumerate(MEASUREMENTS)}
        }
    validation_report=evaluate_split(validation)
    # The held-out test split is sealed for the independent evaluator.
    args.output_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name=="posix" and args.output_dir.stat().st_mode&0o077: raise PermissionError("training output directory must be owner-only (0700)")
    artifact=args.output_dir/"cvi-parametric-body-model.npz"
    if artifact.exists() or artifact.is_symlink(): raise FileExistsError("refusing to overwrite existing shape model")
    fd,temp_name=tempfile.mkstemp(prefix=".cvi-body-model-",suffix=".tmp",dir=args.output_dir)
    temp=Path(temp_name)
    try:
        with os.fdopen(fd,"wb") as stream:
            np.savez_compressed(stream,mean_vertices=mean,shape_basis=basis,explained_variance_ratio=explained,coefficient_std=coefficient_std,faces=train_faces[0],measurement_calibration=calibration,measurement_names=np.asarray(MEASUREMENTS),landmark_names=np.asarray(list(landmark_vertex_indices)),landmark_vertex_indices=np.asarray(list(landmark_vertex_indices.values()),dtype=np.int64))
            stream.flush(); os.fsync(stream.fileno())
        os.link(temp,artifact); temp.unlink()
        if os.name=="posix": os.chmod(artifact,0o600)
    except Exception:
        temp.unlink(missing_ok=True); raise
    digest=hashlib.sha256(artifact.read_bytes()).hexdigest()
    report={
        "schema_version":"1.0","model_id":"cirvanna-parametric-body-shape-v0",
        "architecture":"registered-mesh-pca-plus-ridge-anthropometry-calibration",
        "initialization":"fit_from_consent-governed_registered_3d_scans",
        "source_revision":source_revision,"artifact_sha256":digest,"dataset":dataset,
        "configuration":{"components":len(basis),"requested_components":args.components,"ridge_alpha":args.ridge_alpha,"measurement_names":MEASUREMENTS},
        "explained_variance_ratio":explained.tolist(),
        "validation":validation_report,"held_out_test":{"status":"reserved_for_independent_evaluation","sample_count":len(test_rows)},
        "status":"research_geometry_basis_not_a_photo_reconstruction_model",
        "limitations":["Requires registered scans with identical topology and calibrated millimetre scale.","Does not infer shape coefficients from photographs.","Surface reconstruction errors are on registered scans, not independent anatomical validation.","Tape-measure regression is cohort-specific and must be independently calibrated and subgroup-validated.","No persistent Twin rendering, identity consistency or privacy release gate is qualified."]
    }
    write_private_text(args.output_dir/"training-report.json",json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":report["status"],"artifact_sha256":digest,"components":len(basis),"held_out_test":"reserved_for_independent_evaluation","output_dir":str(args.output_dir)}))
    return 0

if __name__=="__main__": raise SystemExit(main())
