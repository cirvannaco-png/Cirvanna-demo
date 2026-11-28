import base64, datetime, hashlib, io, json, sys, tempfile, subprocess
from pathlib import Path

import numpy as np
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from PIL import Image

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import main as worker

def key_pair():
    private=Ed25519PrivateKey.generate()
    public=private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    return private,base64.b64encode(public).decode()

def sign(payload:bytes,private:Ed25519PrivateKey)->str:
    return base64.b64encode(private.sign(payload)).decode()

def model_bundle(root:Path,private:Ed25519PrivateKey,validity_days=60):
    root.mkdir(mode=0o700)
    files={
        "model.pt":b"safe-state-dict-fixture",
        "training-report.json":b"training-report-fixture",
        "evaluation-report.json":b"independent-evaluation-fixture",
        "dataset.manifest.json":b"dataset-manifest-fixture",
        "person-rights.manifest.json":b"person-rights-fixture",
        "garment-rights.manifest.json":b"garment-rights-fixture",
    }
    for name,data in files.items(): (root/name).write_bytes(data)
    fields={
        "schema_version":"1.0","model_id":worker.MODEL_ID,"architecture":worker.ARCHITECTURE,
        "source_revision":"a"*40,
        "checkpoint_sha256":hashlib.sha256(files["model.pt"]).hexdigest(),
        "training_report_sha256":hashlib.sha256(files["training-report.json"]).hexdigest(),
        "evaluation_report_sha256":hashlib.sha256(files["evaluation-report.json"]).hexdigest(),
        "dataset_manifest_sha256":hashlib.sha256(files["dataset.manifest.json"]).hexdigest(),
        "person_rights_manifest_sha256":hashlib.sha256(files["person-rights.manifest.json"]).hexdigest(),
        "garment_rights_manifest_sha256":hashlib.sha256(files["garment-rights.manifest.json"]).hexdigest(),
        "base_channels":32,"input_resolution":256,"pose_channels":17,
        "max_gpu_memory_fraction":0.8,"minimum_gpu_memory_bytes":8*1024**3,
        "max_concurrency":1,"runtime_image_digest":"b"*64,
    }
    now=datetime.datetime.now(datetime.timezone.utc)
    fields["qualification_attestation"]={
        "result":"qualified","key_id":"independent-model-review-key",
        "signed_at":now.isoformat(),
        "expires_at":(now+datetime.timedelta(days=validity_days)).isoformat()
    }
    payload=worker.model_attestation_payload(fields)
    fields["qualification_attestation"]["payload_sha256"]=hashlib.sha256(payload).hexdigest()
    fields["qualification_attestation"]["signature_base64"]=sign(payload,private)
    (root/"manifest.json").write_text(json.dumps(fields))
    return fields

def privacy_receipt(private,public_key_id,asset_digests,preprocessing_digest,*,expires=None,receipt_id="receipt-opaque-001"):
    payload={
        "schema_version":"1.0","key_id":public_key_id,
        "purpose":"virtual_try_on_inference","consent_scope":"virtual_try_on_inference",
        "receipt_id":receipt_id,"consent_policy_version":"cal-v1",
        "consent_status":"active","revocation_status":"not_revoked",
        "user_binding_sha256":"c"*64,"revocation_epoch":3,
        "preprocessing_manifest_sha256":preprocessing_digest,
        "asset_sha256":asset_digests,
        "face_masked_before_inference":True,"garment_face_masked_before_inference":True,
        "issued_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "expires_at":expires or (datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(seconds=20)).isoformat()
    }
    payload["signature_base64"]=sign(worker.privacy_attestation_payload(payload),private)
    return payload

def image_bytes(mode="RGB",color=20):
    stream=io.BytesIO()
    Image.new(mode,(256,256),color).save(stream,format="PNG")
    return stream.getvalue()

def pose_bytes():
    stream=io.BytesIO()
    np.savez_compressed(stream,heatmaps=np.zeros((17,64,64),dtype=np.float32))
    return stream.getvalue()

