"""Private, GPU-only inference worker for Cirvanna's own Try-On model."""
from __future__ import annotations
import asyncio, base64, hashlib, hmac, io, json, os, re, sqlite3, threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image
from starlette.concurrency import run_in_threadpool

def _find_runtime_root()->Path:
    current=Path(__file__).resolve()
    for parent in current.parents:
        if (parent/"tools/model_training/virtual_try_on/model.py").is_file() or (parent/"model.py").is_file():
            return parent
    return Path("/app")

ROOT=_find_runtime_root()
MODEL_ID="cirvanna-tryon-warp-refine-v0"
ARCHITECTURE="cvi-garment-conditioned-warp-refine-unet-v0"
MODEL_FIELDS=(
    "schema_version","model_id","architecture","source_revision","checkpoint_sha256",
    "training_report_sha256","evaluation_report_sha256","dataset_manifest_sha256",
    "person_rights_manifest_sha256","garment_rights_manifest_sha256","base_channels",
    "input_resolution","pose_channels","max_gpu_memory_fraction","minimum_gpu_memory_bytes",
    "max_concurrency","runtime_image_digest"
)
MODEL_FILES={
    "checkpoint_sha256":"model.pt",
    "training_report_sha256":"training-report.json",
    "evaluation_report_sha256":"evaluation-report.json",
    "dataset_manifest_sha256":"dataset.manifest.json",
    "person_rights_manifest_sha256":"person-rights.manifest.json",
    "garment_rights_manifest_sha256":"garment-rights.manifest.json",
}
ASSET_ROLES=("person_image","garment_image","person_mask","garment_mask","pose_heatmap")
SHA256_RE=re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE=re.compile(r"^[0-9a-f]{40}$")
MAX_IMAGE_BYTES=int(os.getenv("CVI_VTON_MAX_IMAGE_BYTES","10485760"))
MAX_POSE_BYTES=int(os.getenv("CVI_VTON_MAX_POSE_BYTES","5242880"))
MAX_IMAGE_PIXELS=int(os.getenv("CVI_VTON_MAX_IMAGE_PIXELS","20000000"))
MAX_REQUEST_BYTES=int(os.getenv("CVI_VTON_MAX_REQUEST_BYTES",str(60*1024*1024)))
INPUT_RESOLUTION=256
POSE_CHANNELS=17

class _RequestTooLarge(Exception):
    pass

class MaxRequestBodyMiddleware:
    def __init__(self,app,max_bytes:int):
        self.app=app
        self.max_bytes=max_bytes
    async def __call__(self,scope,receive,send):
        if scope.get("type")!="http" or scope.get("path")!="/v1/render":
            await self.app(scope,receive,send)
            return
        headers=dict(scope.get("headers",[]))
        raw_length=headers.get(b"content-length")
        if raw_length is not None:
            try: content_length=int(raw_length)
            except ValueError: content_length=self.max_bytes+1
            if content_length>self.max_bytes:
                await self._reject(send)
                return
        total=0
        async def limited_receive():
            nonlocal total
            message=await receive()
            if message.get("type")=="http.request":
                total+=len(message.get("body",b""))
                if total>self.max_bytes: raise _RequestTooLarge()
            return message
        try:
            await self.app(scope,limited_receive,send)
        except _RequestTooLarge:
            await self._reject(send)
    async def _reject(self,send):
        body=b'{"detail":"request body exceeds configured size limit"}'
        await send({"type":"http.response.start","status":413,"headers":[(b"content-type",b"application/json"),(b"content-length",str(len(body)).encode())]})
        await send({"type":"http.response.body","body":body})

app=FastAPI(title="Cirvanna CVI Try-On GPU Worker",docs_url=None,redoc_url=None,openapi_url=None)
app.add_middleware(MaxRequestBodyMiddleware,max_bytes=MAX_REQUEST_BYTES)
_runtime=None
_runtime_error="not_initialized"
_runtime_lock=threading.Lock()
_inference_slot=threading.BoundedSemaphore(1)

