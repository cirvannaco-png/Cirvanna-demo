from __future__ import annotations
import io
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

def test_capabilities_are_honest_about_consent_and_persistence(client):
    result=client.get("/capabilities").json()
    assert result["input_persistence"] is False
    assert result["output_persistence"] is False
    assert result["remote_urls_accepted"] is False
    assert result["consent_enforced_by_worker"] is False
    assert result["requires_orchestrator_consent_gate"] is True

def test_authentication_required(client):
    assert post(client,headers={}).status_code==401

def test_worker_does_not_accept_client_consent_as_authority(client):
    # The private worker is only callable by the orchestrator after server-side
    # consent verification; multipart booleans are deliberately not part of API.
    assert "consent_image_processing" not in main.render.__annotations__
    assert "consent_virtual_try_on" not in main.render.__annotations__

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

def test_readiness_requires_source_pin_weights_and_gpu(monkeypatch):
    monkeypatch.setenv("VTON_WORKER_TOKEN",TOKEN)
    monkeypatch.setenv("FASHN_VTON_SOURCE_REF","mutable-main")
    monkeypatch.setenv("FASHN_VTON_WEIGHTS_DIR","/missing")
    monkeypatch.setattr(main,"_configured",lambda:(False,"source_checkout_does_not_match_pin"))
    with TestClient(main.app) as client:
        response=client.get("/ready")
    assert response.status_code==503
    assert response.json()["detail"]["reason"]=="source_checkout_does_not_match_pin"


def test_source_checkout_must_match_exact_sha(monkeypatch,tmp_path):
    source=tmp_path/"fashn"
    source.mkdir()
    (source/".git").mkdir()
    expected="a"*40
    monkeypatch.setenv("FASHN_VTON_SOURCE_REF",expected)
    monkeypatch.setenv("FASHN_VTON_SOURCE_DIR",str(source))
    monkeypatch.setattr(main.subprocess,"run",lambda *a,**k:type("Result",(),{"stdout":expected+"\\n"})())
    assert main._source_checkout_matches() is True


def test_required_weights_must_be_present_and_nonempty(monkeypatch,tmp_path):
    root=tmp_path/"weights"
    (root/"dwpose").mkdir(parents=True)
    for name in ("model.safetensors","dwpose/yolox_l.onnx","dwpose/dw-ll_ucoco_384.onnx"):
        (root/name).write_bytes(b"weight")
    monkeypatch.setenv("FASHN_VTON_WEIGHTS_DIR",str(root))
    assert main._required_weights_present() is True
    (root/"model.safetensors").write_bytes(b"")
    assert main._required_weights_present() is False


def test_readiness_loads_all_pipeline_components(client,monkeypatch):
    monkeypatch.setattr(main,"_pipeline",lambda:object())
    response=client.get("/ready")
    assert response.status_code==200
    assert response.json()["model_loaded"] is True


def test_readiness_fails_if_model_or_parser_cannot_load(client,monkeypatch):
    def broken(): raise RuntimeError("model load failure")
    monkeypatch.setattr(main,"_pipeline",broken)
    response=client.get("/ready")
    assert response.status_code==503
    assert response.json()["detail"]["reason"]=="model_initialization_failed"
