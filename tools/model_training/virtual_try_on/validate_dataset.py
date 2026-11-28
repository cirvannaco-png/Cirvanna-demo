#!/usr/bin/env python3
"""Validate rights-cleared paired person/garment/target data for CVI Try-On."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
from typing import Any
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.model_evaluation.fashion_retrieval.data_rights import load_and_validate_data_rights_manifest

SHA256=re.compile(r"^[0-9a-f]{64}$")
REQUIRED_SPLITS={"train","validation","test"}
IMAGE_ROLES=("person_image","garment_image","target_image","person_mask","garment_mask","target_garment_mask","pose_heatmap")
MAX_FILE_BYTES=25*1024*1024
MAX_PIXELS=20_000_000
POSE_CHANNELS=17

def sha256_file(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest()

def safe_path(root:Path,relative:Any)->Path:
    if not isinstance(relative,str) or not relative.strip() or "\\" in relative:
        raise ValueError("media path must be a non-empty POSIX relative path")
    candidate=Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("media path traversal is forbidden")
    resolved_root=root.resolve(); lexical=resolved_root
    for part in candidate.parts:
        lexical=lexical/part
        if lexical.is_symlink(): raise ValueError("symlink media paths are forbidden")
    resolved=lexical.resolve()
    if resolved_root not in resolved.parents or not resolved.is_file():
        raise ValueError("media path must resolve to a regular file inside media root")
    if resolved.stat().st_size>MAX_FILE_BYTES: raise ValueError("media file exceeds byte limit")
    return resolved

def validate_sample(row:Any,line:int)->dict[str,Any]:
    if not isinstance(row,dict): raise ValueError(f"line {line}: sample must be an object")
    for key in ("sample_id","subject_cluster_id","garment_product_id","garment_family_id","split","preprocessing_manifest_sha256"):
        if not isinstance(row.get(key),str) or not row[key].strip(): raise ValueError(f"line {line}: {key} is required")
    if row["split"] not in REQUIRED_SPLITS: raise ValueError(f"line {line}: invalid split")
    if row.get("face_masked_before_training") is not True: raise ValueError(f"line {line}: face masking must precede training")
    if not SHA256.fullmatch(row["preprocessing_manifest_sha256"]): raise ValueError(f"line {line}: preprocessing manifest digest is invalid")
    if row.get("garment_face_masked_before_training") is not True:
        raise ValueError(f"line {line}: garment faces must be masked before training")
    if not isinstance(row.get("subgroups"),dict) or not row["subgroups"]:
        raise ValueError(f"line {line}: non-empty evaluation subgroup metadata is required")
    media=row.get("media")
    if not isinstance(media,dict) or set(media)!=set(IMAGE_ROLES): raise ValueError(f"line {line}: media must bind every required image/mask/pose role")
    for role,value in media.items():
        if not isinstance(value,dict) or not isinstance(value.get("path"),str) or not value["path"].strip():
            raise ValueError(f"line {line}: media role {role} path is required")
        if not isinstance(value.get("sha256"),str) or not SHA256.fullmatch(value["sha256"]):
            raise ValueError(f"line {line}: media role {role} SHA-256 is invalid")
    return row

def split_manifest_digest(rows:list[dict[str,Any]])->str:
    values=sorted(({"sample_id":r["sample_id"],"subject_cluster_id":r["subject_cluster_id"],"garment_family_id":r["garment_family_id"],"split":r["split"]} for r in rows),key=lambda r:r["sample_id"])
    return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def _validate_media(path:Path,role:str,expected_digest:str)->tuple[int,int]:
    if sha256_file(path)!=expected_digest: raise ValueError(f"{role} media digest mismatch")
    if role=="pose_heatmap":
        try:
            with np.load(path,allow_pickle=False) as archive: heatmaps=np.asarray(archive["heatmaps"],dtype=np.float32)
        except Exception as exc: raise ValueError("pose heatmap archive is invalid") from exc
        if heatmaps.ndim!=3 or heatmaps.shape[0]!=POSE_CHANNELS or not np.isfinite(heatmaps).all() or np.any(heatmaps<0) or np.any(heatmaps>1):
            raise ValueError("pose heatmaps must have 17 finite channels in [0,1]")
        return int(heatmaps.shape[2]),int(heatmaps.shape[1])
    with Image.open(path) as image:
        if min(image.width,image.height)<256: raise ValueError(f"{role} dimensions are below the 256px minimum")
        if image.width*image.height>MAX_PIXELS: raise ValueError(f"{role} exceeds pixel limit")
        image.verify()
    with Image.open(path) as image:
        if role.endswith("_mask") and image.mode not in ("L","1"):
            raise ValueError(f"{role} must be a grayscale mask")
        return image.width,image.height

def validate_dataset(manifest_path:Path,annotations_path:Path,media_root:Path,person_rights_path:Path,garment_rights_path:Path)->dict[str,Any]:
    person_rights=load_and_validate_data_rights_manifest(person_rights_path,expected_scope="virtual_try_on_training")
    garment_rights=load_and_validate_data_rights_manifest(garment_rights_path,expected_scope="virtual_try_on_training")
    if person_rights.get("contains_personal_images") is not True or person_rights.get("depicted_person_consent_status")!="verified":
        raise ValueError("person and target images require verified subject consent")
    if person_rights["manifest_sha256"]==garment_rights["manifest_sha256"]:
        raise ValueError("person and catalogue garment rights must be separately evidenced")
    if garment_rights.get("contains_personal_images") is True and garment_rights.get("depicted_person_consent_status")!="verified":
        raise ValueError("garment catalogue images depicting people require verified model consent")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest,dict) or manifest.get("schema_version")!="1.0": raise ValueError("dataset manifest schema_version must be 1.0")
    for key in ("pose_protocol_id","mask_protocol_id"):
        if not isinstance(manifest.get(key),str) or not manifest[key].strip():
            raise ValueError(f"{key} is required")
    raw=annotations_path.read_bytes()
    annotations_digest=hashlib.sha256(raw).hexdigest()
    if manifest.get("annotations_sha256")!=annotations_digest: raise ValueError("annotation file digest mismatch")
    if manifest.get("person_rights_manifest_sha256")!=person_rights["manifest_sha256"]: raise ValueError("person rights manifest digest mismatch")
    if manifest.get("garment_rights_manifest_sha256")!=garment_rights["manifest_sha256"]: raise ValueError("garment rights manifest digest mismatch")
    rows=[]
    for line,value in enumerate(raw.decode("utf-8").splitlines(),1):
        if value.strip(): rows.append(validate_sample(json.loads(value),line))
    if not rows or manifest.get("sample_count")!=len(rows): raise ValueError("dataset sample_count mismatch or dataset empty")
    if len({r["sample_id"] for r in rows})!=len(rows): raise ValueError("sample_id values must be unique")
    if {r["split"] for r in rows}!=REQUIRED_SPLITS: raise ValueError("dataset must contain train, validation and test splits")
    subjects:dict[str,set[str]]={}; garment_families:dict[str,set[str]]={}
    product_families:dict[str,set[str]]={}; product_splits:dict[str,set[str]]={}
    image_splits:dict[str,set[str]]={}
    for row in rows:
        subjects.setdefault(row["subject_cluster_id"],set()).add(row["split"])
        garment_families.setdefault(row["garment_family_id"],set()).add(row["split"])
        product_families.setdefault(row["garment_product_id"],set()).add(row["garment_family_id"])
        product_splits.setdefault(row["garment_product_id"],set()).add(row["split"])
        dimensions={}
        for role,value in row["media"].items():
            path=safe_path(media_root,value["path"])
            dimensions[role]=_validate_media(path,role,value["sha256"])
            if role!="pose_heatmap":
                image_splits.setdefault(value["sha256"],set()).add(row["split"])
        if row["media"]["person_image"]["sha256"]==row["media"]["target_image"]["sha256"]:
            raise ValueError("source person and target-worn images must be distinct")
        for image_role,mask_role in (("person_image","person_mask"),("garment_image","garment_mask"),("target_image","target_garment_mask")):
            if dimensions[image_role]!=dimensions[mask_role]: raise ValueError(f"{mask_role} dimensions must match {image_role}")
        if dimensions["pose_heatmap"]!=(64,64): raise ValueError("pose heatmaps must be 64x64 with 17 channels")
        if dimensions["person_image"]!=dimensions["target_image"]: raise ValueError("person and target images must share dimensions")
    if any(len(splits)!=1 for splits in subjects.values()): raise ValueError("subject clusters leak across dataset splits")
    if any(len(splits)!=1 for splits in garment_families.values()): raise ValueError("garment-family clusters leak across dataset splits")
    if any(len(families)!=1 for families in product_families.values()) or any(len(splits)!=1 for splits in product_splits.values()):
        raise ValueError("garment product IDs must map to exactly one family and split")
    if any(len(splits)!=1 for splits in image_splits.values()): raise ValueError("image bytes leak across dataset splits")
    split_digest=split_manifest_digest(rows)
    if manifest.get("split_manifest_sha256")!=split_digest: raise ValueError("split manifest digest mismatch")
    return {
        "dataset_id":manifest.get("dataset_id"),"sample_count":len(rows),
        "split_counts":{s:sum(r["split"]==s for r in rows) for s in sorted(REQUIRED_SPLITS)},
        "subject_cluster_count":len(subjects),"garment_family_count":len(garment_families),
        "annotations_sha256":annotations_digest,"split_manifest_sha256":split_digest,
        "person_rights_manifest_sha256":person_rights["manifest_sha256"],
        "person_rights_evidence_sha256":person_rights["evidence_sha256"],
        "garment_rights_manifest_sha256":garment_rights["manifest_sha256"],
        "garment_rights_evidence_sha256":garment_rights["evidence_sha256"],
        "status":"validated_for_try_on_training_input_only"
    }

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",required=True,type=Path)
    parser.add_argument("--annotations",required=True,type=Path)
    parser.add_argument("--media-root",required=True,type=Path)
    parser.add_argument("--person-rights-manifest",required=True,type=Path)
    parser.add_argument("--garment-rights-manifest",required=True,type=Path)
    args=parser.parse_args()
    print(json.dumps(validate_dataset(args.manifest,args.annotations,args.media_root,args.person_rights_manifest,args.garment_rights_manifest),indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
