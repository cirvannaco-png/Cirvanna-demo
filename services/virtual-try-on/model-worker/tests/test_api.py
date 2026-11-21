from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from app import main

TOKEN="vton-worker-test-token-with-more-than-32-bytes"

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("VTON_WORKER_TOKEN",TOKEN)
    monkeypatch.setenv("FASHN_VTON_SOURCE_REF","a"*40)
    monkeypatch.setenv("FASHN_VTON_WEIGHTS_DIR","/mock/weights")
    monkeypatch.setattr(main,"_configured",lambda:(True,"ready"))
    with TestClient(main.app) as c:
        yield c

def png(color=(30,90,150)):
    out=io.BytesIO()
    Image.new("RGB",(128,160),color).save(out,format="PNG")
    return out.getvalue()

def auth():
    return {"Authorization":f"Bearer {TOKEN}"}

def post(client,*,headers=None,category="upper_body",person=None,garment=None,garment_photo_type="flat-lay"):
    return client.post("/v1/render",headers=auth() if headers is None else headers,
        data={"category":category,"garment_photo_type":garment_photo_type},
        files={"person_image":("person.png",person or png(),"image/png"),
               "garment_image":("garment.png",garment or png((180,20,40)),"image/png")})

def test_health_is_liveness_only(client):
    assert client.get("/health").json()["status"]=="alive"

def test_capabilities_do_not_claim_persistence_or_remote_urls(client):
    result=client.get("/capabilities").json()
    assert result["input_persistence"] is False
    assert result["output_persistence"] is False
    assert result["remote_urls_accepted"] is False
    assert result["consent_enforced_by_worker"] is False
    assert result["requires_orchestrator_consent_gate"] is True
    assert result["artifact_manifest_required"] is True

def test_authentication_required(client):
    assert post(client,headers={}).status_code==401

def test_worker_does_not_require_or_trust_browser_consent_booleans(client,monkeypatch):
    class FakeResult:
        images=[Image.new("RGB",(128,160),(20,200,80))]
    class FakePipeline:
        def __call__(self,**kwargs):
            assert kwargs["category"]=="tops"
            assert kwargs["garment_photo_type"]=="flat-lay"
            assert kwargs["segmentation_free"] is True
            return FakeResult()
    monkeypatch.setattr(main,"_PIPELINE",FakePipeline())
    response=post(client)
    assert response.status_code==200
    assert response.headers["cache-control"]=="no-store, private"

@pytest.mark.parametrize(("category","mapped"),[
    ("upper_body","tops"),("outerwear","tops"),("lower_body","bottoms"),
    ("dress","one-pieces"),("full_outfit","one-pieces")
])
def test_category_mapping_is_explicit(category,mapped):
    assert main.CATEGORY_MAP[category]==mapped

def test_invalid_image_bytes_are_rejected(client):
    response=post(client,person=b"not an image")
    assert response.status_code==422
    assert response.json()["detail"]["code"]=="INVALID_IMAGE_DATA"

def test_worker_returns_validated_png_from_mock_pipeline(client,monkeypatch):
    class FakeResult:
        images=[Image.new("RGB",(128,160),(20,200,80))]
    class FakePipeline:
        def __call__(self,**kwargs):
            assert kwargs["category"]=="tops"
            assert kwargs["garment_photo_type"]=="flat-lay"
            assert kwargs["segmentation_free"] is True
            assert isinstance(kwargs["person_image"],Image.Image)
            assert isinstance(kwargs["garment_image"],Image.Image)
            return FakeResult()
    monkeypatch.setattr(main,"_PIPELINE",FakePipeline())
    response=post(client)
    assert response.status_code==200
    assert response.headers["content-type"]=="image/png"
    assert response.headers["cache-control"]=="no-store, private"
    with Image.open(io.BytesIO(response.content)) as image:
        image.verify()

def test_pipeline_failure_is_not_reported_as_success(client,monkeypatch):
    class Broken:
        def __call__(self,**kwargs): raise RuntimeError("private provider detail")
    monkeypatch.setattr(main,"_PIPELINE",Broken())
    response=post(client)
    assert response.status_code==502
    assert response.json()["detail"]["code"]=="INFERENCE_FAILED"
    assert "private provider detail" not in response.text

def test_readiness_requires_gpu_source_pin_and_weights(monkeypatch):
    monkeypatch.setenv("VTON_WORKER_TOKEN",TOKEN)
    monkeypatch.setenv("FASHN_VTON_SOURCE_REF","mutable-main")
    monkeypatch.setenv("FASHN_VTON_WEIGHTS_DIR","/missing")
    monkeypatch.setattr(main,"_configured",lambda:(False,"source_checkout_does_not_match_pin"))
    with TestClient(main.app) as client:
        response=client.get("/ready")
    assert response.status_code==503
    assert response.json()["detail"]["reason"]=="source_checkout_does_not_match_pin"


