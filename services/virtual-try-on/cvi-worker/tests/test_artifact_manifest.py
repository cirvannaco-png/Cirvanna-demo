import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_artifact_manifest.py"
SPEC = importlib.util.spec_from_file_location("cvi_artifact_manifest", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def setup_case(tmp_path):
    checkpoint=tmp_path/"model.pt"; checkpoint.write_bytes(b"checkpoint")
    training_path=tmp_path/"training.json"
    dataset_path=tmp_path/"dataset.json"
    dataset={"annotations_sha256":"d"*64,"split_manifest_sha256":"e"*64}
    dataset_path.write_text(json.dumps(dataset))
    training={"model_id":"cirvanna-tryon-warp-refine-v0","architecture":"custom-unet-flow-warp-alpha-residual",
      "source_revision":"a"*40,"held_out_test":{"status":"reserved_for_independent_evaluation","sample_count":10},
      "dataset":{"dataset_manifest_sha256":sha(dataset_path),"person_rights_manifest_sha256":"b"*64,"garment_rights_manifest_sha256":"c"*64}}
    training_path.write_text(json.dumps(training))
    person={"manifest_sha256":"b"*64}; garment={"manifest_sha256":"c"*64}
    evaluation={
      "model_id":training["model_id"],"architecture":training["architecture"],"source_revision":"a"*40,
      "checkpoint_sha256":sha(checkpoint),"training_report_sha256":sha(training_path),
      "dataset_manifest_sha256":sha(dataset_path),"annotations_sha256":"d"*64,"split_manifest_sha256":"e"*64,
      "person_rights_manifest_sha256":"b"*64,"garment_rights_manifest_sha256":"c"*64,
      "status":"independent_held_out_evaluation_not_qualified","sample_count":10,
      "metrics_macro_sample_mean":{"image_mae":0.1,"psnr_db":20.0,"ssim_global":0.8,"garment_region_mae":0.12,"alpha_mask_iou":0.7,"warped_garment_mask_iou":0.68}}
    return training,evaluation,dataset,checkpoint,training_path,dataset_path,"a"*40,person,garment

def test_accepts_fully_bound_independent_test_report(tmp_path):
    case=setup_case(tmp_path)
    MODULE.validate_evaluation_provenance(*case)
    
def test_rejects_training_report_that_consumed_test_split(tmp_path):
    case=setup_case(tmp_path)
    case[0]["held_out_test"]["status"]="evaluated_during_training"
    case[4].write_text(json.dumps(case[0]))
    case[1]["training_report_sha256"]=sha(case[4])
    with pytest.raises(ValueError,match="leave the held-out test"):
        MODULE.validate_evaluation_provenance(*case)

def test_rejects_evaluation_from_different_checkpoint(tmp_path):
    case=setup_case(tmp_path)
    case[1]["checkpoint_sha256"]="f"*64
    with pytest.raises(ValueError,match="checkpoint_sha256"):
        MODULE.validate_evaluation_provenance(*case)

def test_rejects_missing_independent_metrics(tmp_path):
    case=setup_case(tmp_path)
    case[1]["metrics_macro_sample_mean"].pop("ssim_global")
    with pytest.raises(ValueError,match="image-quality metrics"):
        MODULE.validate_evaluation_provenance(*case)
