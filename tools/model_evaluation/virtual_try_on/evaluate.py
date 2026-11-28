#!/usr/bin/env python3
"""Independently evaluate a frozen Cirvanna Try-On checkpoint on held-out test data."""
from __future__ import annotations
import argparse, hashlib, io, json, sys, time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.model_training.provenance import require_clean_source_revision
from tools.model_training.virtual_try_on.validate_dataset import validate_dataset,safe_path
from tools.model_training.virtual_try_on.model import build_model
from tools.model_evaluation.fashion_retrieval.private_artifacts import write_private_text

MODEL_ID="cirvanna-tryon-warp-refine-v0"
ARCHITECTURE="custom-unet-flow-warp-alpha-residual"

def digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def ssim_score(x,y,torch)->float:
    """Global SSIM diagnostic; not a substitute for perceptual or human review."""
    x=x.float(); y=y.float()
    mx=x.mean(); my=y.mean()
    vx=((x-mx)**2).mean(); vy=((y-my)**2).mean()
    covariance=((x-mx)*(y-my)).mean()
    c1=0.01**2; c2=0.03**2
    value=((2*mx*my+c1)*(2*covariance+c2))/((mx*mx+my*my+c1)*(vx+vy+c2)).clamp_min(1e-12)
    return float(value.clamp(-1,1).detach().cpu())

def sample_metrics(outputs:dict[str,Any],target,mask,torch)->dict[str,float]:
    prediction=((outputs["image"]+1.0)/2.0).clamp(0,1)
    target=((target+1.0)/2.0).clamp(0,1)
    absolute=(prediction-target).abs()
    mae=float(absolute.mean().detach().cpu())
    mse=float(((prediction-target)**2).mean().detach().cpu())
    psnr=float((10.0*torch.log10(1.0/torch.tensor(max(mse,1e-12),device=prediction.device))).detach().cpu())
    garment_mae=float((absolute*mask).sum().div(mask.sum().clamp_min(1.0)*3).detach().cpu())
    true_mask=mask>=0.5
    alpha=outputs["alpha"]>=0.5
    warped=outputs["warped_garment_mask"]>=0.5
    def iou(pred):
        intersection=(pred&true_mask).sum().float()
        union=(pred|true_mask).sum().float()
        return float((intersection/union.clamp_min(1.0)).detach().cpu())
    return {
        "image_mae":mae,
        "psnr_db":psnr,
        "ssim_global":ssim_score(prediction,target,torch),
        "garment_region_mae":garment_mae,
        "alpha_mask_iou":iou(alpha),
        "warped_garment_mask_iou":iou(warped),
    }

def mean_metrics(rows:list[dict[str,float]])->dict[str,float]:
    if not rows: raise ValueError("evaluation split is empty")
    keys=rows[0].keys()
    return {key:sum(row[key] for row in rows)/len(rows) for key in keys}

