#!/usr/bin/env python3
"""Train Cirvanna's first Look It component detector from random initialization."""
from __future__ import annotations
import argparse, hashlib, json, os, random, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.model_training.look_it.validate_dataset import validate_dataset, safe_media_path
from tools.model_training.provenance import require_clean_source_revision
from tools.model_evaluation.fashion_retrieval.private_artifacts import write_private_text

def build_model(num_classes: int):
    try:
        import torch
        from torchvision.models.detection import fasterrcnn_resnet50_fpn
        from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
    except ImportError as exc:
        raise RuntimeError("PyTorch and TorchVision must be installed in the approved training image") from exc
    model = fasterrcnn_resnet50_fpn(weights=None, weights_backbone=None, num_classes=91)
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
    return model

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--media-root", required=True, type=Path)
    parser.add_argument("--rights-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=0.0005)
    parser.add_argument("--seed", type=int, default=20261127)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--max-gpu-memory-fraction", type=float, default=0.8)
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1 or not 0 < args.learning_rate < 1:
        raise ValueError("invalid training hyperparameters")
    if not 0.1 <= args.max_gpu_memory_fraction <= 0.95:
        raise ValueError("max-gpu-memory-fraction must be between 0.1 and 0.95")
    source_revision = require_clean_source_revision(ROOT)
    dataset_info = validate_dataset(args.manifest, args.annotations, args.media_root, args.rights_manifest)
    if args.device == "cuda":
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("PyTorch is required for model training") from exc
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but no GPU is available; no CPU fallback is implicit")
    import torch
    from PIL import Image
    from torch.utils.data import DataLoader, Dataset
    import torchvision
    from torchvision.transforms.functional import pil_to_tensor

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if args.device == "cuda":
        torch.cuda.manual_seed_all(args.seed)
        # This constrains PyTorch's caching allocator; it is not a substitute
        # for container/device-level GPU isolation or an external hard quota.
        torch.cuda.set_per_process_memory_fraction(args.max_gpu_memory_fraction, device=0)
    rows = [json.loads(line) for line in args.annotations.read_text(encoding="utf-8").splitlines() if line.strip()]
    categories = ["background", *dataset_info["categories"]]
    category_ids = {name: index for index, name in enumerate(categories)}
    class LookItDataset(Dataset):
        def __init__(self, split: str):
            self.rows = [row for row in rows if row["split"] == split]
        def __len__(self):
            return len(self.rows)
        def __getitem__(self, index):
            row = self.rows[index]
            path = safe_media_path(args.media_root, row["image_path"])
            with Image.open(path) as image:
                tensor = pil_to_tensor(image.convert("RGB")).float() / 255.0
            boxes, labels = [], []
            width, height = row["width"], row["height"]
            for component in row["components"]:
                x1, y1, x2, y2 = component["bbox"]
                boxes.append([x1*width, y1*height, x2*width, y2*height])
                labels.append(category_ids[component["category"]])
            target = {
                "boxes": torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4),
                "labels": torch.tensor(labels, dtype=torch.int64),
                "image_id": torch.tensor([index], dtype=torch.int64),
            }
            return tensor, target
    def collate(batch):
        return tuple(zip(*batch))
    train_data = LookItDataset("train")
    validation_data = LookItDataset("validation")
    train_loader = DataLoader(train_data, batch_size=args.batch_size, shuffle=True, collate_fn=collate, num_workers=0)
    validation_loader = DataLoader(validation_data, batch_size=1, shuffle=False, collate_fn=collate, num_workers=0)
    device = torch.device(args.device)
    model = build_model(len(categories)).to(device)
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.learning_rate)
    history = []
    for epoch in range(args.epochs):
        model.train()
        train_loss = 0.0
        for images, targets in train_loader:
            images = [image.to(device) for image in images]
            targets = [{key: value.to(device) for key, value in target.items()} for target in targets]
            losses = model(images, targets)
            loss = sum(losses.values())
            if not torch.isfinite(loss):
                raise RuntimeError("non-finite training loss; aborting")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            train_loss += float(loss.detach().cpu())
        model.train()
        validation_loss = 0.0
        with torch.no_grad():
            for images, targets in validation_loader:
                images = [image.to(device) for image in images]
                targets = [{key: value.to(device) for key, value in target.items()} for target in targets]
                losses = model(images, targets)
                validation_loss += float(sum(losses.values()).detach().cpu())
        history.append({"epoch": epoch+1, "train_loss": train_loss/max(1,len(train_loader)), "validation_loss": validation_loss/max(1,len(validation_loader))})
    args.output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        if args.output_dir.stat().st_mode & 0o077:
            raise PermissionError("training output directory must be owner-only (0700)")
    checkpoint = args.output_dir / "lookit-detector-state.pt"
    if checkpoint.exists() or checkpoint.is_symlink():
        raise FileExistsError("refusing to overwrite an existing model checkpoint")
    fd, temporary_name = tempfile.mkstemp(prefix=".lookit-checkpoint-", suffix=".tmp", dir=args.output_dir)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            torch.save({"model_state_dict": model.cpu().state_dict(), "categories": categories, "seed": args.seed}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, checkpoint)
        temporary.unlink()
        if os.name == "posix":
            os.chmod(checkpoint, 0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    try:
        source_revision = subprocess.check_output(["git","rev-parse","HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        source_revision = "unknown"
    report = {
        "schema_version":"1.0", "model_id":"cirvanna-lookit-fasterrcnn-v0",
        "architecture":"torchvision-fasterrcnn-resnet50-fpn", "initialization":"random",
        "source_revision":source_revision, "checkpoint_sha256":digest,
        "dataset":dataset_info, "categories":categories,
        "training":{"epochs":args.epochs,"batch_size":args.batch_size,"learning_rate":args.learning_rate,"seed":args.seed,"device":args.device,"max_gpu_memory_fraction":args.max_gpu_memory_fraction},
        "runtime":{"python":sys.version.split()[0],"torch":torch.__version__,"torchvision":torchvision.__version__,"cuda_runtime":torch.version.cuda,"cuda_available":torch.cuda.is_available(),"gpu_name":torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,"gpu_total_memory_bytes":torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else None},
        "history":history, "status":"research_candidate_not_qualified",
        "limitations":["Bounding-box detector only; no pixel-mask segmentation.","Random initialization; no production quality claim.","Validation loss is not a substitute for held-out test evaluation.","No independent review, privacy attestation or commercial release approval is implied."]
    }
    write_private_text(args.output_dir / "training-report.json", json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status":report["status"],"checkpoint_sha256":digest,"output_dir":str(args.output_dir)}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