def sha256_bytes(data:bytes|bytearray)->str:
    return hashlib.sha256(data).hexdigest()

def canonical_json(value:dict[str,Any])->bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")

def model_attestation_payload(manifest:dict[str,Any])->bytes:
    attestation=manifest.get("qualification_attestation")
    if not isinstance(attestation,dict): raise ValueError("qualification attestation metadata is missing")
    signed_metadata={key:attestation[key] for key in ("result","key_id","signed_at","expires_at")}
    return canonical_json({"model":{key:manifest[key] for key in MODEL_FIELDS},"attestation":signed_metadata})

def verify_ed25519(payload:bytes,signature_b64:str,public_key_b64:str)->None:
    try:
        public_key=base64.b64decode(public_key_b64,validate=True)
        signature=base64.b64decode(signature_b64,validate=True)
        if len(public_key)!=32 or len(signature)!=64:
            raise ValueError("invalid Ed25519 key or signature length")
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature,payload)
    except (ValueError,InvalidSignature) as exc:
        raise ValueError("independent Ed25519 signature verification failed") from exc

def verify_model_bundle(bundle_dir:Path,public_key_b64:str,key_id:str)->dict[str,Any]:
    if bundle_dir.is_symlink() or not bundle_dir.is_dir(): raise ValueError("model bundle directory is missing or unsafe")
    bundle_dir=bundle_dir.resolve()
    manifest_path=bundle_dir/"manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file(): raise ValueError("model manifest is missing or unsafe")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest,dict) or not all(key in manifest for key in MODEL_FIELDS):
        raise ValueError("model manifest is incomplete")
    if manifest["schema_version"]!="1.0" or manifest["model_id"]!=MODEL_ID or manifest["architecture"]!=ARCHITECTURE:
        raise ValueError("model identity or architecture is not approved")
    if not isinstance(manifest["source_revision"],str) or not COMMIT_RE.fullmatch(manifest["source_revision"]):
        raise ValueError("model source revision is not pinned")
    if not isinstance(manifest["base_channels"],int) or not 8<=manifest["base_channels"]<=64:
        raise ValueError("model base channel count is outside worker bounds")
    if manifest["input_resolution"]!=INPUT_RESOLUTION or manifest["pose_channels"]!=POSE_CHANNELS:
        raise ValueError("model input contract is incompatible with this worker")
    fraction=manifest["max_gpu_memory_fraction"]
    if not isinstance(fraction,(float,int)) or not 0.1<=fraction<=0.8:
        raise ValueError("model GPU memory fraction exceeds worker policy")
    if not isinstance(manifest["minimum_gpu_memory_bytes"],int) or not 8*1024**3<=manifest["minimum_gpu_memory_bytes"]<=128*1024**3:
        raise ValueError("model minimum GPU memory requirement is invalid")
    if manifest["max_concurrency"]!=1:
        raise ValueError("worker policy supports exactly one concurrent inference")
    if not isinstance(manifest["runtime_image_digest"],str) or not SHA256_RE.fullmatch(manifest["runtime_image_digest"]):
        raise ValueError("runtime image digest must be pinned")
    for field in MODEL_FILES:
        if not isinstance(manifest[field],str) or not SHA256_RE.fullmatch(manifest[field]):
            raise ValueError(f"{field} must be a lowercase SHA-256 digest")
        path=bundle_dir/MODEL_FILES[field]
        if path.is_symlink() or not path.is_file() or path.resolve().parent!=bundle_dir:
            raise ValueError(f"model bundle artifact is missing or unsafe: {MODEL_FILES[field]}")
        if sha256_bytes(path.read_bytes())!=manifest[field]:
            raise ValueError(f"model bundle artifact digest mismatch: {MODEL_FILES[field]}")
    attestation=manifest.get("qualification_attestation")
    if not isinstance(attestation,dict) or attestation.get("result")!="qualified":
        raise ValueError("independent qualification attestation is missing")
    if attestation.get("key_id")!=key_id:
        raise ValueError("qualification signing key ID mismatch")
    try:
        signed_at=datetime.fromisoformat(attestation["signed_at"].replace("Z","+00:00"))
        expires_at=datetime.fromisoformat(attestation["expires_at"].replace("Z","+00:00"))
    except Exception as exc:
        raise ValueError("qualification attestation timestamps are invalid") from exc
    now=datetime.now(timezone.utc)
    if signed_at.tzinfo is None or expires_at.tzinfo is None or signed_at>now+timedelta(seconds=5):
        raise ValueError("qualification attestation signing time is invalid")
    if expires_at<=now or not 0<(expires_at-signed_at).total_seconds()<=90*24*60*60:
        raise ValueError("qualification attestation is expired or outside its 90-day validity window")
    payload=model_attestation_payload(manifest)
    payload_digest=sha256_bytes(payload)
    if attestation.get("payload_sha256")!=payload_digest:
        raise ValueError("qualification attestation payload digest mismatch")
    signature=attestation.get("signature_base64")
    if not isinstance(signature,str): raise ValueError("qualification signature is missing")
    verify_ed25519(payload,signature,public_key_b64)
    return manifest

