#!/usr/bin/env python3
"""Independently evaluate a frozen Cirvanna parametric Twin model on held-out scans."""
from __future__ import annotations
import argparse, hashlib, json, sys
from collections import defaultdict
from pathlib import Path
from typing import Any
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.model_training.provenance import require_clean_source_revision
from tools.model_training.twin_geometry.validate_dataset import validate_dataset,safe_mesh_path,topology_digest
from tools.model_training.twin_geometry.parametric_body import reconstruct_mesh
from tools.model_training.twin_geometry.metrics import MEASUREMENTS,measurement_accuracy_gate
from tools.model_evaluation.fashion_retrieval.private_artifacts import write_private_text

MODEL_ID="cirvanna-parametric-body-shape-v0"
ARCHITECTURE="registered-mesh-pca-plus-ridge-anthropometry-calibration"

def digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def measurement_metrics(actual:np.ndarray,predicted:np.ndarray)->dict[str,float]:
    actual=np.asarray(actual,dtype=np.float64); predicted=np.asarray(predicted,dtype=np.float64)
    if actual.shape!=predicted.shape or actual.ndim!=1 or len(actual)==0 or not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("measurement vectors must be non-empty, finite and shape-matched")
    error=predicted-actual; absolute=np.abs(error)
    return {
        "sample_count":int(len(actual)),
        "mae_mm":float(absolute.mean()),
        "median_absolute_error_mm":float(np.median(absolute)),
        "p95_absolute_error_mm":float(np.percentile(absolute,95)),
        "bias_mm":float(error.mean()),
        "mape_percent":float((absolute/np.maximum(np.abs(actual),1e-6)).mean()*100),
    }

def surface_metrics(actual:np.ndarray,predicted:np.ndarray)->dict[str,float]:
    actual=np.asarray(actual,dtype=np.float64); predicted=np.asarray(predicted,dtype=np.float64)
    if actual.shape!=predicted.shape or actual.ndim!=2 or actual.shape[1]!=3 or not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("registered mesh vertices must be finite and have identical Nx3 topology")
    errors=np.linalg.norm(predicted-actual,axis=1)
    return {"mean_vertex_error_mm":float(errors.mean()),"median_vertex_error_mm":float(np.median(errors)),"p95_vertex_error_mm":float(np.percentile(errors,95)),"max_vertex_error_mm":float(errors.max())}

def mean_dict(rows:list[dict[str,float]])->dict[str,float]:
    if not rows: raise ValueError("held-out evaluation split is empty")
    return {key:sum(float(row[key]) for row in rows)/len(rows) for key in rows[0]}

