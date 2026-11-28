#!/usr/bin/env python3
"""Run Cirvanna-owned image-to-image Click It retrieval on a rights-cleared frozen test set."""
from __future__ import annotations
import argparse, hashlib, json, math, os, re, sys
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.model_evaluation.fashion_retrieval.data_rights import load_and_validate_data_rights_manifest
from tools.model_evaluation.fashion_retrieval.private_artifacts import write_private_text
from tools.model_training.provenance import require_clean_source_revision
from tools.model_training.click_it.train_retrieval import build_model

MAX_BYTES=25*1024*1024
MAX_PIXELS=20_000_000
MODEL_ID="cirvanna-clickit-resnet50-supcon-v0"
ARCHITECTURE="torchvision-resnet50-projection-head"

def digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def safe_image_path(root:Path,relative:Any)->Path:
    if not isinstance(relative,str) or not relative.strip() or "\\" in relative:
        raise ValueError("image path must be a POSIX relative path")
    p=Path(relative)
    if p.is_absolute() or ".." in p.parts: raise ValueError("image path traversal is forbidden")
    base=root.resolve(); current=base
    for part in p.parts:
        current=current/part
        if current.is_symlink(): raise ValueError("image symlinks are forbidden")
    resolved=current.resolve()
    if base not in resolved.parents or not resolved.is_file(): raise ValueError("image must be a regular file under media root")
    if resolved.stat().st_size>MAX_BYTES: raise ValueError("image exceeds byte limit")
    return resolved

def validate_image(path:Path,expected_sha:str,Image)->None:
    if digest(path)!=expected_sha: raise ValueError("image digest mismatch")
    with Image.open(path) as image:
        if image.format not in ("PNG","JPEG","WEBP"): raise ValueError("unsupported image format")
        if image.width*image.height>MAX_PIXELS: raise ValueError("image exceeds pixel limit")
        image.verify()

def validate_record(row:Any,line:int)->dict[str,Any]:
    if not isinstance(row,dict): raise ValueError(f"line {line}: record must be an object")
    for key in ("schema_version","query_id","cluster_id","split","query_image_path","query_image_sha256"):
        if not isinstance(row.get(key),str) or not row[key].strip(): raise ValueError(f"line {line}: {key} is required")
    if row["schema_version"]!="1.0" or row["split"]!="test": raise ValueError(f"line {line}: only schema 1.0 frozen test records are accepted")
    if row.get("face_masked_before_inference") is not True: raise ValueError(f"line {line}: query must be face-masked before inference")
    candidates=row.get("candidates")
    if not isinstance(candidates,list) or not candidates: raise ValueError(f"line {line}: candidates must be non-empty")
    ids=set(); products=set()
    for i,c in enumerate(candidates):
        if not isinstance(c,dict): raise ValueError(f"line {line}: candidate {i} must be an object")
        for key in ("candidate_id","product_id","image_path","image_sha256"):
            if not isinstance(c.get(key),str) or not c[key].strip(): raise ValueError(f"line {line}: candidate {i} missing {key}")
        if c["candidate_id"] in ids or c["product_id"] in products: raise ValueError(f"line {line}: candidate and product IDs must be unique")
        ids.add(c["candidate_id"]); products.add(c["product_id"])
        if c.get("face_masked_before_inference") is not True: raise ValueError(f"line {line}: candidate images must be face-masked before inference")
        grade=c.get("relevance")
        if isinstance(grade,bool) or not isinstance(grade,int) or not 0<=grade<=4: raise ValueError(f"line {line}: relevance must be integer 0..4")
    if not any(c["relevance"]>0 for c in candidates): raise ValueError(f"line {line}: at least one relevant candidate is required")
    if not isinstance(row.get("subgroups"),dict) or not row["subgroups"]: raise ValueError(f"line {line}: subgroup labels are required")
    return row

