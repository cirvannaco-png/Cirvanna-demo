import datetime, hashlib, json, sys, tempfile
import pytest
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tools.model_training.twin_geometry.reconstruct_appearance import (
    reconstruct_appearance,validate_appearance_capture,fuse_vertex_appearance
)
from test_twin_geometry_dataset import synthetic_mesh

def write_image(path:Path,mode:str,color):
    path.parent.mkdir(parents=True,exist_ok=True)
    Image.new(mode,(512,512),color).save(path,format="PNG")
    return hashlib.sha256(path.read_bytes()).hexdigest()

def camera_views():
    front=np.asarray([
        [1200,0,256,256*5000],
        [0,-1200,256,256*5000+1200*850],
        [0,0,1,5000]
    ],dtype=float)
    side=np.asarray([
        [256,0,1200,256*5000-1200*70],
        [256,-1200,0,256*5000+1200*850],
        [1,0,0,5000]
    ],dtype=float)
    return [("front",front),("side",side)]

def make_fixture(root:Path):
    media=root/"media"; media.mkdir()
    vertices,faces=synthetic_mesh(240,1700,140)
    geometry=root/"geometry.npz"; np.savez_compressed(geometry,vertices=vertices,faces=faces)
    calibration={"schema_version":"1.0","profiles":{
        "front":{"color_calibration_matrix":np.eye(3).tolist(),"white_balance_gain":[1,1,1]},
        "side":{"color_calibration_matrix":np.eye(3).tolist(),"white_balance_gain":[1,1,1]}
    }}
    calibration_path=media/"color-calibration.json"; calibration_path.write_text(json.dumps(calibration))
    views=[]
    for index,(view_id,camera) in enumerate(camera_views()):
        image_path=media/f"{view_id}.png"
        body_path=media/f"{view_id}-body.png"
        face_path=media/f"{view_id}-face.png"
        image_hash=write_image(image_path,"RGB",(190,80+index*50,40))
        body_hash=write_image(body_path,"L",255)
        face_mask=np.zeros((512,512),dtype=np.uint8)
        face_mask[30:100,220:292]=255
        face_stream=Image.fromarray(face_mask,"L")
        face_stream.save(face_path,format="PNG")
        face_hash=hashlib.sha256(face_path.read_bytes()).hexdigest()
        views.append({
            "view_id":view_id,"image_path":image_path.name,"image_sha256":image_hash,
            "body_mask_path":body_path.name,"body_mask_sha256":body_hash,
            "face_mask_path":face_path.name,"face_mask_sha256":face_hash,
            "image_width":512,"image_height":512,"camera_matrix":camera.tolist(),
            "color_calibration_matrix":np.eye(3).tolist(),"white_balance_gain":[1,1,1],
            "view_confidence":1.0
        })
    evidence=root/"consent.txt"; evidence.write_text("verified consent for appearance fixture")
    rights={
        "schema_version":"1.0","approval_status":"approved","scope":"twin_appearance_inference",
        "reviewed_by":"reviewer-1","reviewer_role":"privacy-owner",
        "reviewed_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_provenance":"controlled synthetic appearance fixture","evidence_path":str(evidence),
        "evidence_sha256":hashlib.sha256(evidence.read_bytes()).hexdigest(),
        "commercial_evaluation_permitted":True,"human_review_permitted":True,
        "retention_until":(datetime.date.today()+datetime.timedelta(days=10)).isoformat(),
        "contains_personal_images":True,"depicted_person_consent_status":"verified"
    }
    rights_path=root/"rights.json"; rights_path.write_text(json.dumps(rights))
    capture={
        "schema_version":"1.0","capture_id":"appearance-fixture-001",
        "rights_manifest_sha256":hashlib.sha256(rights_path.read_bytes()).hexdigest(),
        "geometry_sha256":hashlib.sha256(geometry.read_bytes()).hexdigest(),
        "face_masked_before_inference":True,"preprocessing_manifest_sha256":"a"*64,
        "color_calibration_evidence_ref":"calibration:chart-001",
        "color_calibration_evidence_path":calibration_path.name,
        "color_calibration_evidence_sha256":hashlib.sha256(calibration_path.read_bytes()).hexdigest(),
        "views":views
    }
    capture_path=root/"capture.json"; capture_path.write_text(json.dumps(capture))
    return geometry,capture_path,rights_path,media,vertices,faces,capture

def test_fuses_calibrated_multiview_vertex_appearance_and_excludes_face_pixels(tmp_path):
    geometry,capture_path,rights_path,media,vertices,faces,capture=make_fixture(tmp_path)
    rights,checked=validate_appearance_capture(capture,rights_path,geometry,media)
    colors,confidence,quality=fuse_vertex_appearance(vertices,faces,checked["views"])
    assert confidence[0]==0.0
    assert quality["coverage_ratio"]>0.05
    assert quality["face_pixels_excluded"] is True
    output=tmp_path/"output"
    report=reconstruct_appearance(geometry,capture_path,rights_path,media,output,"b"*40)
    glb=output/"twin-appearance-candidate.glb"
    assert glb.read_bytes().startswith(b"glTF")
    assert report["status"]=="research_candidate_not_qualified"
    assert report["quality"]["textured_vertex_count"]>0
    assert report["quality"]["face_pixels_excluded"] is True

def test_appearance_capture_fails_closed_without_face_mask_or_calibration_binding(tmp_path):
    geometry,capture_path,rights_path,media,vertices,faces,capture=make_fixture(tmp_path)
    capture["face_masked_before_inference"]=False
    with pytest.raises(ValueError,match="face masking"):
        validate_appearance_capture(capture,rights_path,geometry,media)