def test_artifact_manifest_requires_all_core_weights_and_exact_hashes(tmp_path):
    weights = tmp_path
    hashes = {}
    for relative in main.REQUIRED_ARTIFACTS:
        target = weights / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(("artifact:" + relative).encode())
        hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = {"schema_version": 1, "source_commit": "a" * 40, "artifacts": hashes}
    (weights / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert main._verify_artifact_manifest(weights, "a" * 40) == (True, "verified")
    assert main._verify_artifact_manifest(weights, "b" * 40) == (False, "model_artifact_source_mismatch")


def test_artifact_manifest_detects_tampered_weights(tmp_path):
    weights = tmp_path
    hashes = {}
    for relative in main.REQUIRED_ARTIFACTS:
        target = weights / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(("artifact:" + relative).encode())
        hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    (weights / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "source_commit": "a" * 40, "artifacts": hashes}),
        encoding="utf-8",
    )
    (weights / "model.safetensors").write_bytes(b"tampered")
    assert main._verify_artifact_manifest(weights, "a" * 40) == (False, "model_artifact_checksum_mismatch")


def test_artifact_manifest_rejects_missing_model_files(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "source_commit": "a" * 40, "artifacts": {}}),
        encoding="utf-8",
    )
    assert main._verify_artifact_manifest(tmp_path, "a" * 40) == (False, "model_artifact_checksum_missing")


def test_readiness_requires_model_pipeline_to_load(monkeypatch):
    monkeypatch.setenv("VTON_WORKER_TOKEN", TOKEN)
    monkeypatch.setenv("FASHN_VTON_SOURCE_REF", "a" * 40)
    monkeypatch.setattr(main, "_configured", lambda: (True, "ready"))
    monkeypatch.setattr(main, "_pipeline", lambda: (_ for _ in ()).throw(RuntimeError("load failed")))
    with TestClient(main.app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "model_load_failed"


def test_production_readiness_allows_maskless_flat_lay_without_restricted_parser(monkeypatch, tmp_path):
    _configured_worker(monkeypatch, tmp_path)
    monkeypatch.setenv("CIRVANNA_DEPLOYMENT_MODE", "production")
    monkeypatch.setenv("FASHN_VTON_PARSER_MODE", "maskless_flat_lay")
    monkeypatch.delenv("FASHN_HUMAN_PARSER_COMMERCIAL_LICENSE_APPROVED", raising=False)
    assert main._configured() == (True, "ready")


def test_worker_rejects_model_worn_garment_photo_type(client, monkeypatch):
    def forbidden_pipeline():
        raise AssertionError("Model-worn garment mode must not load the restricted parser.")
    monkeypatch.setattr(main, "_pipeline", forbidden_pipeline)
    response = post(client, garment_photo_type="model")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "UNSUPPORTED_GARMENT_PHOTO_TYPE"


def test_runtime_source_must_match_built_image_source(monkeypatch):
    monkeypatch.setenv("VTON_WORKER_TOKEN", TOKEN)
    monkeypatch.setenv("FASHN_VTON_SOURCE_REF", main.PINNED_FASHN_VTON_COMMIT)
    monkeypatch.setenv("FASHN_VTON_BUILT_SOURCE_REF", "b" * 40)
    monkeypatch.setenv("CIRVANNA_DEPLOYMENT_MODE", "research")
    ready, reason = main._configured()
    assert ready is False
    assert reason == "built_source_commit_mismatch"


def _configured_worker(monkeypatch, tmp_path, *, vram=8 * 1024**3, providers=("CUDAExecutionProvider", "CPUExecutionProvider"), checkout=None):
    pin = main.PINNED_FASHN_VTON_COMMIT
    source = tmp_path / "source"
    (source / ".git").mkdir(parents=True, exist_ok=True)
    weights = tmp_path / "weights"
    hashes = {}
    for relative in main.REQUIRED_ARTIFACTS:
        target = weights / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(("artifact:" + relative).encode())
        hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    (weights / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "source_commit": pin, "artifacts": hashes}),
        encoding="utf-8",
    )
    monkeypatch.setenv("VTON_WORKER_TOKEN", TOKEN)
    monkeypatch.setenv("FASHN_VTON_SOURCE_REF", pin)
    monkeypatch.setenv("FASHN_VTON_BUILT_SOURCE_REF", pin)
    monkeypatch.setenv("FASHN_VTON_SOURCE_DIR", str(source))
    monkeypatch.setenv("FASHN_VTON_WEIGHTS_DIR", str(weights))
    monkeypatch.setenv("CIRVANNA_DEPLOYMENT_MODE", "research")
    monkeypatch.setattr(
        main.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=(checkout or pin) + "\n"),
    )
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: True,
            get_device_properties=lambda _device: SimpleNamespace(total_memory=vram),
        )
    )
    fake_onnxruntime = SimpleNamespace(get_available_providers=lambda: list(providers))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_onnxruntime)
    return source, weights


def test_worker_image_excludes_restricted_human_parser_dependency():
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")
    assert "sed -i '/fashn-human-parser/d'" in dockerfile
    assert "python3 -m pip show fashn-human-parser" in dockerfile
    assert "PYTHONPATH=/app/vendor:/opt/fashn-vton/src" in dockerfile


