#!/usr/bin/env python3
"""Train Cirvanna's garment-conditioned warp-and-refine Virtual Try-On candidate."""
from __future__ import annotations
import argparse, hashlib, io, json, os, random, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.model_training.virtual_try_on.validate_dataset import validate_dataset,safe_path
from tools.model_training.virtual_try_on.model import build_model,try_on_loss
from tools.model_training.provenance import require_clean_source_revision
from tools.model_evaluation.fashion_retrieval.private_artifacts import write_private_text

def save_private_checkpoint(path:Path,torch,model,metadata):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name=="posix" and path.parent.stat().st_mode&0o077:
        raise PermissionError("training output directory must be owner-only (0700)")
    if path.exists() or path.is_symlink(): raise FileExistsError("refusing to overwrite model checkpoint")
    fd,temp_name=tempfile.mkstemp(prefix=".cvi-vton-",suffix=".tmp",dir=path.parent)
    temp=Path(temp_name)
    try:
        with os.fdopen(fd,"wb") as stream:
            torch.save({"model_state_dict":model.cpu().state_dict(),**metadata},stream)
            stream.flush(); os.fsync(stream.fileno())
        os.link(temp,path); temp.unlink()
        if os.name=="posix": os.chmod(path,0o600)
    except Exception:
        temp.unlink(missing_ok=True); raise

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",required=True,type=Path)
    parser.add_argument("--annotations",required=True,type=Path)
    parser.add_argument("--media-root",required=True,type=Path)
    parser.add_argument("--person-rights-manifest",required=True,type=Path)
    parser.add_argument("--garment-rights-manifest",required=True,type=Path)
    parser.add_argument("--output-dir",required=True,type=Path)
    parser.add_argument("--epochs",type=int,default=50)
    parser.add_argument("--batch-size",type=int,default=2)
    parser.add_argument("--learning-rate",type=float,default=0.0002)
    parser.add_argument("--base-channels",type=int,default=32)
    parser.add_argument("--seed",type=int,default=20261127)
    parser.add_argument("--device",choices=("cpu","cuda"),default="cuda")
    parser.add_argument("--max-gpu-memory-fraction",type=float,default=0.8)
    args=parser.parse_args()
    if args.epochs<1 or args.batch_size<1 or args.base_channels<8:
        raise ValueError("invalid training hyperparameters")
    if not 0<args.learning_rate<1 or not 0.1<=args.max_gpu_memory_fraction<=0.95:
        raise ValueError("invalid optimizer or GPU resource configuration")
    source_revision=require_clean_source_revision(ROOT)
    dataset=validate_dataset(args.manifest,args.annotations,args.media_root,args.person_rights_manifest,args.garment_rights_manifest)
    try:
        import torch
        import torch.nn.functional as F
        from torch.utils.data import DataLoader,Dataset
    except ImportError as exc:
        raise RuntimeError("PyTorch must be installed in the approved Try-On training image") from exc
    if args.device=="cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but no GPU is available; no CPU fallback is implicit")
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    if args.device=="cuda":
        torch.cuda.manual_seed_all(args.seed)
        torch.cuda.set_per_process_memory_fraction(args.max_gpu_memory_fraction,device=0)
    rows=[json.loads(line) for line in args.annotations.read_text(encoding="utf-8").splitlines() if line.strip()]
    class TryOnDataset(Dataset):
        def __init__(self,split): self.rows=[row for row in rows if row["split"]==split]
        def __len__(self): return len(self.rows)
        def _image(self,row,role,mask=False):
            media=row["media"][role]
            path=safe_path(args.media_root,media["path"])
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=media["sha256"]:
                raise ValueError(f"{role} changed after dataset validation")
            with Image.open(io.BytesIO(raw)) as image:
                image=image.convert("L" if mask else "RGB")
                image=image.resize((256,256),Image.Resampling.NEAREST if mask else Image.Resampling.BICUBIC)
                array=np.asarray(image,dtype=np.float32)
            if mask:
                return torch.from_numpy(array.copy()).unsqueeze(0)/255.0
            return torch.from_numpy(array.copy()).permute(2,0,1)/127.5-1.0
        def __getitem__(self,index):
            row=self.rows[index]
            pose_media=row["media"]["pose_heatmap"]
            pose_path=safe_path(args.media_root,pose_media["path"])
            pose_bytes=pose_path.read_bytes()
            if hashlib.sha256(pose_bytes).hexdigest()!=pose_media["sha256"]:
                raise ValueError("pose heatmap changed after dataset validation")
            with np.load(io.BytesIO(pose_bytes),allow_pickle=False) as archive:
                pose=torch.from_numpy(np.asarray(archive["heatmaps"],dtype=np.float32)).unsqueeze(0)
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
    train_data=TryOnDataset("train"); validation_data=TryOnDataset("validation"); test_data=TryOnDataset("test")
    train_loader=DataLoader(train_data,batch_size=args.batch_size,shuffle=True,num_workers=0)
    validation_loader=DataLoader(validation_data,batch_size=args.batch_size,shuffle=False,num_workers=0)
    test_loader=DataLoader(test_data,batch_size=args.batch_size,shuffle=False,num_workers=0)
    device=torch.device(args.device)
    model=build_model(args.base_channels).to(device)
    if args.device=="cuda": torch.cuda.reset_peak_memory_stats()
    optimizer=torch.optim.AdamW(model.parameters(),lr=args.learning_rate)
    def evaluate(loader):
        model.eval()
        total_mae=total_psnr=total_garment_mae=total_iou=total_warp_iou=0.0
        batches=0
        with torch.no_grad():
            for batch in loader:
                values={key:value.to(device) for key,value in batch.items()}
                outputs=model(values["person"],values["garment"],values["person_mask"],values["garment_mask"],values["pose"])
                prediction=((outputs["image"]+1)/2).clamp(0,1)
                target=((values["target"]+1)/2).clamp(0,1)
                mae=torch.abs(prediction-target).mean()
                mse=torch.mean((prediction-target)**2)
                psnr=10*torch.log10(1.0/mse.clamp_min(1e-8))
                mask=values["target_mask"]
                garment_mae=(torch.abs(prediction-target)*mask).sum()/(mask.sum().clamp_min(1.0)*3)
                pred_mask=outputs["alpha"]>=0.5; true_mask=mask>=0.5
                intersection=(pred_mask&true_mask).sum().float()
                union=(pred_mask|true_mask).sum().float()
                iou=intersection/union.clamp_min(1.0)
                warped_mask=outputs["warped_garment_mask"]>=0.5
                warp_intersection=(warped_mask&true_mask).sum().float()
                warp_union=(warped_mask|true_mask).sum().float()
                warp_iou=warp_intersection/warp_union.clamp_min(1.0)
                total_mae+=float(mae); total_psnr+=float(psnr); total_garment_mae+=float(garment_mae); total_iou+=float(iou); total_warp_iou+=float(warp_iou); batches+=1
        if not batches: raise ValueError("validation/test split is empty")
        return {"image_mae":total_mae/batches,"psnr_db":total_psnr/batches,"garment_region_mae":total_garment_mae/batches,"alpha_mask_iou":total_iou/batches,"warped_garment_mask_iou":total_warp_iou/batches,"batches":batches}
    history=[]
    for epoch in range(args.epochs):
        model.train(); losses=[]
        for batch in train_loader:
            values={key:value.to(device) for key,value in batch.items()}
            outputs=model(values["person"],values["garment"],values["person_mask"],values["garment_mask"],values["pose"])
            loss,parts=try_on_loss(outputs,values["target"],values["target_mask"])
            if not torch.isfinite(loss): raise RuntimeError("non-finite Try-On loss; aborting")
            optimizer.zero_grad(set_to_none=True); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),max_norm=1.0)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        history.append({"epoch":epoch+1,"train_loss":sum(losses)/max(1,len(losses)),"validation":evaluate(validation_loader)})
    test_metrics=evaluate(test_loader)
    if args.device=="cuda": torch.cuda.synchronize()
    peak_gpu_allocated=torch.cuda.max_memory_allocated() if args.device=="cuda" else None
    peak_gpu_reserved=torch.cuda.max_memory_reserved() if args.device=="cuda" else None
    args.output_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    checkpoint=args.output_dir/"cvi-tryon-warp-net-state.pt"
    save_private_checkpoint(checkpoint,torch,model,{"seed":args.seed,"base_channels":args.base_channels,"architecture":"cvi-garment-conditioned-warp-refine-unet-v0"})
    checkpoint_digest=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    report={
        "schema_version":"1.0","model_id":"cirvanna-tryon-warp-refine-v0",
        "architecture":"custom-unet-flow-warp-alpha-residual","initialization":"random",
        "source_revision":source_revision,"checkpoint_sha256":checkpoint_digest,"dataset":dataset,
        "training":{"epochs":args.epochs,"batch_size":args.batch_size,"learning_rate":args.learning_rate,"base_channels":args.base_channels,"seed":args.seed,"device":args.device,"max_gpu_memory_fraction":args.max_gpu_memory_fraction},
        "runtime":{"python":sys.version.split()[0],"torch":torch.__version__,"cuda_runtime":torch.version.cuda,"cuda_available":torch.cuda.is_available(),"gpu_name":torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,"gpu_total_memory_bytes":torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else None,"peak_gpu_memory_allocated_bytes":peak_gpu_allocated,"peak_gpu_memory_reserved_bytes":peak_gpu_reserved},
        "history":history,"held_out_test":test_metrics,"status":"research_candidate_not_qualified",
        "limitations":["256x256 baseline; no high-resolution detail preservation claim.","No pretrained perceptual backbone or diffusion prior is used.","Metrics do not prove garment identity, pattern/logo preservation, occlusion realism or human preference.","No independent subgroup confidence intervals are included in this baseline report.","No GPU training was run in the development environment.","No production inference, consent revocation or deletion proof is implied."]
    }
    write_private_text(args.output_dir/"training-report.json",json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":report["status"],"checkpoint_sha256":checkpoint_digest,"test_metrics":test_metrics,"output_dir":str(args.output_dir)}))
    return 0

if __name__=="__main__": raise SystemExit(main())