def privacy_attestation_payload(attestation:dict[str,Any])->bytes:
    return canonical_json({key:value for key,value in attestation.items() if key!="signature_base64"})

def verify_privacy_attestation(
    attestation_json:str,public_key_b64:str,key_id:str,asset_digests:dict[str,str],preprocessing_digest:str
)->str:
    if len(attestation_json)>32768: raise ValueError("privacy attestation exceeds size limit")
    attestation=json.loads(attestation_json)
    if not isinstance(attestation,dict) or attestation.get("schema_version")!="1.0":
        raise ValueError("privacy attestation schema is invalid")
    if attestation.get("key_id")!=key_id or attestation.get("purpose")!="virtual_try_on_inference" or attestation.get("consent_scope")!="virtual_try_on_inference":
        raise ValueError("privacy attestation scope or key ID is invalid")
    if not isinstance(attestation.get("consent_policy_version"),str) or not attestation["consent_policy_version"].strip():
        raise ValueError("privacy attestation policy version is required")
    if attestation.get("consent_status")!="active" or attestation.get("revocation_status")!="not_revoked":
        raise ValueError("privacy consent is inactive or revoked")
    if not isinstance(attestation.get("user_binding_sha256"),str) or not SHA256_RE.fullmatch(attestation["user_binding_sha256"]):
        raise ValueError("privacy attestation user binding is invalid")
    if not isinstance(attestation.get("revocation_epoch"),int) or attestation["revocation_epoch"]<0:
        raise ValueError("privacy attestation revocation epoch is invalid")
    receipt_id=attestation.get("receipt_id")
    if not isinstance(receipt_id,str) or not receipt_id.strip(): raise ValueError("privacy receipt ID is required")
    if attestation.get("preprocessing_manifest_sha256")!=preprocessing_digest:
        raise ValueError("preprocessing manifest digest mismatch")
    if attestation.get("asset_sha256")!=asset_digests:
        raise ValueError("privacy receipt does not bind the exact submitted assets")
    if attestation.get("face_masked_before_inference") is not True or attestation.get("garment_face_masked_before_inference") is not True:
        raise ValueError("privacy receipt must attest face masking before inference")
    issued_at=attestation.get("issued_at")
    expiry=attestation.get("expires_at")
    if not isinstance(issued_at,str) or not isinstance(expiry,str):
        raise ValueError("privacy receipt issue and expiry timestamps are required")
    try:
        issued=datetime.fromisoformat(issued_at.replace("Z","+00:00"))
        expires=datetime.fromisoformat(expiry.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("privacy receipt timestamps are invalid") from exc
    now=datetime.now(timezone.utc)
    if issued.tzinfo is None or expires.tzinfo is None or issued>now.replace(microsecond=0)+timedelta(seconds=5):
        raise ValueError("privacy receipt issue time is invalid")
    if (now-issued).total_seconds()>15 or expires<=now or not 0<(expires-issued).total_seconds()<=30:
        raise ValueError("privacy receipt is expired or outside the short-lived receipt window")
    signature=attestation.get("signature_base64")
    if not isinstance(signature,str): raise ValueError("privacy receipt signature is missing")
    verify_ed25519(privacy_attestation_payload(attestation),signature,public_key_b64)
    consume_receipt_once(receipt_id, expires)
    return receipt_id

def _receipt_ledger_path() -> Path:
    configured = os.getenv("CVI_VTON_REPLAY_DB_PATH", "/var/lib/cvi-tryon/replay-ledger.sqlite3").strip()
    if not configured:
        raise RuntimeError("durable privacy receipt ledger is not configured")
    db_path = Path(configured)
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if db_path.parent.is_symlink() or db_path.is_symlink():
            raise RuntimeError("privacy receipt ledger path must not contain a symlink")
    except OSError as exc:
        raise RuntimeError("durable privacy receipt ledger is unavailable") from exc
    return db_path


def check_receipt_ledger() -> None:
    """Verify that the durable replay ledger is readable, writable and healthy."""
    db_path = _receipt_ledger_path()
    try:
        with sqlite3.connect(str(db_path), timeout=5.0, isolation_level=None) as connection:
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS consumed_privacy_receipts ("
                "receipt_id TEXT PRIMARY KEY, expires_at TEXT NOT NULL)"
            )
            result = connection.execute("PRAGMA quick_check").fetchone()
            if not result or result[0] != "ok":
                raise RuntimeError("durable privacy receipt ledger integrity check failed")
        os.chmod(db_path, 0o600)
    except (OSError, sqlite3.Error) as exc:
        raise RuntimeError("durable privacy receipt ledger is unavailable") from exc


def consume_receipt_once(receipt_id: str, expires_at: datetime) -> None:
    """Atomically consume a privacy receipt in durable storage.

    The ledger stores only an opaque receipt ID and expiry timestamp. It never
    stores image bytes, asset URLs, user IDs, or consent payloads. A missing,
    unsafe, read-only, or unavailable ledger is a hard failure.
    """
    db_path = _receipt_ledger_path()
    now = datetime.now(timezone.utc)
    now_text = now.isoformat(timespec="microseconds")
    expiry_text = expires_at.astimezone(timezone.utc).isoformat(timespec="microseconds")
    try:
        with sqlite3.connect(str(db_path), timeout=5.0, isolation_level=None) as connection:
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS consumed_privacy_receipts ("
                "receipt_id TEXT PRIMARY KEY, expires_at TEXT NOT NULL)"
            )
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM consumed_privacy_receipts WHERE expires_at <= ?", (now_text,)
            )
            try:
                connection.execute(
                    "INSERT INTO consumed_privacy_receipts(receipt_id, expires_at) VALUES (?, ?)",
                    (receipt_id, expiry_text),
                )
            except sqlite3.IntegrityError as exc:
                connection.execute("ROLLBACK")
                raise ValueError("privacy receipt replay detected") from exc
            connection.execute("COMMIT")
        os.chmod(db_path, 0o600)
    except ValueError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise RuntimeError("durable privacy receipt ledger is unavailable") from exc

