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

def post(client,*,headers=None,consent=True,category="upper_body",person=None,garment=None):
    return client.post("/v1/render",headers=auth() if headers is None else headers,
        data={"consent_image_processing":str(consent).lower(),"consent_virtual_try_on":"true","category":category},
        files={"person_image":("person.png",person or png(),"image/png"),
               "garment_image":("garment.png",garment or png((180,20,40)),"image/png")})

def test_health_is_liveness_only(client):
    assert client.get("/health").json()["status"]=="alive"

def test_capabilities_do_not_claim_persistence_or_remote_urls(client):
    result=client.get("/capabilities").json()
    assert result["input_persistence"] is False
    assert result["output_persistence"] is False
    assert result["remote_urls_accepted"] is False

def test_authentication_required(client):
    assert post(client,headers={}).status_code==401

def test_explicit_consent_required(client):
    response=post(client,consent=False)
    assert response.status_code==403
    assert response.json()["detail"]["code"]=="EXPLICIT_CONSENT_REQUIRED"

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
    monkeypatch.setattr(main,"_configured",lambda:(False,"pinned_source_commit_required"))
    with TestClient(main.app) as client:
        response=client.get("/ready")
    assert response.status_code==503