def run(args)->dict[str,Any]:
    source_revision=require_clean_source_revision(ROOT)
    dataset=validate_dataset(args.manifest,args.annotations,args.mesh_root,args.rights_manifest)
    manifest_sha=digest(args.manifest)
    training=json.loads(args.training_report.read_text(encoding="utf-8"))
    if training.get("model_id")!=MODEL_ID or training.get("architecture")!=ARCHITECTURE:
        raise ValueError("training report does not describe the Cirvanna parametric Twin model")
    if training.get("source_revision")!=source_revision:
        raise ValueError("evaluation source revision must exactly match the training source revision")
    if training.get("artifact_sha256")!=digest(args.model):
        raise ValueError("shape model artifact digest does not match training report")
    trained_dataset=training.get("dataset",{})
    if trained_dataset.get("dataset_manifest_sha256")!=manifest_sha:
        raise ValueError("training report dataset manifest digest mismatch")
    for key in ("annotations_sha256","split_manifest_sha256","rights_manifest_sha256"):
        if trained_dataset.get(key)!=dataset.get(key):
            raise ValueError(f"training report dataset provenance mismatch: {key}")
    held_out=training.get("held_out_test",{})
    if held_out.get("status")!="reserved_for_independent_evaluation":
        raise ValueError("training report must leave the held-out test split for independent evaluation")
    rows=[json.loads(line) for line in args.annotations.read_text(encoding="utf-8").splitlines() if line.strip()]
    test_rows=[row for row in rows if row["split"]=="test"]
    held_out_count=held_out.get("sample_count")
    if isinstance(held_out_count,bool) or not isinstance(held_out_count,int) or held_out_count<1 or len(test_rows)!=held_out_count:
        raise ValueError("training report held-out sample count differs from the frozen test split")
    with np.load(args.model,allow_pickle=False) as archive:
        model={key:np.asarray(archive[key]) for key in archive.files}
    required={"mean_vertices","shape_basis","coefficient_std","faces","measurement_calibration","measurement_names"}
    if not required.issubset(model): raise ValueError("shape model artifact is missing required arrays")
    mean=model["mean_vertices"].astype(np.float64)
    basis=model["shape_basis"].astype(np.float64)
    std=model["coefficient_std"].astype(np.float64)
    faces=model["faces"].astype(np.int64)
    calibration=model["measurement_calibration"].astype(np.float64)
    names=[str(value) for value in model["measurement_names"].tolist()]
    if names!=list(MEASUREMENTS):
        raise ValueError("shape model measurement schema does not match the canonical anthropometry protocol")
    if mean.ndim!=2 or mean.shape[1]!=3 or basis.ndim!=3 or basis.shape[1:]!=mean.shape or std.shape!=(len(basis),) or calibration.shape!=(len(basis)+1,len(names)):
        raise ValueError("shape model array dimensions are inconsistent")
    if faces.ndim!=2 or faces.shape[1]!=3 or len(faces)<4 or np.any(faces<0) or np.any(faces>=len(mean)):
        raise ValueError("shape model face topology is invalid")
    if "landmark_vertex_indices" not in model:
        raise ValueError("shape model artifact is missing its anatomical landmark map")
    landmark_indices=np.asarray(model["landmark_vertex_indices"],dtype=np.int64)
    expected_landmarks=dataset.get("landmark_vertex_indices",{})
    expected_names=list(expected_landmarks)
    if "landmark_names" not in model or landmark_indices.shape!=(7,) or np.any(landmark_indices<0) or np.any(landmark_indices>=len(mean)) or len(np.unique(landmark_indices))!=7:
        raise ValueError("shape model anatomical landmark map is invalid")
    landmark_names=[str(value) for value in model["landmark_names"].tolist()]
    if landmark_names!=expected_names or landmark_indices.tolist()!=[expected_landmarks[name] for name in expected_names]:
        raise ValueError("shape model anatomical landmark map differs from the approved dataset manifest")
    if topology_digest(faces,len(mean))!=dataset.get("topology_sha256"):
        raise ValueError("shape model topology differs from the validated dataset topology")
    if not np.isfinite(mean).all() or not np.isfinite(basis).all() or not np.isfinite(std).all() or np.any(std<=0) or not np.isfinite(calibration).all():
        raise ValueError("shape model arrays must be finite with positive coefficient scales")
    surface_rows=[]; measurement_rows=defaultdict(list); subgroup_rows=defaultdict(list); topology_valid=0
    for row in test_rows:
        mesh_path=safe_mesh_path(args.mesh_root,row["mesh_path"])
        if digest(mesh_path)!=row["mesh_sha256"]: raise ValueError("test mesh changed after dataset validation")
        with np.load(mesh_path,allow_pickle=False) as archive:
            vertices=np.asarray(archive["vertices"],dtype=np.float64)
            test_faces=np.asarray(archive["faces"],dtype=np.int64)
        if vertices.shape!=mean.shape or not np.array_equal(test_faces,faces):
            raise ValueError("test scan topology differs from frozen shape basis")
        if not np.isfinite(vertices).all():
            raise ValueError("held-out scan contains non-finite vertices")
        coefficients=(vertices-mean).reshape(-1)@basis.reshape(len(basis),-1).T
        coefficients=np.clip(coefficients,-3*std,3*std)
        reconstructed,_=reconstruct_mesh(mean,basis,coefficients,faces)
        surface=surface_metrics(vertices,reconstructed); surface_rows.append(surface)
        feature=np.concatenate(([1.0],coefficients))
        predictions=feature@calibration
        actual=np.asarray([float(row["measurements_mm"][name]) for name in names],dtype=np.float64)
        for index,name in enumerate(names):
            measurement_rows[name].append((actual[index],predictions[index]))
        try:
            import trimesh
            mesh=trimesh.Trimesh(vertices=reconstructed,faces=faces,process=False)
            topology_valid+=int(bool(mesh.is_watertight and mesh.is_winding_consistent))
        except Exception:
            pass
        for key,value in row.get("subgroups",{}).items():
            subgroup_rows[f"{key}={value}"].append((surface,actual,predictions))
    measurement_summary={}
    for name,values in measurement_rows.items():
        actual=np.asarray([value[0] for value in values],dtype=np.float64)
        predicted=np.asarray([value[1] for value in values],dtype=np.float64)
        measurement_summary[name]=measurement_metrics(actual,predicted)
    subgroups={}
    for key,values in sorted(subgroup_rows.items()):
        actual=np.stack([item[1] for item in values]); predicted=np.stack([item[2] for item in values])
        subgroups[key]={
            "sample_count":len(values),
            "surface":mean_dict([item[0] for item in values]),
            "measurements":{name:measurement_metrics(actual[:,i],predicted[:,i]) for i,name in enumerate(names)}
        }
    return {
        "schema_version":"1.0","task":"independent_twin_geometry_held_out_evaluation",
        "model_id":MODEL_ID,"architecture":ARCHITECTURE,"source_revision":source_revision,
        "model_artifact_sha256":digest(args.model),"training_report_sha256":digest(args.training_report),
        "dataset_manifest_sha256":manifest_sha,"annotations_sha256":dataset["annotations_sha256"],
        "split_manifest_sha256":dataset["split_manifest_sha256"],"rights_manifest_sha256":dataset["rights_manifest_sha256"],
        "sample_count":len(test_rows),"subject_cluster_count":len({row["subject_cluster_id"] for row in test_rows}),
        "surface":mean_dict(surface_rows),"measurements":measurement_summary,
        "held_out_measurement_accuracy_gate":measurement_accuracy_gate({"measurements":measurement_summary}),
        "structural_mesh_validity":{"watertight_and_winding_consistent":topology_valid,"sample_count":len(test_rows),"ratio":topology_valid/len(test_rows)},
        "subgroups":subgroups,
        "status":"independent_held_out_geometry_evaluation_not_qualified",
        "limitations":[
            "This evaluates registered 3D scans projected into a PCA basis; it does not measure photo-to-3D reconstruction accuracy.",
            "The measurement regressor is cohort- and protocol-specific; subgroup means are descriptive and lack cluster-bootstrap confidence intervals.",
            "Structural watertightness is not anatomical validation. Independent clinical/anatomical review and repeat-capture measurement calibration remain required.",
            "No persistent Twin Registry write, renderer qualification or user-facing fit/sizing claim is authorized."
        ]
    }

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model",required=True,type=Path)
    parser.add_argument("--training-report",required=True,type=Path)
    parser.add_argument("--manifest",required=True,type=Path)
    parser.add_argument("--annotations",required=True,type=Path)
    parser.add_argument("--mesh-root",required=True,type=Path)
    parser.add_argument("--rights-manifest",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--overwrite",action="store_true")
    args=parser.parse_args()
    report=run(args)
    write_private_text(args.output,json.dumps(report,indent=2,sort_keys=True)+"\n",overwrite=args.overwrite)
    print(json.dumps({"status":report["status"],"sample_count":report["sample_count"],"surface":report["surface"],"measurements":report["measurements"]}))
    return 0
if __name__=="__main__": raise SystemExit(main())
