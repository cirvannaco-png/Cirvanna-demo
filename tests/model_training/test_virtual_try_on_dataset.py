import datetime, hashlib, json, sys, tempfile, unittest
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.model_training.virtual_try_on.validate_dataset import validate_dataset, split_manifest_digest

ROLES=("person_image","garment_image","target_image","person_mask","garment_mask","target_garment_mask","pose_heatmap")

class VirtualTryOnDatasetTests(unittest.TestCase):
    def _rights(self,root:Path,name:str,*,personal:bool,consent:str,scope="virtual_try_on_training"):
        evidence=root/f"{name}-evidence.txt"; evidence.write_text(f"rights evidence for {name}")
        value={
            "schema_version":"1.0","approval_status":"approved","scope":scope,
            "reviewed_by":"reviewer-1","reviewer_role":"data-rights-owner",
            "reviewed_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source_provenance":f"approved {name} fixture","evidence_path":str(evidence),
            "evidence_sha256":hashlib.sha256(evidence.read_bytes()).hexdigest(),
            "commercial_evaluation_permitted":True,"human_review_permitted":True,
            "retention_until":(datetime.date.today()+datetime.timedelta(days=30)).isoformat(),
            "contains_personal_images":personal,"depicted_person_consent_status":consent
        }
        path=root/f"{name}-rights.json"; path.write_text(json.dumps(value))
        return path

    def _fixture(self,root:Path,*,subject_leak=False,garment_leak=False,face_masked=True,pose_channels=17,garment_personal=False,garment_consent="not_applicable",path_traversal=False):
        media_root=root/"media"; media_root.mkdir()
        rows=[]
        for index,split in enumerate(("train","validation","test")):
            media={}
            for role_index,role in enumerate(ROLES):
                name=f"{split}-{role}"
                path=media_root/(name+(".npz" if role=="pose_heatmap" else ".png"))
                if role=="pose_heatmap":
                    np.savez_compressed(path,heatmaps=np.zeros((pose_channels,64,64),dtype=np.float32))
                elif role.endswith("_mask"):
                    Image.new("L",(256,256),(index*50+role_index*11)%256).save(path)
                else:
                    Image.new("RGB",(256,256),(30+index*50,50+role_index*7,80)).save(path)
                media[role]={"path":path.name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
            if path_traversal and index==0:
                media["person_image"]["path"]="../escape.png"
            rows.append({
                "sample_id":f"sample-{split}","subject_cluster_id":"shared-subject" if subject_leak and split in {"train","validation"} else f"subject-{split}",
                "garment_product_id":f"product-{split}","garment_family_id":"shared-family" if garment_leak and split in {"train","validation"} else f"family-{split}",
                "split":split,"face_masked_before_training":face_masked,"garment_face_masked_before_training":True,
                "preprocessing_manifest_sha256":"a"*64,"subgroups":{"lighting":"controlled","garment_category":"tops"},"media":media
            })
        person_rights=self._rights(root,"person",personal=True,consent="verified")
        garment_rights=self._rights(root,"garment",personal=garment_personal,consent=garment_consent)
        annotations=root/"annotations.jsonl"
        def write_rows():
            annotations.write_text("".join(json.dumps(row,sort_keys=True)+"\n" for row in rows),encoding="utf-8")
        write_rows()
        manifest={
            "schema_version":"1.0","dataset_id":"cvi-vton-synthetic",
            "person_rights_manifest_sha256":hashlib.sha256(person_rights.read_bytes()).hexdigest(),
            "garment_rights_manifest_sha256":hashlib.sha256(garment_rights.read_bytes()).hexdigest(),
            "annotations_sha256":hashlib.sha256(annotations.read_bytes()).hexdigest(),
            "sample_count":len(rows),"pose_protocol_id":"pose-17-v1","mask_protocol_id":"garment-mask-v1",
            "split_manifest_sha256":split_manifest_digest(rows)
        }
        manifest_path=root/"dataset.json"; manifest_path.write_text(json.dumps(manifest))
        return validate_dataset(manifest_path,annotations,media_root,person_rights,garment_rights),rows,manifest_path,annotations,media_root,person_rights,garment_rights

    def test_validates_two_rights_domains_and_disjoint_paired_data(self):
        with tempfile.TemporaryDirectory() as temp:
            result,*_=self._fixture(Path(temp))
            self.assertEqual(result["status"],"validated_for_try_on_training_input_only")
            self.assertEqual(result["split_counts"],{"test":1,"train":1,"validation":1})

    def test_rejects_subject_and_garment_family_split_leakage(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"subject clusters leak"):
                self._fixture(Path(temp),subject_leak=True)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"garment-family clusters leak"):
                self._fixture(Path(temp),garment_leak=True)

    def test_requires_face_masking_and_valid_pose_channels(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"face masking"):
                self._fixture(Path(temp),face_masked=False)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"17 finite channels"):
                self._fixture(Path(temp),pose_channels=16)

    def test_rejects_unconsented_persons_in_garment_catalogue_images(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"depicted-person consent"):
                self._fixture(Path(temp),garment_personal=True,garment_consent="unknown")

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"traversal"):
                self._fixture(Path(temp),path_traversal=True)

if __name__=="__main__": unittest.main()
