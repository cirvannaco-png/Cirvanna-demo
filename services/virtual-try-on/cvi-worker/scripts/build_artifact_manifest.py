#!/usr/bin/env python3
"""Assemble a digest-bound CVI Try-On model bundle; does not grant release approval."""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from tools.model_evaluation.fashion_retrieval.data_rights import load_and_validate_data_rights_manifest

SHA256=re.compile(r"^[0-9a-f]{64}$")
COMMIT=re.compile(r"^[0-9a-f]{40}$")
FILES={
    "checkpoint":"model.pt",
    "training_report":"training-report.json",
    "evaluation_report":"evaluation-report.json",
    "dataset_manifest":"dataset.manifest.json",
    "person_rights_manifest":"person-rights.manifest.json",
    "garment_rights_manifest":"garment-rights.manifest.json",
}
def digest(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest()
def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir",required=True,type=Path)
    parser.add_argument("--checkpoint",required=True,type=Path)
    parser.add_argument("--training-report",required=True,type=Path)
    parser.add_argument("--evaluation-report",required=True,type=Path)
    parser.add_argument("--dataset-manifest",required=True,type=Path)
    parser.add_argument("--person-rights-manifest",required=True,type=Path)
    parser.add_argument("--garment-rights-manifest",required=True,type=Path)
    parser.add_argument("--source-revision",required=True)
    parser.add_argument("--runtime-image-digest",required=True)
    parser.add_argument("--minimum-gpu-memory-bytes",type=int,default=8*1024**3)
    parser.add_argument("--max-gpu-memory-fraction",type=float,default=0.8)
    args=parser.parse_args()
    if not COMMIT.fullmatch(args.source_revision): raise ValueError("source revision must be a full 40-character commit SHA")
    if not SHA256.fullmatch(args.runtime_image_digest): raise ValueError("runtime image digest must be lowercase SHA-256")
    if not 8*1024**3<=args.minimum_gpu_memory_bytes<=128*1024**3: raise ValueError("minimum GPU memory must be between 8 and 128 GiB")
    if not 0.1<=args.max_gpu_memory_fraction<=0.8: raise ValueError("GPU memory fraction must be between 0.1 and 0.8")
    for path in (args.checkpoint,args.training_report,args.evaluation_report,args.dataset_manifest,args.person_rights_manifest,args.garment_rights_manifest):
        if path.is_symlink() or not path.is_file(): raise ValueError(f"required bundle input is missing or unsafe: {path.name}")
    training=json.loads(args.training_report.read_text(encoding="utf-8"))
    evaluation=json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    dataset=json.loads(args.dataset_manifest.read_text(encoding="utf-8"))
    person_rights=load_and_validate_data_rights_manifest(args.person_rights_manifest,expected_scope="virtual_try_on_training")
    garment_rights=load_and_validate_data_rights_manifest(args.garment_rights_manifest,expected_scope="virtual_try_on_training")
    if person_rights.get("contains_personal_images") is not True or person_rights.get("depicted_person_consent_status")!="verified":
        raise ValueError("person training rights do not prove verified subject consent")
    if garment_rights.get("contains_personal_images") is True and garment_rights.get("depicted_person_consent_status")!="verified":
        raise ValueError("catalogue garment rights do not prove depicted-model consent")
    if dataset.get("person_rights_manifest_sha256")!=person_rights["manifest_sha256"] or dataset.get("garment_rights_manifest_sha256")!=garment_rights["manifest_sha256"]:
        raise ValueError("dataset manifest does not bind the supplied person and garment rights")
    if training.get("model_id")!="cirvanna-tryon-warp-refine-v0" or training.get("architecture")!="custom-unet-flow-warp-alpha-residual":
        raise ValueError("training report does not describe the CVI Try-On candidate")
    if training.get("source_revision")!=args.source_revision: raise ValueError("source revision differs from training report")
    if training.get("dataset",{}).get("person_rights_manifest_sha256")!=person_rights["manifest_sha256"] or training.get("dataset",{}).get("garment_rights_manifest_sha256")!=garment_rights["manifest_sha256"]:
        raise ValueError("training report rights digests differ from supplied rights manifests")
    if evaluation.get("model_id")!="cirvanna-tryon-warp-refine-v0":
        raise ValueError("independent evaluation report model ID is invalid")
    if evaluation.get("checkpoint_sha256")!=digest(args.checkpoint) or evaluation.get("dataset_manifest_sha256")!=digest(args.dataset_manifest):
        raise ValueError("independent evaluation report is not bound to this checkpoint and dataset")
    base_channels=training.get("training",{}).get("base_channels")
    if not isinstance(base_channels,int) or not 8<=base_channels<=64: raise ValueError("training report base_channels is invalid")
    args.bundle_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    if args.bundle_dir.is_symlink() or args.bundle_dir.stat().st_mode&0o077:
        raise PermissionError("model bundle directory must be owner-only and not a symlink")
    inputs={
        "model.pt":args.checkpoint,"training-report.json":args.training_report,
        "evaluation-report.json":args.evaluation_report,"dataset.manifest.json":args.dataset_manifest,
        "person-rights.manifest.json":args.person_rights_manifest,"garment-rights.manifest.json":args.garment_rights_manifest
    }
    for name,source in inputs.items():
        target=args.bundle_dir/name
        if target.exists() or target.is_symlink(): raise FileExistsError(f"refusing to overwrite {name}")
        shutil.copyfile(source,target)
        os.chmod(target,0o600)
    manifest={
        "schema_version":"1.0","model_id":"cirvanna-tryon-warp-refine-v0",
        "architecture":"cvi-garment-conditioned-warp-refine-unet-v0",
        "source_revision":args.source_revision,
        "checkpoint_sha256":digest(args.bundle_dir/"model.pt"),
        "training_report_sha256":digest(args.bundle_dir/"training-report.json"),
        "evaluation_report_sha256":digest(args.bundle_dir/"evaluation-report.json"),
        "dataset_manifest_sha256":digest(args.bundle_dir/"dataset.manifest.json"),
        "person_rights_manifest_sha256":digest(args.bundle_dir/"person-rights.manifest.json"),
        "garment_rights_manifest_sha256":digest(args.bundle_dir/"garment-rights.manifest.json"),
        "base_channels":base_channels,"input_resolution":256,"pose_channels":17,
        "max_gpu_memory_fraction":args.max_gpu_memory_fraction,
        "minimum_gpu_memory_bytes":args.minimum_gpu_memory_bytes,
        "max_concurrency":1,"runtime_image_digest":args.runtime_image_digest,
        "qualification_attestation":None
    }
    target=args.bundle_dir/"manifest.json"
    if target.exists() or target.is_symlink(): raise FileExistsError("refusing to overwrite model manifest")
    target.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    os.chmod(target,0o600)
    print(json.dumps({"status":"bundle_assembled_pending_independent_attestation","manifest_sha256":digest(target),"bundle_dir":str(args.bundle_dir)}))
    return 0
if __name__=="__main__": raise SystemExit(main())