def run(args)->dict[str,Any]:
    source_revision=require_clean_source_revision(ROOT)
    rights=validate_dataset(args.manifest,args.annotations,args.media_root,args.person_rights_manifest,args.garment_rights_manifest)
    manifest_sha=digest(args.manifest)
    training=json.loads(args.training_report.read_text(encoding="utf-8"))
    if training.get("model_id")!=MODEL_ID or training.get("architecture")!=ARCHITECTURE:
        raise ValueError("training report does not describe the Cirvanna Try-On model")
    if training.get("source_revision")!=source_revision:
        raise ValueError("evaluation source revision must exactly match the training source revision")
    if digest(args.checkpoint)!=training.get("checkpoint_sha256"):
        raise ValueError("checkpoint digest does not match training report")
    trained_dataset=training.get("dataset",{})
    if trained_dataset.get("dataset_manifest_sha256")!=manifest_sha:
        raise ValueError("training report dataset manifest digest mismatch")
    for key in ("annotations_sha256","split_manifest_sha256","person_rights_manifest_sha256","garment_rights_manifest_sha256"):
        if trained_dataset.get(key)!=rights.get(key):
            raise ValueError(f"training report dataset provenance mismatch: {key}")
    if training.get("training",{}).get("device")!="cuda" and not args.allow_cpu_diagnostic:
        raise ValueError("qualification evaluation requires a CUDA-trained checkpoint; CPU diagnostic must be explicitly allowed")
    try:
        import torch
        import torch.nn.functional as F
        from torch.utils.data import DataLoader,Dataset
    except ImportError as exc:
        raise RuntimeError("PyTorch is required in the approved evaluation runtime") from exc
    if args.device=="cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable; no implicit CPU fallback")
    if args.device=="cuda":
        torch.cuda.set_per_process_memory_fraction(args.max_gpu_memory_fraction,device=0)
        torch.cuda.reset_peak_memory_stats()
    rows=[json.loads(line) for line in args.annotations.read_text(encoding="utf-8").splitlines() if line.strip()]
    test_rows=[row for row in rows if row["split"]=="test"]
    if not test_rows: raise ValueError("frozen test split is empty")
    class TestDataset(Dataset):
        def __len__(self): return len(test_rows)
        def _image(self,row,role,mask=False):
            media=row["media"][role]
            path=safe_path(args.media_root,media["path"])
            if digest(path)!=media["sha256"]: raise ValueError(f"{role} changed after validation")
            with Image.open(path) as image:
                image=image.convert("L" if mask else "RGB")
                image=image.resize((256,256),Image.Resampling.NEAREST if mask else Image.Resampling.BICUBIC)
                array=np.asarray(image,dtype=np.float32).copy()
            if mask: return torch.from_numpy(array).unsqueeze(0)/255.0
            return torch.from_numpy(array).permute(2,0,1)/127.5-1.0
        def __getitem__(self,index):
            row=test_rows[index]
            pose_media=row["media"]["pose_heatmap"]
            pose_path=safe_path(args.media_root,pose_media["path"])
            if digest(pose_path)!=pose_media["sha256"]: raise ValueError("pose heatmap changed after validation")
            with np.load(io.BytesIO(pose_path.read_bytes()),allow_pickle=False) as archive:
                pose=torch.from_numpy(np.asarray(archive["heatmaps"],dtype=np.float32).copy()).unsqueeze(0)
            pose=F.interpolate(pose,size=(256,256),mode="bilinear",align_corners=False).squeeze(0)
            return {
                "person":self._image(row,"person_image"),
                "garment":self._image(row,"garment_image"),
                "person_mask":self._image(row,"person_mask",True),
                "garment_mask":self._image(row,"garment_mask",True),
                "pose":pose,
                "target":self._image(row,"target_image"),
                "target_mask":self._image(row,"target_garment_mask",True),
            }
    loader=DataLoader(TestDataset(),batch_size=args.batch_size,shuffle=False,num_workers=0)
    base_channels=training.get("training",{}).get("base_channels")
    if isinstance(base_channels,bool) or not isinstance(base_channels,int) or not 8<=base_channels<=64:
        raise ValueError("training report base_channels is invalid")
    checkpoint=torch.load(args.checkpoint,map_location="cpu",weights_only=True)
    if not isinstance(checkpoint,dict) or not isinstance(checkpoint.get("model_state_dict"),dict):
        raise ValueError("checkpoint must contain a safe model_state_dict")
    model=build_model(base_channels).to(args.device)
    model.load_state_dict(checkpoint["model_state_dict"],strict=True)
    model.eval()
    per_sample=[]; subgroup_rows=defaultdict(list); elapsed=[]
    with torch.inference_mode():
        offset=0
        for batch in loader:
            values={key:value.to(args.device) for key,value in batch.items()}
            started=time.perf_counter()
            outputs=model(values["person"],values["garment"],values["person_mask"],values["garment_mask"],values["pose"])
            if args.device=="cuda": torch.cuda.synchronize()
            elapsed.append((time.perf_counter()-started)/len(batch["person"]))
            for i in range(len(batch["person"])):
                metrics=sample_metrics({key:value[i:i+1] for key,value in outputs.items()},values["target"][i:i+1],values["target_mask"][i:i+1],torch)
                row=test_rows[offset+i]
                per_sample.append(metrics)
                for key,value in row["subgroups"].items():
                    subgroup_rows[f"{key}={value}"].append(metrics)
            offset+=len(batch["person"])
            for value in values.values():
                try: value.zero_()
                except Exception: pass
            for value in outputs.values():
                try: value.zero_()
                except Exception: pass
    if args.device=="cuda": torch.cuda.synchronize()
    report={
        "schema_version":"1.0",
        "task":"independent_virtual_try_on_held_out_evaluation",
        "model_id":MODEL_ID,"architecture":ARCHITECTURE,
        "source_revision":source_revision,
        "checkpoint_sha256":digest(args.checkpoint),
        "training_report_sha256":digest(args.training_report),
        "dataset_manifest_sha256":manifest_sha,
        "annotations_sha256":rights["annotations_sha256"],
        "split_manifest_sha256":rights["split_manifest_sha256"],
        "person_rights_manifest_sha256":rights["person_rights_manifest_sha256"],
        "garment_rights_manifest_sha256":rights["garment_rights_manifest_sha256"],
        "sample_count":len(test_rows),
        "subject_cluster_count":len({row["subject_cluster_id"] for row in test_rows}),
        "garment_family_count":len({row["garment_family_id"] for row in test_rows}),
        "device":args.device,
        "metrics_macro_sample_mean":mean_metrics(per_sample),
        "subgroups":{key:{"sample_count":len(values),"metrics":mean_metrics(values)} for key,values in sorted(subgroup_rows.items())},
        "latency_ms":{"mean_per_sample":sum(elapsed)/len(elapsed)*1000,"p95_per_sample":float(np.percentile(elapsed,95)*1000)},
        "peak_gpu_memory_allocated_bytes":torch.cuda.max_memory_allocated() if args.device=="cuda" else None,
        "peak_gpu_memory_reserved_bytes":torch.cuda.max_memory_reserved() if args.device=="cuda" else None,
        "status":"independent_held_out_evaluation_not_qualified",
        "limitations":[
            "Pixel metrics and global SSIM do not establish garment identity, logo/pattern preservation, drape, occlusion realism or human preference.",
            "Subgroup means are descriptive and do not include cluster-bootstrap confidence intervals.",
            "The evaluator does not independently audit pixel-level face masking or legal rights evidence.",
            "A separate blinded human evaluation, privacy/deletion review and real GPU resource test remain mandatory."
        ]
    }
    return report

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",required=True,type=Path)
    parser.add_argument("--annotations",required=True,type=Path)
    parser.add_argument("--media-root",required=True,type=Path)
    parser.add_argument("--person-rights-manifest",required=True,type=Path)
    parser.add_argument("--garment-rights-manifest",required=True,type=Path)
    parser.add_argument("--checkpoint",required=True,type=Path)
    parser.add_argument("--training-report",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--device",choices=("cpu","cuda"),default="cuda")
    parser.add_argument("--batch-size",type=int,default=1)
    parser.add_argument("--max-gpu-memory-fraction",type=float,default=0.8)
    parser.add_argument("--allow-cpu-diagnostic",action="store_true")
    parser.add_argument("--overwrite",action="store_true")
    args=parser.parse_args()
    if args.batch_size<1 or not 0.1<=args.max_gpu_memory_fraction<=0.8:
        raise ValueError("invalid batch size or GPU memory fraction")
    report=run(args)
    write_private_text(args.output,json.dumps(report,indent=2,sort_keys=True)+"\n",overwrite=args.overwrite)
    print(json.dumps({"status":report["status"],"sample_count":report["sample_count"],"metrics":report["metrics_macro_sample_mean"]}))
    return 0
if __name__=="__main__": raise SystemExit(main())