def test_model_bundle_requires_valid_independent_signature_and_exact_artifacts(tmp_path):
    private,public=key_pair()
    bundle=tmp_path/"bundle"
    manifest=model_bundle(bundle,private)
    verified=worker.verify_model_bundle(bundle,public,"independent-model-review-key")
    assert verified["model_id"]==worker.MODEL_ID
    (bundle/"model.pt").write_bytes(b"tampered")
    with pytest.raises(ValueError,match="digest mismatch"):
        worker.verify_model_bundle(bundle,public,"independent-model-review-key")

def test_model_bundle_rejects_wrong_qualification_key(tmp_path):
    private,public=key_pair()
    bundle=tmp_path/"bundle"
    model_bundle(bundle,private)
    with pytest.raises(ValueError,match="key ID mismatch"):
        worker.verify_model_bundle(bundle,public,"untrusted-key")

def test_model_bundle_rejects_expired_independent_qualification(tmp_path):
    private,public=key_pair()
    bundle=tmp_path/"bundle"
    model_bundle(bundle,private,validity_days=-1)
    with pytest.raises(ValueError,match="expired"):
        worker.verify_model_bundle(bundle,public,"independent-model-review-key")

def test_model_bundle_rejects_unsigned_research_checkpoint(tmp_path):
    private,public=key_pair()
    bundle=tmp_path/"bundle"
    manifest=model_bundle(bundle,private)
    manifest["qualification_attestation"]=None
    (bundle/"manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="attestation is missing"):
        worker.verify_model_bundle(bundle,public,"independent-model-review-key")

def test_privacy_receipt_binds_assets_user_scope_expiry_and_masking():
    private,public=key_pair()
    assets={role:(str(index+1)*64) for index,role in enumerate(worker.ASSET_ROLES)}
    preprocessing="f"*64
    receipt=privacy_receipt(private,"privacy-governance-key",assets,preprocessing)
    assert worker.verify_privacy_attestation(json.dumps(receipt),public,"privacy-governance-key",assets,preprocessing)=="receipt-opaque-001"
    with pytest.raises(ValueError,match="replay"):
        worker.verify_privacy_attestation(json.dumps(receipt),public,"privacy-governance-key",assets,preprocessing)
    changed=dict(assets); changed["person_image"]="e"*64
    with pytest.raises(ValueError,match="exact submitted assets"):
        worker.verify_privacy_attestation(json.dumps(receipt),public,"privacy-governance-key",changed,preprocessing)

def test_privacy_receipt_rejects_expired_or_unmasked_assets():
    private,public=key_pair()
    assets={role:(str(index+1)*64) for index,role in enumerate(worker.ASSET_ROLES)}
    preprocessing="f"*64
    expired=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=1)).isoformat()
    receipt=privacy_receipt(private,"privacy-governance-key",assets,preprocessing,expires=expired)
    with pytest.raises(ValueError,match="expired"):
        worker.verify_privacy_attestation(json.dumps(receipt),public,"privacy-governance-key",assets,preprocessing)
    receipt=privacy_receipt(private,"privacy-governance-key",assets,preprocessing)
    receipt["face_masked_before_inference"]=False
    with pytest.raises(ValueError,match="face masking"):
        worker.verify_privacy_attestation(json.dumps(receipt),public,"privacy-governance-key",assets,preprocessing)

def test_input_validation_and_sensitive_buffer_wipe():
    assert worker.validate_image_bytes(bytearray(image_bytes()),"person_image")== (256,256)
    assert worker.validate_image_bytes(bytearray(image_bytes("L")),"person_mask")== (256,256)
    with pytest.raises(ValueError,match="grayscale PNG"):
        worker.validate_image_bytes(bytearray(image_bytes("RGB")),"person_mask")
    worker.validate_pose_bytes(bytearray(pose_bytes()))
    with pytest.raises(ValueError,match="17x64x64"):
        bad=io.BytesIO(); np.savez_compressed(bad,heatmaps=np.zeros((16,64,64),dtype=np.float32))
        worker.validate_pose_bytes(bytearray(bad.getvalue()))
    buffers={"person_image":bytearray(b"private image bytes"),"pose_heatmap":bytearray(b"private pose bytes")}
    worker.wipe_sensitive_buffers(buffers)
    assert buffers=={} or all(not value for value in buffers.values())