def test_source_checkout_must_match_reviewed_commit(monkeypatch, tmp_path):
    _configured_worker(monkeypatch, tmp_path, checkout="f" * 40)
    assert main._source_checkout_matches() is False


def test_configured_requires_gpu_vram_and_onnx_cuda_provider(monkeypatch, tmp_path):
    _configured_worker(monkeypatch, tmp_path, vram=8 * 1024**3)
    assert main._configured() == (True, "ready")

    _configured_worker(monkeypatch, tmp_path, vram=7 * 1024**3)
    assert main._configured() == (False, "gpu_vram_below_8_gib")

    _configured_worker(monkeypatch, tmp_path, providers=("CPUExecutionProvider",))
    assert main._configured() == (False, "onnx_cuda_provider_unavailable")




def test_gpu_worker_returns_retryable_429_when_render_slot_is_busy(client, monkeypatch):
    monkeypatch.setattr(main, "_INFERENCE_SLOT", threading.BoundedSemaphore(value=0))
    response=post(client)
    assert response.status_code==429
    assert response.json()["detail"]["code"]=="GPU_WORKER_BUSY"
    assert response.json()["detail"]["retryable"] is True
    assert response.headers["Retry-After"]=="2"



def test_render_closes_pipeline_output_after_encoding(client, monkeypatch):
    output_image = Image.new("RGB", (128, 160), (20, 200, 80))

    class FakeResult:
        images = [output_image]

    class FakePipeline:
        def __call__(self, **kwargs):
            assert isinstance(kwargs["person_image"], Image.Image)
            assert isinstance(kwargs["garment_image"], Image.Image)
            return FakeResult()

    monkeypatch.setattr(main, "_PIPELINE", FakePipeline())
    response = post(client)
    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")
    with pytest.raises(ValueError, match="closed image"):
        output_image.getpixel((0, 0))


def test_render_closes_every_pipeline_output_image(monkeypatch):
    first = Image.new("RGB", (128, 160), (10, 20, 30))
    second = Image.new("RGB", (128, 160), (40, 50, 60))

    class FakeResult:
        images = [first, second]

    class FakePipeline:
        def __call__(self, **kwargs):
            return FakeResult()

    monkeypatch.setattr(main, "_PIPELINE", FakePipeline())
    encoded = main._render(
        Image.new("RGB", (128, 160)),
        Image.new("RGB", (128, 160)),
        "upper_body",
        "flat-lay",
    )
    assert encoded.startswith(b"\x89PNG")
    for generated in (first, second):
        with pytest.raises(ValueError, match="closed image"):
            generated.getpixel((0, 0))


def test_render_request_closes_decoded_uploads_after_success(client, monkeypatch):
    decoded = []

    def decode(data, content_type):
        with Image.open(io.BytesIO(data)) as source:
            result = source.convert("RGB")
        decoded.append(result)
        return result

    def render(person, garment, category, garment_photo_type):
        assert person.getpixel((0, 0)) is not None
        assert garment.getpixel((0, 0)) is not None
        assert category == "upper_body"
        assert garment_photo_type == "flat-lay"
        return png()

    async def inline_threadpool(function, *args):
        return function(*args)

    monkeypatch.setattr(main, "_decode_image", decode)
    monkeypatch.setattr(main, "_render", render)
    monkeypatch.setattr(main, "run_in_threadpool", inline_threadpool)
    response = post(client)
    assert response.status_code == 200
    assert len(decoded) == 2
    for image in decoded:
        with pytest.raises(ValueError, match="closed image"):
            image.getpixel((0, 0))


def test_render_request_closes_decoded_uploads_when_gpu_worker_is_busy(client, monkeypatch):
    decoded = []

    def decode(data, content_type):
        with Image.open(io.BytesIO(data)) as source:
            result = source.convert("RGB")
        decoded.append(result)
        return result

    monkeypatch.setattr(main, "_decode_image", decode)
    assert main._INFERENCE_SLOT.acquire(blocking=False)
    try:
        response = post(client)
    finally:
        main._INFERENCE_SLOT.release()
    assert response.status_code == 429
    assert len(decoded) == 2
    for image in decoded:
        with pytest.raises(ValueError, match="closed image"):
            image.getpixel((0, 0))


def test_render_request_closes_decoded_uploads_when_inference_fails(client, monkeypatch):
    from fastapi import HTTPException

    decoded = []

    def decode(data, content_type):
        with Image.open(io.BytesIO(data)) as source:
            result = source.convert("RGB")
        decoded.append(result)
        return result

    def fail_render(*_args):
        raise HTTPException(502, detail={"code": "INFERENCE_FAILED"})

    async def inline_threadpool(function, *args):
        return function(*args)

    monkeypatch.setattr(main, "_decode_image", decode)
    monkeypatch.setattr(main, "_render", fail_render)
    monkeypatch.setattr(main, "run_in_threadpool", inline_threadpool)
    response = post(client)
    assert response.status_code == 502
    assert len(decoded) == 2
    for image in decoded:
        with pytest.raises(ValueError, match="closed image"):
            image.getpixel((0, 0))