def validate_privacy_preprocessing_manifest(
    manifest_path:Path, records:list[dict[str,Any]], media_root:Path
)->dict[str,Any]:
    """Bind every embedded image to an approved, face-masked preprocessing record."""
    value=json.loads(manifest_path.read_text(encoding="utf-8"))
    required={
        "schema_version","approval_status","scope","reviewed_by","reviewed_at_utc",
        "evidence_path","evidence_sha256","face_masked_before_inference","face_recognition",
        "detector_model_id","detector_source_revision","detector_weights_sha256","images",
    }
    if not isinstance(value,dict) or required-set(value):
        missing=sorted(required-set(value)) if isinstance(value,dict) else sorted(required)
        raise ValueError("privacy preprocessing manifest missing fields: "+", ".join(missing))
    if value["schema_version"]!="1.0" or value["approval_status"]!="approved":
        raise ValueError("privacy preprocessing manifest must be approved schema 1.0")
    if value["scope"]!="click_it_retrieval_evaluation":
        raise ValueError("privacy preprocessing scope must be click_it_retrieval_evaluation")
    if not isinstance(value["reviewed_by"],str) or not value["reviewed_by"].strip():
        raise ValueError("privacy preprocessing reviewer must be identified")
    try:
        reviewed=datetime.fromisoformat(str(value["reviewed_at_utc"]).replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("privacy preprocessing reviewed_at_utc must be ISO-8601") from exc
    if reviewed.tzinfo is None or reviewed>datetime.now(timezone.utc):
        raise ValueError("privacy preprocessing review timestamp is invalid")
    if value["face_masked_before_inference"] is not True or value["face_recognition"] is not False:
        raise ValueError("Click It evaluation requires face masking and prohibits face recognition")
    if not isinstance(value["detector_model_id"],str) or not value["detector_model_id"].strip():
        raise ValueError("privacy preprocessing detector_model_id is required")
    if not isinstance(value["detector_source_revision"],str) or not re.fullmatch(r"[0-9a-f]{40}",value["detector_source_revision"]):
        raise ValueError("privacy preprocessing detector source revision must be a full commit SHA")
    if not isinstance(value["detector_weights_sha256"],str) or not re.fullmatch(r"[0-9a-f]{64}",value["detector_weights_sha256"]):
        raise ValueError("privacy preprocessing detector weights digest must be a full SHA-256")
    evidence=Path(str(value["evidence_path"])).expanduser()
    if not evidence.is_absolute(): evidence=manifest_path.resolve().parent/evidence
    evidence=evidence.resolve()
    if not evidence.is_file() or value["evidence_sha256"]!=digest(evidence):
        raise ValueError("privacy preprocessing reviewer evidence is missing or has a digest mismatch")
    expected={}
    for row in records:
        expected[row["query_image_path"]]=row["query_image_sha256"]
        for candidate in row["candidates"]:
            expected[candidate["image_path"]]=candidate["image_sha256"]
    images=value["images"]
    if not isinstance(images,dict) or set(images)!=set(expected):
        raise ValueError("privacy preprocessing manifest must cover every query and candidate image exactly once")
    masked_total=0
    for relative,expected_sha in expected.items():
        item=images[relative]
        if not isinstance(item,dict) or item.get("processed_image_sha256")!=expected_sha:
            raise ValueError(f"preprocessed image digest does not match test record for {relative}")
        count=item.get("faces_masked")
        if isinstance(count,bool) or not isinstance(count,int) or count<0:
            raise ValueError(f"faces_masked must be a non-negative integer for {relative}")
        image_path=safe_image_path(media_root,relative)
        if digest(image_path)!=expected_sha:
            raise ValueError(f"preprocessed image bytes do not match approved digest for {relative}")
        masked_total+=count
    return {
        "manifest_sha256":digest(manifest_path),
        "evidence_sha256":value["evidence_sha256"],
        "detector_model_id":value["detector_model_id"],
        "detector_source_revision":value["detector_source_revision"],
        "detector_weights_sha256":value["detector_weights_sha256"],
        "face_masked_before_inference":True,
        "face_recognition":False,
        "image_count":len(expected),
        "faces_masked_total":masked_total,
    }


def _dcg(grades:list[int])->float:
    return sum((2**grade-1)/math.log2(index+2) for index,grade in enumerate(grades))

def ranking_metrics(ranked_ids:list[str],grades:dict[str,int],ks=(1,5,10))->dict[str,Any]:
    ordered=[grades[item] for item in ranked_ids]
    relevant=sum(value>0 for value in grades.values())
    out={}
    for k in ks:
        top=ordered[:k]
        hits=sum(value>0 for value in top)
        out[f"recall@{k}"]=hits/relevant if relevant else 0.0
        out[f"precision@{k}"]=hits/k
        ideal=sorted(grades.values(),reverse=True)[:k]
        out[f"ndcg@{k}"]=_dcg(top)/_dcg(ideal) if _dcg(ideal)>0 else 0.0
    out["mrr"]=next((1/(i+1) for i,value in enumerate(ordered) if value>0),0.0)
    out["top1_hit"]=bool(ordered and ordered[0]>0)
    return out

def run(args)->dict[str,Any]:
    rights=load_and_validate_data_rights_manifest(args.rights_manifest,expected_scope="click_it_retrieval_evaluation")
    source_revision=require_clean_source_revision(ROOT)
    try:
        import torch
        from PIL import Image
        from torchvision.transforms import Compose,Resize,CenterCrop,ToTensor,Normalize
    except ImportError as exc: raise RuntimeError("PyTorch, TorchVision and Pillow are required in the approved Click It evaluation runtime") from exc
    if args.device=="cuda" and not torch.cuda.is_available(): raise RuntimeError("CUDA requested but unavailable; no implicit CPU fallback")
    training=json.loads(args.training_report.read_text(encoding="utf-8"))
    if training.get("model_id")!=MODEL_ID or training.get("architecture")!=ARCHITECTURE: raise ValueError("training report model identity mismatch")
    model_revision=training.get("source_revision")
    if not isinstance(model_revision,str) or len(model_revision)!=40 or any(c not in "0123456789abcdef" for c in model_revision): raise ValueError("training report source revision is not pinned")
    if model_revision!=source_revision: raise ValueError("evaluation checkout must match the exact model training source revision")
    if digest(args.checkpoint)!=training.get("checkpoint_sha256"): raise ValueError("checkpoint digest does not match training report")
    embedding_dim=training.get("embedding_dim")
    if not isinstance(embedding_dim,int) or not 32<=embedding_dim<=4096: raise ValueError("training report embedding dimension is invalid")
    records=[]
    raw=args.input.read_bytes()
    for line,value in enumerate(raw.decode("utf-8").splitlines(),1):
        if value.strip(): records.append(validate_record(json.loads(value),line))
    if not records: raise ValueError("test dataset is empty")
    if len({r["query_id"] for r in records})!=len(records): raise ValueError("query IDs must be unique")
    root=args.media_root
    privacy_preprocessing=validate_privacy_preprocessing_manifest(
        args.privacy_preprocessing_manifest,records,root
    )
    all_paths={}
    candidate_snapshot = None
    for row in records:
        current_snapshot = tuple(sorted((c["candidate_id"], c["product_id"], c["image_sha256"]) for c in row["candidates"]))
        if candidate_snapshot is None:
            candidate_snapshot = current_snapshot
        elif current_snapshot != candidate_snapshot:
            raise ValueError("all queries must use the exact same frozen candidate image snapshot")
        query=safe_image_path(root,row["query_image_path"])
        validate_image(query,row["query_image_sha256"],Image)
        all_paths[("query",row["query_id"])]=query
        for candidate in row["candidates"]:
            path=safe_image_path(root,candidate["image_path"])
            validate_image(path,candidate["image_sha256"],Image)
            all_paths[("candidate",(row["query_id"],candidate["candidate_id"]))]=path
    device=torch.device(args.device)
    model=build_model(embedding_dim)
    checkpoint=torch.load(args.checkpoint,map_location="cpu",weights_only=True)
    if not isinstance(checkpoint,dict) or "model_state_dict" not in checkpoint: raise ValueError("checkpoint must contain a state dictionary")
    model.load_state_dict(checkpoint["model_state_dict"],strict=True)
    model.to(device).eval()
    transform=Compose([Resize(256),CenterCrop(224),ToTensor(),Normalize((0.485,0.456,0.406),(0.229,0.224,0.225))])
    cache={}
    def embed(path:Path)->list[float]:
        key=digest(path)
        if key in cache: return cache[key]
        with Image.open(path) as im: tensor=transform(im.convert("RGB")).unsqueeze(0).to(device)
        with torch.inference_mode(): vector=torch.nn.functional.normalize(model(tensor),dim=1)[0].detach().float().cpu().tolist()
        tensor.zero_()
        cache[key]=[float(x) for x in vector]
        return cache[key]
    results=[]; per_query=[]; subgroup_values={}
    with torch.inference_mode():
        for row in records:
            q=embed(all_paths[("query",row["query_id"])])
            scores={}
            grades={}
            for c in row["candidates"]:
                v=embed(all_paths[("candidate",(row["query_id"],c["candidate_id"]))])
                scores[c["candidate_id"]]=sum(a*b for a,b in zip(q,v))
                grades[c["candidate_id"]]=c["relevance"]
            ranked=sorted(scores,key=lambda key:(-scores[key],key))
            metrics=ranking_metrics(ranked,grades)
            per_query.append(metrics)
            for key,value in row["subgroups"].items():
                subgroup_values.setdefault(f"{key}={value}",[]).append(metrics)
            results.append({"query_id":row["query_id"],"cluster_id":row["cluster_id"],"ranked_candidate_ids":ranked,"scores":{key:round(value,8) for key,value in scores.items()},"qrels":grades,"subgroups":row["subgroups"]})
    keys=[key for key in per_query[0] if key!="top1_hit"]
    mean={key:sum(float(m[key]) for m in per_query)/len(per_query) for key in keys}
    mean["top1_hit_rate"]=sum(bool(m["top1_hit"]) for m in per_query)/len(per_query)
    report={
      "schema_version":"1.0","task":"image_to_catalog_image","model_id":MODEL_ID,
      "architecture":ARCHITECTURE,"model_source_revision":model_revision,
      "checkpoint_sha256":training["checkpoint_sha256"],"training_report_sha256":digest(args.training_report),
      "test_input_sha256":hashlib.sha256(raw).hexdigest(),"rights_manifest_sha256":rights["manifest_sha256"],
      "privacy_preprocessing":privacy_preprocessing,
      "rights_evidence_sha256":rights["evidence_sha256"],"sample_count":len(records),
      "independent_query_clusters":len({r["cluster_id"] for r in records}),
      "candidate_image_count":len(candidate_snapshot or ()),"candidate_snapshot_sha256":hashlib.sha256(json.dumps(candidate_snapshot,separators=(",",":")).encode()).hexdigest(),
      "device":args.device,"metrics_macro_query_mean":mean,
      "subgroups":{key:{metric:sum(float(x[metric]) for x in values)/len(values) for metric in keys} for key,values in sorted(subgroup_values.items())},
      "results":results,"status":"research_evaluation_not_independent_qualification",
      "limitations":["The model is randomly initialized unless trained on a substantial approved corpus.","Metrics are a frozen test-set result and do not imply production readiness.","No confidence intervals are computed; cluster-bootstrap analysis and minimum subgroup counts remain required.","Face masking is asserted by the supplied preprocessing contract; independent image-byte verification of masking is not performed by this runner."]
    }
    return report

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True,type=Path); p.add_argument("--media-root",required=True,type=Path)
    p.add_argument("--rights-manifest",required=True,type=Path); p.add_argument("--privacy-preprocessing-manifest",required=True,type=Path)
    p.add_argument("--checkpoint",required=True,type=Path)
    p.add_argument("--training-report",required=True,type=Path); p.add_argument("--output",required=True,type=Path)
    p.add_argument("--device",choices=("cpu","cuda"),default="cuda"); p.add_argument("--overwrite",action="store_true")
    args=p.parse_args()
    report=run(args)
    write_private_text(args.output,json.dumps(report,indent=2,sort_keys=True)+"\n",overwrite=args.overwrite)
    print(json.dumps({"status":report["status"],"sample_count":report["sample_count"],"metrics":report["metrics_macro_query_mean"]}))
    return 0
if __name__=="__main__": raise SystemExit(main())