async def read_limited(upload:UploadFile,limit:int)->bytearray:
    result=bytearray()
    while True:
        chunk=await upload.read(64*1024)
        if not chunk: break
        if len(result)+len(chunk)>limit:
            raise HTTPException(status_code=413,detail="upload exceeds configured size limit")
        result.extend(chunk)
    if not result: raise HTTPException(status_code=422,detail="empty upload")
    return result

def validate_image_bytes(data:bytearray,role:str)->tuple[int,int]:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ("PNG","JPEG","WEBP"): raise ValueError("unsupported image format")
            width,height=image.size
            if min(width,height)<256 or width*height>MAX_IMAGE_PIXELS:
                raise ValueError("image dimensions are outside worker bounds")
            if role.endswith("_mask") and (image.format!="PNG" or image.mode not in ("L","1")):
                raise ValueError("mask must be a grayscale PNG")
            image.verify()
        return width,height
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"{role} image is invalid") from exc

def validate_pose_bytes(data:bytearray)->None:
    try:
        with np.load(io.BytesIO(data),allow_pickle=False) as archive:
            heatmaps=np.asarray(archive["heatmaps"],dtype=np.float32)
    except Exception as exc:
        raise ValueError("pose heatmap archive is invalid") from exc
    if heatmaps.shape!=(POSE_CHANNELS,64,64) or not np.isfinite(heatmaps).all() or np.any(heatmaps<0) or np.any(heatmaps>1):
        raise ValueError("pose heatmaps must contain 17x64x64 finite values in [0,1]")

