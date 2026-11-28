#!/usr/bin/env python3
"""Train Cirvanna's first fashion image-embedding model with supervised contrastive learning."""
from __future__ import annotations
import argparse, hashlib, json, os, random, sys, tempfile
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.model_training.click_it.validate_dataset import validate_dataset, safe_media_path
from tools.model_training.provenance import require_clean_source_revision
from tools.model_evaluation.fashion_retrieval.private_artifacts import write_private_text

def supervised_contrastive_loss(features, labels, temperature: float):
    import torch
    import torch.nn.functional as F
    features=F.normalize(features,dim=1)
    logits=torch.matmul(features,features.T)/temperature
    logits=logits - logits.max(dim=1,keepdim=True).values.detach()
    identity=torch.eye(len(labels),device=labels.device,dtype=torch.bool)
    positive=(labels[:,None] == labels[None,:]) & ~identity
    logits=logits.masked_fill(identity,float("-inf"))
    log_prob=logits-torch.logsumexp(logits,dim=1,keepdim=True)
    positive_counts=positive.sum(dim=1)
    valid=positive_counts>0
    if not torch.any(valid):
        raise RuntimeError("contrastive batch contains no positive image pairs")
    mean_positive=(positive.to(log_prob.dtype)*log_prob).sum(dim=1)/positive_counts.clamp_min(1)
    return -mean_positive[valid].mean()