def test_render_requires_bearer_auth_and_signed_privacy_receipt(monkeypatch):
    private,public=key_pair()
    monkeypatch.setenv("CVI_VTON_WORKER_TOKEN","w"*48)
    monkeypatch.setenv("CVI_VTON_PRIVACY_KEY_ID","privacy-governance-key")
    monkeypatch.setenv("CVI_VTON_PRIVACY_PUBLIC_KEY_B64",public)
    runtime={"privacy_public_key":public,"privacy_key_id":"privacy-governance-key"}
    monkeypatch.setattr(worker,"get_runtime",lambda:(runtime,None))
    monkeypatch.setattr(worker,"run_inference",lambda runtime,buffers:b"fake-png")
    wiped=[]
    original_wipe=worker.wipe_sensitive_buffers
    def capture_wipe(buffers):
        references=list(buffers.values())
        original_wipe(buffers)
        wiped.extend(references)
    monkeypatch.setattr(worker,"wipe_sensitive_buffers",capture_wipe)
    person=image_bytes("RGB",20); garment=image_bytes("RGB",40)
    person_mask=image_bytes("L",0); garment_mask=image_bytes("L",255); pose=pose_bytes()
    assets={
        "person_image":hashlib.sha256(person).hexdigest(),
        "garment_image":hashlib.sha256(garment).hexdigest(),
        "person_mask":hashlib.sha256(person_mask).hexdigest(),
        "garment_mask":hashlib.sha256(garment_mask).hexdigest(),
        "pose_heatmap":hashlib.sha256(pose).hexdigest()
    }
    preprocessing="d"*64
    receipt=privacy_receipt(private,"privacy-governance-key",assets,preprocessing,receipt_id="receipt-render-001")
    files={
        "person_image":("person.png",person,"image/png"),
        "garment_image":("garment.png",garment,"image/png"),
        "person_mask":("person-mask.png",person_mask,"image/png"),
        "garment_mask":("garment-mask.png",garment_mask,"image/png"),
        "pose_heatmap":("pose.npz",pose,"application/octet-stream")
    }
    data={"preprocessing_manifest_sha256":preprocessing,"privacy_attestation":json.dumps(receipt)}
    client=TestClient(worker.app)
    unauth=client.post("/v1/render",files=files,data=data)
    assert unauth.status_code==401
    response=client.post("/v1/render",files=files,data=data,headers={"Authorization":"Bearer "+"w"*48})
    assert response.status_code==200
    assert response.content==b"fake-png"
    assert response.headers["cache-control"].startswith("no-store")
    assert response.headers["x-content-type-options"]=="nosniff"
    assert len(wiped)==5 and all(len(value)==0 for value in wiped)

def test_readiness_fails_closed_without_model_bundle(monkeypatch):
    worker._runtime=None
    monkeypatch.setenv("CVI_VTON_WORKER_TOKEN","w"*48)
    monkeypatch.setenv("CVI_VTON_QUALIFICATION_PUBLIC_KEY_B64","x")
    monkeypatch.setenv("CVI_VTON_QUALIFICATION_KEY_ID","key")
    monkeypatch.setenv("CVI_VTON_PRIVACY_PUBLIC_KEY_B64","x")
    monkeypatch.setenv("CVI_VTON_PRIVACY_KEY_ID","key")
    monkeypatch.setenv("CVI_VTON_MODEL_BUNDLE","/definitely/missing/cvi-vton-model")
    client=TestClient(worker.app)
    assert client.get("/health").status_code==200
    assert client.get("/ready").status_code==503

def test_request_body_middleware_rejects_declared_and_streamed_oversize():
    import asyncio
    async def fake_app(scope,receive,send):
        await receive()
        await send({"type":"http.response.start","status":200,"headers":[]})
        await send({"type":"http.response.body","body":b"ok"})
    middleware=worker.MaxRequestBodyMiddleware(fake_app,max_bytes=4)
    async def run(scope,body):
        messages=[]
        async def receive(): return {"type":"http.request","body":body,"more_body":False}
        async def send(message): messages.append(message)
        await middleware(scope,receive,send)
        return messages
    scope={"type":"http","path":"/v1/render","method":"POST","headers":[(b"content-length",b"5")]}
    declared=asyncio.run(run(scope,b"12345"))
    assert declared[0]["status"]==413
    chunked_scope={"type":"http","path":"/v1/render","method":"POST","headers":[]}
    streamed=asyncio.run(run(chunked_scope,b"12345"))
    assert streamed[0]["status"]==413

