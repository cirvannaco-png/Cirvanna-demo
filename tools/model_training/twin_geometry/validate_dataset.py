#!/usr/bin/env python3
"""Validate consented registered 3D body scans and anthropometry ground truth."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
from typing import Any
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.model_evaluation.fashion_retrieval.data_rights import load_and_validate_data_rights_manifest

SHA256=re.compile(r"^[0-9a-f]{64}$")
REQUIRED_SPLITS={"train","validation","test"}
REQUIRED_LANDMARKS={"head_top","left_shoulder","right_shoulder","left_hip","right_hip","left_ankle","right_ankle"}
REQUIRED_MEASUREMENTS={"height_mm","chest_circumference_mm","waist_circumference_mm","hip_circumference_mm","inseam_mm"}
MEASUREMENT_RANGES={"height_mm":(500,2500),"chest_circumference_mm":(300,2000),"waist_circumference_mm":(300,2000),"hip_circumference_mm":(300,2000),"inseam_mm":(200,1500)}
MAX_MESH_BYTES=250*1024*1024
MAX_VERTICES=250_000
MAX_FACES=500_000

def sha256_file(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest()

def topology_digest(faces:np.ndarray,vertex_count:int)->str:
    canonical=np.ascontiguousarray(faces,dtype="<i8")
    digest=hashlib.sha256()
    digest.update(str(vertex_count).encode())
    digest.update(canonical.tobytes())
    return digest.hexdigest()

def safe_mesh_path(root:Path,relative:Any)->Path:
    if not isinstance(relative,str) or not relative.strip() or "\\" in relative:
        raise ValueError("mesh_path must be a non-empty POSIX relative path")
    candidate=Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("mesh_path traversal is forbidden")
    resolved_root=root.resolve()
    lexical=resolved_root
    for part in candidate.parts:
        lexical=lexical/part
        if lexical.is_symlink(): raise ValueError("symlink mesh paths are forbidden")
    resolved=lexical.resolve()
    if resolved_root not in resolved.parents or not resolved.is_file():
        raise ValueError("mesh_path must resolve to a regular file inside mesh root")
    if resolved.stat().st_size>MAX_MESH_BYTES: raise ValueError("mesh file exceeds byte limit")
    return resolved

def validate_sample(row:Any,line:int,alignment_protocol_id:str)->dict[str,Any]:
    if not isinstance(row,dict): raise ValueError(f"line {line}: sample must be an object")
    for key in ("sample_id","subject_cluster_id","split","mesh_path","mesh_sha256","alignment_protocol_id"):
        if not isinstance(row.get(key),str) or not row[key].strip(): raise ValueError(f"line {line}: {key} is required")
    if row["split"] not in REQUIRED_SPLITS: raise ValueError(f"line {line}: invalid split")
    if row["alignment_protocol_id"]!=alignment_protocol_id: raise ValueError(f"line {line}: alignment protocol mismatch")
    if not SHA256.fullmatch(row["mesh_sha256"]): raise ValueError(f"line {line}: mesh_sha256 must be lowercase SHA-256")
    landmarks=row.get("landmarks_mm")
    if not isinstance(landmarks,dict) or not REQUIRED_LANDMARKS.issubset(landmarks):
        raise ValueError(f"line {line}: required anatomical landmarks are missing")
    points={}
    for name in REQUIRED_LANDMARKS:
        point=landmarks[name]
        if not isinstance(point,list) or len(point)!=3:
            raise ValueError(f"line {line}: landmark {name} must be a 3D coordinate")
        coords=np.asarray(point,dtype=np.float64)
        if not np.isfinite(coords).all() or np.any(np.abs(coords)>3000):
            raise ValueError(f"line {line}: landmark {name} is outside the valid coordinate range")
        points[name]=coords
    if not (points["head_top"][1] > points["left_shoulder"][1] > points["left_hip"][1] > points["left_ankle"][1]
            and points["head_top"][1] > points["right_shoulder"][1] > points["right_hip"][1] > points["right_ankle"][1]):
        raise ValueError(f"line {line}: anatomical landmark vertical ordering is implausible")
    if abs(points["left_shoulder"][0]-points["right_shoulder"][0]) < 50 or abs(points["left_hip"][0]-points["right_hip"][0]) < 50:
        raise ValueError(f"line {line}: bilateral anatomical landmarks are implausibly close")
    measurements=row.get("measurements_mm")
    if not isinstance(measurements,dict) or not REQUIRED_MEASUREMENTS.issubset(measurements):
        raise ValueError(f"line {line}: required anthropometric measurements are missing")
    for name in REQUIRED_MEASUREMENTS:
        value=measurements[name]
        lower,upper=MEASUREMENT_RANGES[name]
        if not isinstance(value,(int,float)) or not np.isfinite(value) or not lower<=value<=upper:
            raise ValueError(f"line {line}: measurement {name} is outside the plausible millimetre range")
    if not isinstance(row.get("subgroups"),dict) or not row["subgroups"]:
        raise ValueError(f"line {line}: evaluation subgroup metadata is required")
    return row

def split_manifest_digest(rows:list[dict[str,Any]])->str:
    values=sorted(({"sample_id":r["sample_id"],"subject_cluster_id":r["subject_cluster_id"],"split":r["split"]} for r in rows),key=lambda r:r["sample_id"])
    return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def validate_dataset(manifest_path:Path,annotations_path:Path,mesh_root:Path,rights_path:Path)->dict[str,Any]:
    rights=load_and_validate_data_rights_manifest(rights_path,expected_scope="twin_geometry_training")
    if rights.get("contains_personal_images") is not True or rights.get("depicted_person_consent_status")!="verified":
        raise ValueError("3D body scans require verified subject consent")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest,dict) or manifest.get("schema_version")!="1.0": raise ValueError("dataset manifest schema_version must be 1.0")
    if manifest.get("units")!="millimetres" or manifest.get("coordinate_frame")!="right_handed_x_right_y_up_z_forward":
        raise ValueError("dataset must use canonical millimetre, y-up coordinate frame")
    alignment=manifest.get("alignment_protocol_id")
    measurement_protocol=manifest.get("measurement_protocol_id")
    if not isinstance(alignment,str) or not alignment.strip() or not isinstance(measurement_protocol,str) or not measurement_protocol.strip():
        raise ValueError("alignment and measurement protocol IDs are required")
    raw=annotations_path.read_bytes()
    annotations_digest=hashlib.sha256(raw).hexdigest()
    if manifest.get("annotations_sha256")!=annotations_digest: raise ValueError("annotation file digest mismatch")
    if manifest.get("rights_manifest_sha256")!=rights["manifest_sha256"]: raise ValueError("dataset rights manifest digest mismatch")
    rows=[]
    for line,value in enumerate(raw.decode("utf-8").splitlines(),1):
        if value.strip(): rows.append(validate_sample(json.loads(value),line,alignment))
    if not rows or manifest.get("sample_count")!=len(rows): raise ValueError("dataset sample_count mismatch or dataset empty")
    if len({r["sample_id"] for r in rows})!=len(rows): raise ValueError("sample_id values must be unique")
    if {r["split"] for r in rows}!=REQUIRED_SPLITS: raise ValueError("dataset must contain train, validation and test splits")
    clusters:dict[str,set[str]]={}
    mesh_digests:dict[str,int]={}
    topology=None
    vertex_count=None
    face_count=None
    for row in rows:
        clusters.setdefault(row["subject_cluster_id"],set()).add(row["split"])
        mesh_digests[row["mesh_sha256"]]=mesh_digests.get(row["mesh_sha256"],0)+1
        mesh_path=safe_mesh_path(mesh_root,row["mesh_path"])
        if sha256_file(mesh_path)!=row["mesh_sha256"]: raise ValueError(f"mesh digest mismatch for sample {row['sample_id']}")
        try:
            with np.load(mesh_path,allow_pickle=False) as archive:
                vertices=np.asarray(archive["vertices"],dtype=np.float64)
                faces=np.asarray(archive["faces"],dtype=np.int64)
        except Exception as exc:
            raise ValueError(f"invalid registered mesh archive for sample {row['sample_id']}") from exc
        if vertices.ndim!=2 or vertices.shape[1]!=3 or not 4<=len(vertices)<=MAX_VERTICES: raise ValueError("mesh vertices must have shape (N,3) within configured bounds")
        if faces.ndim!=2 or faces.shape[1]!=3 or not 4<=len(faces)<=MAX_FACES: raise ValueError("mesh faces must have shape (M,3) within configured bounds")
        if not np.isfinite(vertices).all() or np.any(np.abs(vertices)>3000): raise ValueError("mesh coordinates must be finite millimetres within bounds")
        if np.any(faces<0) or np.any(faces>=len(vertices)): raise ValueError("mesh face indices are out of bounds")
        if np.any((faces[:,0]==faces[:,1])|(faces[:,1]==faces[:,2])|(faces[:,0]==faces[:,2])): raise ValueError("mesh contains degenerate face indices")
        triangle=vertices[faces]
        areas=np.linalg.norm(np.cross(triangle[:,1]-triangle[:,0],triangle[:,2]-triangle[:,0]),axis=1)
        if np.any(areas<=1e-8): raise ValueError("mesh contains zero-area triangles")
        for point in row["landmarks_mm"].values():
            landmark=np.asarray(point,dtype=np.float64)
            if np.any(landmark < vertices.min(axis=0)-150) or np.any(landmark > vertices.max(axis=0)+150):
                raise ValueError(f"anatomical landmark lies outside mesh bounds for sample {row['sample_id']}")
        current=topology_digest(faces,len(vertices))
        if topology is None: topology=current; vertex_count=len(vertices); face_count=len(faces)
        elif current!=topology: raise ValueError("registered meshes do not share identical vertex topology")
    if any(len(v)!=1 for v in clusters.values()): raise ValueError("subject clusters leak across dataset splits")
    if any(count>1 for count in mesh_digests.values()): raise ValueError("duplicate mesh bytes must be deduplicated")
    if manifest.get("template_topology_sha256")!=topology: raise ValueError("template topology digest mismatch")
    split_digest=split_manifest_digest(rows)
    if manifest.get("split_manifest_sha256")!=split_digest: raise ValueError("split manifest digest mismatch")
    return {
        "dataset_id":manifest.get("dataset_id"),"sample_count":len(rows),
        "split_counts":{s:sum(r["split"]==s for r in rows) for s in sorted(REQUIRED_SPLITS)},
        "subject_cluster_count":len(clusters),"vertex_count":vertex_count,"face_count":face_count,
        "topology_sha256":topology,"alignment_protocol_id":alignment,
        "measurement_protocol_id":measurement_protocol,"annotations_sha256":annotations_digest,
        "split_manifest_sha256":split_digest,"rights_manifest_sha256":rights["manifest_sha256"],
        "rights_evidence_sha256":rights["evidence_sha256"],"status":"validated_for_shape_model_training_only"
    }

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",required=True,type=Path)
    parser.add_argument("--annotations",required=True,type=Path)
    parser.add_argument("--mesh-root",required=True,type=Path)
    parser.add_argument("--rights-manifest",required=True,type=Path)
    args=parser.parse_args()
    print(json.dumps(validate_dataset(args.manifest,args.annotations,args.mesh_root,args.rights_manifest),indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