def wipe_sensitive_buffers(buffers:dict[str,bytearray])->None:
    for value in buffers.values():
        for index in range(len(value)): value[index]=0
        value.clear()

def load_runtime():
    global _runtime,_runtime_error
    if _runtime is not None: return _runtime,None
    with _runtime_lock:
        if _runtime is not None: return _runtime,None
        try:
            token=os.getenv("CVI_VTON_WORKER_TOKEN","")
            if len(token)<32: raise RuntimeError("worker bearer credential is not configured")
            bundle=Path(os.getenv("CVI_VTON_MODEL_BUNDLE","/models/cvi-tryon"))
            qualification_key=os.getenv("CVI_VTON_QUALIFICATION_PUBLIC_KEY_B64","")
            qualification_key_id=os.getenv("CVI_VTON_QUALIFICATION_KEY_ID","")
            privacy_key=os.getenv("CVI_VTON_PRIVACY_PUBLIC_KEY_B64","")
            privacy_key_id=os.getenv("CVI_VTON_PRIVACY_KEY_ID","")
            if not all((qualification_key,qualification_key_id,privacy_key,privacy_key_id)):
                raise RuntimeError("qualification or privacy verification keys are not configured")
            manifest=verify_model_bundle(bundle,qualification_key,qualification_key_id)
            runtime_digest=os.getenv("CVI_VTON_RUNTIME_IMAGE_DIGEST","")
            if runtime_digest!=manifest["runtime_image_digest"]:
                raise RuntimeError("runtime container image digest does not match qualified manifest")
            import torch
            if not torch.cuda.is_available(): raise RuntimeError("NVIDIA CUDA device is unavailable")
            device=torch.device("cuda:0")
            properties=torch.cuda.get_device_properties(device)
            minimum=int(manifest["minimum_gpu_memory_bytes"])
            if properties.total_memory<minimum: raise RuntimeError("GPU memory is below the qualified minimum")
            torch.cuda.set_per_process_memory_fraction(float(manifest["max_gpu_memory_fraction"]),device=0)
            sys_path=str(ROOT)
            if sys_path not in __import__("sys").path: __import__("sys").path.insert(0,sys_path)
            try:
                from tools.model_training.virtual_try_on.model import build_model
            except ModuleNotFoundError:
                from model import build_model
            model=build_model(int(manifest["base_channels"]),int(manifest["pose_channels"]))
            checkpoint=torch.load(bundle/"model.pt",map_location="cpu",weights_only=True)
            if not isinstance(checkpoint,dict) or "model_state_dict" not in checkpoint:
                raise RuntimeError("checkpoint does not contain a safe state dictionary")
            model.load_state_dict(checkpoint["model_state_dict"],strict=True)
            model.to(device).eval()
            _runtime={
                "model":model,"torch":torch,"device":device,"manifest":manifest,
                "privacy_public_key":privacy_key,"privacy_key_id":privacy_key_id,
                "gpu_name":properties.name,"gpu_memory_bytes":properties.total_memory,
                "bundle_manifest_sha256":sha256_bytes((bundle/"manifest.json").read_bytes())
            }
            _runtime_error=""
            return _runtime,None
        except Exception as exc:
            _runtime_error=type(exc).__name__
            return None,_runtime_error