def test_artifact_builder_creates_unsigned_bundle_that_worker_refuses(tmp_path):
    sys.path.insert(0,str(ROOT/"tests/model_training"))
    from test_virtual_try_on_dataset import VirtualTryOnDatasetTests
    source_root=tmp_path/"source"
    source_root.mkdir()
    fixture=VirtualTryOnDatasetTests()
    dataset_result,rows,dataset_manifest,annotations,media_root,person_rights,garment_rights=fixture._fixture(source_root)
    checkpoint=source_root/"checkpoint.pt"
    checkpoint.write_bytes(b"trained-checkpoint-placeholder")
    training={
        "model_id":"cirvanna-tryon-warp-refine-v0",
        "architecture":"custom-unet-flow-warp-alpha-residual",
        "source_revision":"a"*40,"training":{"base_channels":32},
        "dataset":{
            "person_rights_manifest_sha256":dataset_result["person_rights_manifest_sha256"],
            "garment_rights_manifest_sha256":dataset_result["garment_rights_manifest_sha256"]
        }
    }
    training_path=source_root/"training-report.json"
    training_path.write_text(json.dumps(training))
    evaluation={
        "model_id":"cirvanna-tryon-warp-refine-v0",
        "checkpoint_sha256":hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "dataset_manifest_sha256":hashlib.sha256(dataset_manifest.read_bytes()).hexdigest()
    }
    evaluation_path=source_root/"evaluation-report.json"
    evaluation_path.write_text(json.dumps(evaluation))
    bundle=tmp_path/"bundle"
    command=[
        sys.executable,str(ROOT/"services/virtual-try-on/cvi-worker/scripts/build_artifact_manifest.py"),
        "--bundle-dir",str(bundle),"--checkpoint",str(checkpoint),
        "--training-report",str(training_path),"--evaluation-report",str(evaluation_path),
        "--dataset-manifest",str(dataset_manifest),"--person-rights-manifest",str(person_rights),
        "--garment-rights-manifest",str(garment_rights),"--source-revision","a"*40,
        "--runtime-image-digest","b"*64
    ]
    subprocess.run(command,check=True,capture_output=True,text=True)
    manifest=json.loads((bundle/"manifest.json").read_text())
    assert manifest["qualification_attestation"] is None
    private,public=key_pair()
    with pytest.raises(ValueError,match="attestation is missing"):
        worker.verify_model_bundle(bundle,public,"independent-model-review-key")


def test_privacy_receipt_replay_is_durable_across_worker_restarts(tmp_path, monkeypatch):
    ledger = tmp_path / "durable" / "replay-ledger.sqlite3"
    monkeypatch.setenv("CVI_VTON_REPLAY_DB_PATH", str(ledger))
    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=20)
    worker.consume_receipt_once("receipt-persistent-001", expires)

    # A new worker process has no in-memory state to inherit. The database
    # uniqueness constraint must still reject the same unexpired receipt.
    assert ledger.is_file()
    assert ledger.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="replay"):
        worker.consume_receipt_once("receipt-persistent-001", expires)


def test_privacy_receipt_ledger_allows_exactly_one_concurrent_consumer(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    ledger = tmp_path / "replay-ledger.sqlite3"
    monkeypatch.setenv("CVI_VTON_REPLAY_DB_PATH", str(ledger))
    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=20)

    def consume():
        try:
            worker.consume_receipt_once("receipt-race-001", expires)
            return "accepted"
        except ValueError:
            return "replay"

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: consume(), range(8)))
    assert outcomes.count("accepted") == 1
    assert outcomes.count("replay") == 7


def test_privacy_receipt_ledger_fails_closed_when_unconfigured(monkeypatch):
    monkeypatch.setenv("CVI_VTON_REPLAY_DB_PATH", "")
    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=20)
    with pytest.raises(RuntimeError, match="not configured"):
        worker.consume_receipt_once("receipt-no-ledger-001", expires)
