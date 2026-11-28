#!/usr/bin/env python3
"""Fuse face-masked, colour-calibrated multi-view photographs onto a fitted Twin mesh."""
from __future__ import annotations
import argparse, hashlib, json, os, tempfile
from pathlib import Path
from typing import Any
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0,str(ROOT))
from tools.model_evaluation.fashion_retrieval.data_rights import load_and_validate_data_rights_manifest
from tools.model_training.provenance import require_clean_source_revision

SHA256_LENGTH=64

def digest(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def safe_media_path(root:Path,value:Any)->Path:
    if not isinstance(value,str) or not value.strip() or "\\" in value: raise ValueError("appearance media path must be a POSIX relative path")
    relative=Path(value)
    if relative.is_absolute() or ".." in relative.parts: raise ValueError("appearance media path traversal is forbidden")
    base=root.resolve(); current=base
    for part in relative.parts:
        current=current/part
        if current.is_symlink(): raise ValueError("appearance media symlinks are forbidden")
    resolved=current.resolve()
    if base not in resolved.parents or not resolved.is_file(): raise ValueError("appearance media must be a regular file under media root")
    if resolved.stat().st_size>25*1024*1024: raise ValueError("appearance media exceeds byte limit")
    return resolved

def _load_image(path:Path,expected_digest:str,mask:bool)->np.ndarray:
    if digest(path)!=expected_digest: raise ValueError("appearance media digest mismatch")
    with Image.open(path) as image:
        if image.width*image.height>20_000_000: raise ValueError("appearance image exceeds pixel limit")
        if mask:
            if image.format!="PNG" or image.mode not in ("L","1"): raise ValueError("body and face masks must be grayscale PNGs")
            return np.asarray(image,dtype=np.uint8).copy()
        if image.format not in ("PNG","JPEG","WEBP"): raise ValueError("unsupported appearance image format")
        return np.asarray(image.convert("RGB"),dtype=np.uint8).copy()

def _camera_center(camera:np.ndarray)->np.ndarray:
    _,_,vh=np.linalg.svd(camera)
    center=vh[-1]
    if abs(center[3])<1e-10: raise ValueError("camera calibration does not define a finite camera center")
    return center[:3]/center[3]

def _project(vertices:np.ndarray,camera:np.ndarray)->tuple[np.ndarray,np.ndarray]:
    homogeneous=np.column_stack([vertices,np.ones(len(vertices))])
    projected=(camera@homogeneous.T).T
    depth=projected[:,2]
    xy=np.full((len(vertices),2),np.nan,dtype=np.float64)
    valid=depth>1e-8
    xy[valid]=projected[valid,:2]/depth[valid,None]
    return xy,depth

def _build_zbuffer(xy:np.ndarray,depth:np.ndarray,faces:np.ndarray,width:int,height:int)->np.ndarray:
    zbuffer=np.full((height,width),np.inf,dtype=np.float32)
    for face in faces:
        p=xy[face]
        z=depth[face]
        if not np.isfinite(p).all() or np.any(z<=0): continue
        x0=max(0,int(np.floor(p[:,0].min()))); x1=min(width-1,int(np.ceil(p[:,0].max())))
        y0=max(0,int(np.floor(p[:,1].min()))); y1=min(height-1,int(np.ceil(p[:,1].max())))
        if x1<x0 or y1<y0: continue
        a,b,c=p
        denominator=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(denominator)<1e-10: continue
        grid_x,grid_y=np.meshgrid(np.arange(x0,x1+1)+0.5,np.arange(y0,y1+1)+0.5)
        w0=((b[1]-c[1])*(grid_x-c[0])+(c[0]-b[0])*(grid_y-c[1]))/denominator
        w1=((c[1]-a[1])*(grid_x-c[0])+(a[0]-c[0])*(grid_y-c[1]))/denominator
        w2=1.0-w0-w1
        inside=(w0>=-1e-6)&(w1>=-1e-6)&(w2>=-1e-6)
        inverse_depth=w0/z[0]+w1/z[1]+w2/z[2]
        triangle_depth=np.divide(1.0,inverse_depth,out=np.full_like(inverse_depth,np.inf),where=inverse_depth>1e-10)
        region=zbuffer[y0:y1+1,x0:x1+1]
        region[inside]=np.minimum(region[inside],triangle_depth[inside].astype(np.float32))
    return zbuffer

def validate_appearance_capture(capture:dict[str,Any],rights_path:Path,geometry_path:Path,media_root:Path)->tuple[dict[str,Any],dict[str,Any]]:
    rights=load_and_validate_data_rights_manifest(rights_path,expected_scope="twin_appearance_inference")
    if rights.get("contains_personal_images") is not True or rights.get("depicted_person_consent_status")!="verified":
        raise ValueError("appearance reconstruction requires verified subject consent")
    if capture.get("rights_manifest_sha256")!=rights["manifest_sha256"]: raise ValueError("appearance rights manifest digest mismatch")
    if capture.get("face_masked_before_inference") is not True: raise ValueError("face masking must precede appearance reconstruction")
    preprocessing=capture.get("preprocessing_manifest_sha256")
    if not isinstance(preprocessing,str) or len(preprocessing)!=SHA256_LENGTH or any(c not in "0123456789abcdef" for c in preprocessing):
        raise ValueError("appearance preprocessing manifest digest is invalid")
    if not isinstance(capture.get("color_calibration_evidence_ref"),str) or not capture["color_calibration_evidence_ref"].strip():
        raise ValueError("colour calibration evidence reference is required")
    calibration_digest=capture.get("color_calibration_evidence_sha256")
    if not isinstance(calibration_digest,str) or len(calibration_digest)!=SHA256_LENGTH or any(c not in "0123456789abcdef" for c in calibration_digest):
        raise ValueError("colour calibration evidence digest is invalid")
    calibration_path=safe_media_path(media_root,capture.get("color_calibration_evidence_path"))
    if digest(calibration_path)!=calibration_digest: raise ValueError("colour calibration evidence digest mismatch")
    calibration=json.loads(calibration_path.read_text(encoding="utf-8"))
    if calibration.get("schema_version")!="1.0" or not isinstance(calibration.get("profiles"),dict):
        raise ValueError("colour calibration evidence schema is invalid")
    if capture.get("geometry_sha256")!=digest(geometry_path): raise ValueError("geometry asset digest mismatch")
    views=capture.get("views")
    if not isinstance(views,list) or len(views)<2: raise ValueError("at least two calibrated appearance views are required")
    checked=[]
    for view in views:
        camera=np.asarray(view.get("camera_matrix"),dtype=np.float64)
        if camera.shape!=(3,4) or not np.isfinite(camera).all() or np.linalg.matrix_rank(camera)<3:
            raise ValueError("appearance camera matrix must be finite, calibrated and rank 3")
        if int(view.get("image_width",0))<256 or int(view.get("image_height",0))<256:
            raise ValueError("appearance image dimensions are below minimum")
        matrix=np.asarray(view.get("color_calibration_matrix"),dtype=np.float64)
        gain=np.asarray(view.get("white_balance_gain"),dtype=np.float64)
        if matrix.shape!=(3,3) or gain.shape!=(3,) or not np.isfinite(matrix).all() or not np.isfinite(gain).all() or np.any(gain<0.1) or np.any(gain>4.0):
            raise ValueError("colour calibration matrix or white-balance gains are invalid")
        confidence=float(view.get("view_confidence",0))
        if not 0<confidence<=1: raise ValueError("appearance view confidence must be in (0,1]")
        profile=calibration["profiles"].get(str(view.get("view_id","")))
        if not isinstance(profile,dict) or not np.allclose(matrix,np.asarray(profile.get("color_calibration_matrix"),dtype=np.float64),atol=1e-9):
            raise ValueError("view colour matrix does not match the calibration evidence")
        if not np.allclose(gain,np.asarray(profile.get("white_balance_gain"),dtype=np.float64),atol=1e-9):
            raise ValueError("view white balance does not match the calibration evidence")
        loaded={}
        for role in ("image","body_mask","face_mask"):
            path=safe_media_path(media_root,view.get(f"{role}_path"))
            loaded[role]=_load_image(path,view.get(f"{role}_sha256",""),mask=role!="image")
        if loaded["image"].shape[:2]!=(int(view["image_height"]),int(view["image_width"])):
            raise ValueError("appearance image dimensions do not match manifest")
        if loaded["body_mask"].shape!=loaded["image"].shape[:2] or loaded["face_mask"].shape!=loaded["image"].shape[:2]:
            raise ValueError("body and face masks must match source image dimensions")
        if not np.any(loaded["face_mask"]>127): raise ValueError("face mask must be present and non-empty")
        if not np.any(loaded["body_mask"]>127): raise ValueError("body silhouette mask is empty")
        checked.append({"camera":camera,"matrix":matrix,"gain":gain,"confidence":confidence,**loaded,"view_id":str(view.get("view_id","view"))})
    return rights,{"views":checked,"preprocessing_manifest_sha256":preprocessing,"color_calibration_evidence_sha256":calibration_digest}

def fuse_vertex_appearance(vertices:np.ndarray,faces:np.ndarray,views:list[dict[str,Any]])->tuple[np.ndarray,np.ndarray,dict[str,Any]]:
    import trimesh
    mesh=trimesh.Trimesh(vertices=np.asarray(vertices,dtype=np.float64),faces=np.asarray(faces,dtype=np.int64),process=False)
    mesh.fix_normals(multibody=True)
    normals=np.asarray(mesh.vertex_normals,dtype=np.float64)
    accum=np.zeros((len(vertices),3),dtype=np.float64)
    weights=np.zeros(len(vertices),dtype=np.float64)
    face_masked=np.zeros(len(vertices),dtype=bool)
    per_view=[]
    for view in views:
        image=view["image"].astype(np.float64)/255.0
        corrected=np.clip((image@view["matrix"].T)*view["gain"],0,1)
        xy,depth=_project(vertices,view["camera"])
        height,width=view["image"].shape[:2]
        zbuffer=_build_zbuffer(xy,depth,faces,width,height)
        camera_center=_camera_center(view["camera"])
        direction=camera_center[None,:]-vertices
        direction/=np.maximum(np.linalg.norm(direction,axis=1,keepdims=True),1e-9)
        facing=np.clip(np.sum(normals*direction,axis=1),0,1)
        px=np.rint(xy[:,0]).astype(np.int64,casting="unsafe",copy=False)
        py=np.rint(xy[:,1]).astype(np.int64,casting="unsafe",copy=False)
        in_bounds=np.isfinite(xy).all(axis=1)&(depth>0)&(px>=0)&(px<width)&(py>=0)&(py<height)
        candidate=np.where(in_bounds)[0]
        visible=np.zeros(len(vertices),dtype=bool)
        if len(candidate):
            nearest=zbuffer[py[candidate],px[candidate]]
            tolerance=np.maximum(2.0,depth[candidate]*0.002)
            visible[candidate]=np.abs(nearest-depth[candidate])<=tolerance
        valid=np.zeros(len(vertices),dtype=bool)
        valid[candidate]=(
            visible[candidate]
            &(view["body_mask"][py[candidate],px[candidate]]>127)
            &(view["face_mask"][py[candidate],px[candidate]]<=127)
            &(facing[candidate]>0.02)
        )
        face_masked[candidate]|=view["face_mask"][py[candidate],px[candidate]]>127
        indices=np.where(valid)[0]
        if len(indices):
            pixel_colors=corrected[py[indices],px[indices]]
            sample_weights=view["confidence"]*(facing[indices]**2)
            accum[indices]+=pixel_colors*sample_weights[:,None]
            weights[indices]+=sample_weights
        per_view.append({"view_id":view["view_id"],"visible_vertex_samples":int(len(indices)),"face_masked_vertex_samples":int(np.sum(in_bounds & (view["face_mask"][np.clip(py,0,height-1),np.clip(px,0,width-1)]>127)))})
    covered=weights>0
    colors=np.full((len(vertices),4),[150,150,150,255],dtype=np.uint8)
    if np.any(covered):
        colors[covered,:3]=np.clip(accum[covered]/weights[covered,None]*255,0,255).astype(np.uint8)
    confidence=np.clip(weights,0,1)
    return colors,confidence,{
        "vertex_count":int(len(vertices)),"textured_vertex_count":int(np.sum(covered)),
        "coverage_ratio":float(np.mean(covered)),"face_masked_untextured_vertex_count":int(np.sum(face_masked&~covered)),
        "per_view":per_view,"texture_representation":"multi_view_fused_vertex_colours",
        "face_pixels_excluded":True
    }

def write_private(path:Path,data:bytes)->None:
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name=="posix" and path.parent.stat().st_mode&0o077: raise PermissionError("appearance output directory must be owner-only")
    if path.exists() or path.is_symlink(): raise FileExistsError("refusing to overwrite appearance artifact")
    fd,temp_name=tempfile.mkstemp(prefix=".cvi-appearance-",suffix=".tmp",dir=path.parent)
    temp=Path(temp_name)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.link(temp,path); temp.unlink()
        if os.name=="posix": os.chmod(path,0o600)
    except Exception:
        temp.unlink(missing_ok=True); raise

def reconstruct_appearance(geometry_path:Path,capture_path:Path,rights_path:Path,media_root:Path,output_dir:Path,source_revision:str)->dict[str,Any]:
    capture=json.loads(capture_path.read_text(encoding="utf-8"))
    rights,checked=validate_appearance_capture(capture,rights_path,geometry_path,media_root)
    with np.load(geometry_path,allow_pickle=False) as archive:
        vertices=np.asarray(archive["vertices"],dtype=np.float64)
        faces=np.asarray(archive["faces"],dtype=np.int64)
    if vertices.ndim!=2 or vertices.shape[1]!=3 or not np.isfinite(vertices).all(): raise ValueError("geometry vertices are invalid")
    if faces.ndim!=2 or faces.shape[1]!=3 or np.any(faces<0) or np.any(faces>=len(vertices)): raise ValueError("geometry faces are invalid")
    colors,confidence,quality=fuse_vertex_appearance(vertices,faces,checked["views"])
    if quality["coverage_ratio"]<0.05: raise ValueError("appearance projection coverage is below the 5% minimum")
    import trimesh
    mesh=trimesh.Trimesh(vertices=vertices,faces=faces,vertex_colors=colors,process=False)
    mesh.fix_normals(multibody=True)
    glb=mesh.export(file_type="glb")
    if not isinstance(glb,bytes) or not glb.startswith(b"glTF"): raise ValueError("appearance GLB serialization failed")
    output_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    glb_path=output_dir/"twin-appearance-candidate.glb"
    write_private(glb_path,glb)
    report={
        "schema_version":"1.0","status":"research_candidate_not_qualified",
        "source_revision":source_revision,
        "geometry_sha256":digest(geometry_path),"capture_sha256":digest(capture_path),
        "rights_manifest_sha256":rights["manifest_sha256"],
        "preprocessing_manifest_sha256":checked["preprocessing_manifest_sha256"],
        "color_calibration_evidence_sha256":checked["color_calibration_evidence_sha256"],
        "appearance_asset_sha256":hashlib.sha256(glb).hexdigest(),
        "quality":quality,"limitations":[
            "Vertex-colour fusion is not a high-resolution UV texture atlas.",
            "Colour correction depends on supplied camera calibration evidence.",
            "No independent appearance likeness, material, skin/hair or temporal consistency evaluation has been performed.",
            "Face regions are deliberately excluded and remain neutral; no facial identity reconstruction is performed.",
            "No Twin Registry persistence, revocation or deletion integration is included."
        ]
    }
    report_path=output_dir/"appearance-report.json"
    report_bytes=(json.dumps(report,indent=2,sort_keys=True)+"\n").encode()
    write_private(report_path,report_bytes)
    return report

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry",required=True,type=Path)
    parser.add_argument("--capture",required=True,type=Path)
    parser.add_argument("--rights-manifest",required=True,type=Path)
    parser.add_argument("--media-root",required=True,type=Path)
    parser.add_argument("--output-dir",required=True,type=Path)
    args=parser.parse_args()
    source_revision=require_clean_source_revision(ROOT)
    result=reconstruct_appearance(args.geometry,args.capture,args.rights_manifest,args.media_root,args.output_dir,source_revision)
    print(json.dumps({"status":result["status"],"appearance_asset_sha256":result["appearance_asset_sha256"],"quality":result["quality"]}))
    return 0

if __name__=="__main__": raise SystemExit(main())