def run_inference(runtime:dict[str,Any],buffers:dict[str,bytearray])->bytes:
    import torch
    tensors=[]
    try:
        def image_tensor(role:str,mask:bool=False):
            with Image.open(io.BytesIO(buffers[role])) as image:
                image=image.convert("L" if mask else "RGB")
                image=image.resize((INPUT_RESOLUTION,INPUT_RESOLUTION),Image.Resampling.NEAREST if mask else Image.Resampling.BICUBIC)
                array=np.asarray(image,dtype=np.float32).copy()
            if mask: cpu_tensor=torch.from_numpy(array).unsqueeze(0).unsqueeze(0)/255.0
            else: cpu_tensor=torch.from_numpy(array).permute(2,0,1).unsqueeze(0)/127.5-1.0
            tensor=cpu_tensor.to(runtime["device"])
            cpu_tensor.zero_(); array.fill(0)
            tensors.append(tensor)
            return tensor
        person=image_tensor("person_image")
        garment=image_tensor("garment_image")
        person_mask=image_tensor("person_mask",True)
        garment_mask=image_tensor("garment_mask",True)
        with np.load(io.BytesIO(buffers["pose_heatmap"]),allow_pickle=False) as archive:
            pose_array=np.asarray(archive["heatmaps"],dtype=np.float32).copy()
        pose=torch.from_numpy(pose_array).unsqueeze(0).to(runtime["device"])
        pose=torch.nn.functional.interpolate(pose,size=(INPUT_RESOLUTION,INPUT_RESOLUTION),mode="bilinear",align_corners=False)
        tensors.append(pose)
        with torch.inference_mode():
            outputs=runtime["model"](person,garment,person_mask,garment_mask,pose)
            output=outputs["image"]
            pixels=((output[0].detach().float().cpu().permute(1,2,0).numpy()+1.0)*127.5).clip(0,255).astype(np.uint8)
        image=Image.fromarray(pixels,"RGB")
        stream=io.BytesIO()
        image.save(stream,format="PNG",optimize=True)
        image.close()
        result=stream.getvalue()
        stream.close()
        return result
    finally:
        for tensor in tensors:
            try: tensor.zero_()
            except Exception: pass
        if "outputs" in locals():
            for value in outputs.values():
                try: value.zero_()
                except Exception: pass
        elif "output" in locals():
            try: output.zero_()
            except Exception: pass
        if "pixels" in locals(): pixels.fill(0)
        if "pose_array" in locals(): pose_array.fill(0)
        if torch.cuda.is_available():
            try: torch.cuda.synchronize(); torch.cuda.empty_cache()
            except Exception: pass

def get_runtime():
    return load_runtime()

@app.get("/health")
def health():
    return {"status":"alive"}

@app.get("/ready")
def ready():
    runtime,error=get_runtime()
    if runtime is None:
        raise HTTPException(status_code=503,detail="qualified GPU model is not ready")
    try:
        check_receipt_ledger()
    except RuntimeError as exc:
        raise HTTPException(status_code=503,detail="durable privacy receipt ledger is not ready") from exc
    return {
        "status":"ready","model_id":runtime["manifest"]["model_id"],
        "gpu":runtime["gpu_name"],"gpu_memory_bytes":runtime["gpu_memory_bytes"],
        "bundle_manifest_sha256":runtime["bundle_manifest_sha256"]
    }