def build_model(embedding_dim: int):
    try:
        import torch.nn as nn
        from torchvision.models import resnet50
    except ImportError as exc:
        raise RuntimeError("PyTorch and TorchVision must be installed in the approved training image") from exc
    backbone=resnet50(weights=None)
    backbone.fc=nn.Identity()
    return nn.Sequential(backbone,nn.Linear(2048,1024),nn.ReLU(inplace=True),nn.Dropout(0.1),nn.Linear(1024,embedding_dim))

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",required=True,type=Path)
    parser.add_argument("--annotations",required=True,type=Path)
    parser.add_argument("--media-root",required=True,type=Path)
    parser.add_argument("--rights-manifest",required=True,type=Path)
    parser.add_argument("--output-dir",required=True,type=Path)
    parser.add_argument("--epochs",type=int,default=40)
    parser.add_argument("--products-per-batch",type=int,default=8)
    parser.add_argument("--images-per-product",type=int,default=2)
    parser.add_argument("--embedding-dim",type=int,default=512)
    parser.add_argument("--temperature",type=float,default=0.07)
    parser.add_argument("--learning-rate",type=float,default=0.0003)
    parser.add_argument("--seed",type=int,default=20261127)
    parser.add_argument("--device",choices=("cpu","cuda"),default="cuda")
    parser.add_argument("--max-gpu-memory-fraction",type=float,default=0.8)
    args=parser.parse_args()
    if args.epochs<1 or args.products_per_batch<2 or args.images_per_product<2 or args.embedding_dim<32:
        raise ValueError("invalid training dimensions or batch composition")
    if not 0.01<=args.temperature<=1 or not 0<args.learning_rate<1 or not 0.1<=args.max_gpu_memory_fraction<=0.95:
        raise ValueError("invalid optimization or GPU resource settings")
    source_revision=require_clean_source_revision(ROOT)
    dataset_info=validate_dataset(args.manifest,args.annotations,args.media_root,args.rights_manifest,args.images_per_product)
    import torch
    import torchvision
    import torch.nn.functional as F
    from torch.utils.data import DataLoader,Dataset,Sampler
    from torchvision.transforms import Compose,RandomResizedCrop,RandomHorizontalFlip,ColorJitter,ToTensor,Normalize,Resize,CenterCrop
    if args.device=="cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but no GPU is available; no CPU fallback is implicit")
    random.seed(args.seed); torch.manual_seed(args.seed)
    if args.device=="cuda":
        torch.cuda.manual_seed_all(args.seed)
        torch.cuda.set_per_process_memory_fraction(args.max_gpu_memory_fraction,device=0)
    rows=[json.loads(line) for line in args.annotations.read_text(encoding="utf-8").splitlines() if line.strip()]
    train_rows=[row for row in rows if row["split"]=="train"]
    validation_rows=[row for row in rows if row["split"]=="validation"]
    products=sorted({row["product_id"] for row in rows})
    product_to_label={product:index for index,product in enumerate(products)}
    class ProductImageDataset(Dataset):
        def __init__(self,selected,training: bool):
            self.rows=selected
            if training:
                self.transform=Compose([RandomResizedCrop(224,scale=(0.75,1.0)),RandomHorizontalFlip(0.5),ColorJitter(0.08,0.08,0.08,0.02),ToTensor(),Normalize((0.485,0.456,0.406),(0.229,0.224,0.225))])
            else:
                self.transform=Compose([Resize(256),CenterCrop(224),ToTensor(),Normalize((0.485,0.456,0.406),(0.229,0.224,0.225))])
        def __len__(self): return len(self.rows)
        def __getitem__(self,index):
            from PIL import Image
            row=self.rows[index]
            with Image.open(safe_media_path(args.media_root,row["image_path"])) as image:
                tensor=self.transform(image.convert("RGB"))
            return tensor,product_to_label[row["product_id"]]
    class ProductBatchSampler(Sampler):
        def __init__(self,selected,products_per_batch,images_per_product):
            grouped=defaultdict(list)
            for index,row in enumerate(selected): grouped[row["product_id"]].append(index)
            self.groups={key:value for key,value in grouped.items() if len(value)>=images_per_product}
            self.p=products_per_batch; self.k=images_per_product
            if len(self.groups)<self.p: raise ValueError("not enough distinct products for the configured contrastive batch")
        def __iter__(self):
            keys=list(self.groups)
            random.shuffle(keys)
            for start in range(0,len(keys)-self.p+1,self.p):
                batch=[]
                for key in keys[start:start+self.p]:
                    batch.extend(random.sample(self.groups[key],self.k))
                yield batch
        def __len__(self): return len(self.groups)//self.p
    def collate(batch):
        images,labels=zip(*batch)
        return torch.stack(images),torch.tensor(labels,dtype=torch.long)
    train_data=ProductImageDataset(train_rows,training=True)
    validation_data=ProductImageDataset(validation_rows,training=False)
    train_sampler=ProductBatchSampler(train_rows,args.products_per_batch,args.images_per_product)
    validation_sampler=ProductBatchSampler(validation_rows,args.products_per_batch,args.images_per_product)
    train_loader=DataLoader(train_data,batch_sampler=train_sampler,collate_fn=collate,num_workers=0)
    validation_loader=DataLoader(validation_data,batch_sampler=validation_sampler,collate_fn=collate,num_workers=0)
    device=torch.device(args.device)
    model=build_model(args.embedding_dim).to(device)
    optimizer=torch.optim.AdamW(model.parameters(),lr=args.learning_rate)
    history=[]
    for epoch in range(args.epochs):
        model.train(); train_losses=[]
        for images,labels in train_loader:
            images=images.to(device); labels=labels.to(device)
            embeddings=model(images)
            loss=supervised_contrastive_loss(embeddings,labels,args.temperature)
            if not torch.isfinite(loss): raise RuntimeError("non-finite contrastive loss; aborting")
            optimizer.zero_grad(set_to_none=True); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),max_norm=5.0)
            optimizer.step(); train_losses.append(float(loss.detach().cpu()))
        model.eval(); validation_losses=[]
        with torch.no_grad():
            for images,labels in validation_loader:
                loss=supervised_contrastive_loss(model(images.to(device)),labels.to(device),args.temperature)
                validation_losses.append(float(loss.detach().cpu()))
        history.append({"epoch":epoch+1,"train_loss":sum(train_losses)/max(1,len(train_losses)),"validation_loss":sum(validation_losses)/max(1,len(validation_losses))})
    args.output_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name=="posix" and args.output_dir.stat().st_mode & 0o077:
        raise PermissionError("training output directory must be owner-only (0700)")
    checkpoint=args.output_dir/"clickit-image-encoder-state.pt"
    if checkpoint.exists() or checkpoint.is_symlink(): raise FileExistsError("refusing to overwrite existing model checkpoint")
    fd,temp_name=tempfile.mkstemp(prefix=".clickit-checkpoint-",suffix=".tmp",dir=args.output_dir)
    temp=Path(temp_name)
    try:
        with os.fdopen(fd,"wb") as stream:
            torch.save({"model_state_dict":model.cpu().state_dict(),"embedding_dim":args.embedding_dim,"seed":args.seed},stream)
            stream.flush(); os.fsync(stream.fileno())
        os.link(temp,checkpoint); temp.unlink()
        if os.name=="posix": os.chmod(checkpoint,0o600)
    except Exception:
        temp.unlink(missing_ok=True); raise
    digest=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    try: revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    except Exception: revision="unknown"
    report={
        "schema_version":"1.0","model_id":"cirvanna-clickit-resnet50-supcon-v0",
        "architecture":"torchvision-resnet50-projection-head","initialization":"random",
        "source_revision":revision,"checkpoint_sha256":digest,"embedding_dim":args.embedding_dim,
        "dataset":dataset_info,
        "training":{"epochs":args.epochs,"products_per_batch":args.products_per_batch,"images_per_product":args.images_per_product,"temperature":args.temperature,"learning_rate":args.learning_rate,"seed":args.seed,"device":args.device,"max_gpu_memory_fraction":args.max_gpu_memory_fraction},
        "runtime":{"python":sys.version.split()[0],"torch":torch.__version__,"torchvision":torchvision.__version__,"cuda_runtime":torch.version.cuda,"cuda_available":torch.cuda.is_available(),"gpu_name":torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,"gpu_total_memory_bytes":torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else None},
        "history":history,"status":"research_candidate_not_qualified",
        "limitations":["Random initialization; requires a substantial rights-cleared catalogue corpus.","No calibrated match probability or abstention threshold is produced.","No test split was used for model selection.","This is image-to-image retrieval representation learning, not identity recognition or face search.","No independent review, privacy attestation or commercial release approval is implied."]
    }
    write_private_text(args.output_dir/"training-report.json",json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":report["status"],"checkpoint_sha256":digest,"output_dir":str(args.output_dir)}))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