@app.get("/capabilities")
def capabilities():
    runtime,error=get_runtime()
    return {
        "ready":runtime is not None,"model_id":runtime["manifest"]["model_id"] if runtime else None,
        "input_resolution":INPUT_RESOLUTION,"pose_channels":POSE_CHANNELS,
        "max_image_bytes":MAX_IMAGE_BYTES,"max_pose_bytes":MAX_POSE_BYTES,"max_request_bytes":MAX_REQUEST_BYTES,
        "max_concurrency":1,"persistent_storage":False,"requires_signed_privacy_receipt":True,
        "requires_face_masking":True,"error_code":error
    }

@app.post("/v1/render")
async def render(
    person_image:UploadFile=File(...),
    garment_image:UploadFile=File(...),
    person_mask:UploadFile=File(...),
    garment_mask:UploadFile=File(...),
    pose_heatmap:UploadFile=File(...),
    preprocessing_manifest_sha256:str=Form(...),
    privacy_attestation:str=Form(...),
    authorization:str|None=Header(default=None),
):
    token=os.getenv("CVI_VTON_WORKER_TOKEN","")
    if len(token)<32 or not authorization or not authorization.startswith("Bearer ") or not hmac.compare_digest(authorization[7:],token):
        raise HTTPException(status_code=401,detail="unauthorized")
    runtime,error=get_runtime()
    if runtime is None: raise HTTPException(status_code=503,detail="qualified GPU model is not ready")
    if not _inference_slot.acquire(blocking=False): raise HTTPException(status_code=429,detail="GPU worker is at capacity")
    uploads=(person_image,garment_image,person_mask,garment_mask,pose_heatmap)
    buffers={}
    try:
        for role,upload,limit in (
            ("person_image",person_image,MAX_IMAGE_BYTES),("garment_image",garment_image,MAX_IMAGE_BYTES),
            ("person_mask",person_mask,MAX_IMAGE_BYTES),("garment_mask",garment_mask,MAX_IMAGE_BYTES),
            ("pose_heatmap",pose_heatmap,MAX_POSE_BYTES)
        ):
            buffers[role]=await read_limited(upload,limit)
        dimensions={role:validate_image_bytes(buffers[role],role) for role in ("person_image","garment_image","person_mask","garment_mask")}
        if dimensions["person_image"]!=dimensions["person_mask"] or dimensions["garment_image"]!=dimensions["garment_mask"]:
            raise HTTPException(status_code=422,detail="image and mask dimensions must match")
        validate_pose_bytes(buffers["pose_heatmap"])
        if not SHA256_RE.fullmatch(preprocessing_manifest_sha256):
            raise HTTPException(status_code=422,detail="preprocessing manifest digest is invalid")
        asset_digests={role:sha256_bytes(buffers[role]) for role in ASSET_ROLES}
        try:
            verify_privacy_attestation(
                privacy_attestation,runtime["privacy_public_key"],runtime["privacy_key_id"],
                asset_digests,preprocessing_manifest_sha256
            )
        except ValueError as exc:
            raise HTTPException(status_code=403,detail="signed privacy attestation rejected") from exc
        except Exception as exc:
            raise HTTPException(status_code=503,detail="privacy receipt replay ledger unavailable") from exc
        png=await run_in_threadpool(run_inference,runtime,buffers)
        return Response(content=png,media_type="image/png",headers={
            "Cache-Control":"no-store, no-cache, must-revalidate, private",
            "Pragma":"no-cache","Expires":"0","X-Content-Type-Options":"nosniff",
            "Content-Security-Policy":"default-src 'none'; sandbox"
        })
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500,detail="inference failed") from exc
    finally:
        wipe_sensitive_buffers(buffers)
        for upload in uploads:
            try: await upload.close()
            except Exception: pass
        _inference_slot.release()
