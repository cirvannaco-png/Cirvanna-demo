import datetime, hashlib, json, sys, tempfile, unittest
from pathlib import Path
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.model_training.click_it.validate_dataset import validate_sample, split_manifest_digest, safe_media_path, validate_dataset

class ClickItDatasetContractTests(unittest.TestCase):
    def _fixture(self,root:Path,*,family_leak=False,duplicate=False,views=2):
        media=root/"media"; media.mkdir()
        rows=[]
        for split_index,split in enumerate(("train","validation","test")):
            for product_index in range(2):
                product=f"{split}-product-{product_index}"
                family="shared-family" if family_leak and split in {"train","validation"} and product_index==0 else f"{split}-family-{product_index}"
                for view in range(views):
                    name=f"{split}-{product_index}-{view}.png"
                    path=media/name
                    color=(40+split_index*40,50+product_index*50,60+view*40)
                    Image.new("RGB",(128,128),color).save(path)
                    if duplicate and split=="train" and product_index==0 and view==1:
                        path.write_bytes((media/"train-0-0.png").read_bytes())
                    digest=hashlib.sha256(path.read_bytes()).hexdigest()
                    rows.append({"sample_id":f"sample-{split}-{product_index}-{view}","product_id":product,"product_family_id":family,"split":split,"image_path":name,"image_sha256":digest,"width":128,"height":128,"category":"tops"})
        annotations=root/"annotations.jsonl"
        annotations.write_text("".join(json.dumps(row,sort_keys=True)+"\n" for row in rows),encoding="utf-8")
        evidence=root/"rights-evidence.txt"; evidence.write_text("approved catalogue image rights")
        rights={
            "schema_version":"1.0","approval_status":"approved","scope":"click_it_retrieval_evaluation",
            "reviewed_by":"reviewer-1","reviewer_role":"data-rights-owner",
            "reviewed_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source_provenance":"approved catalogue fixture","evidence_path":str(evidence),
            "evidence_sha256":hashlib.sha256(evidence.read_bytes()).hexdigest(),
            "commercial_evaluation_permitted":True,"human_review_permitted":True,
            "retention_until":(datetime.date.today()+datetime.timedelta(days=30)).isoformat(),
            "contains_personal_images":False,"depicted_person_consent_status":"not_applicable"
        }
        rights_path=root/"rights.json"; rights_path.write_text(json.dumps(rights))
        manifest={
            "schema_version":"1.0","dataset_id":"clickit-test-corpus",
            "rights_manifest_sha256":hashlib.sha256(rights_path.read_bytes()).hexdigest(),
            "annotations_sha256":hashlib.sha256(annotations.read_bytes()).hexdigest(),
            "sample_count":len(rows),"categories":["tops"],
            "split_manifest_sha256":split_manifest_digest(rows)
        }
        manifest_path=root/"dataset.json"; manifest_path.write_text(json.dumps(manifest))
        return validate_dataset(manifest_path,annotations,media,rights_path),rows,media

    def test_validates_rights_bound_family_disjoint_corpus(self):
        with tempfile.TemporaryDirectory() as temp:
            result,_,_=self._fixture(Path(temp))
            self.assertEqual(result["status"],"validated_for_training_input_only")
            self.assertEqual(result["product_count_by_split"],{"test":2,"train":2,"validation":2})

    def test_rejects_product_family_leakage(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"product-family clusters leak"):
                self._fixture(Path(temp),family_leak=True)

    def test_rejects_duplicate_image_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"duplicate image bytes"):
                self._fixture(Path(temp),duplicate=True)

    def test_requires_multiple_distinct_product_views(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"enough distinct views"):
                self._fixture(Path(temp),views=1)

    def test_rejects_path_traversal_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); outside=root.parent/"clickit-outside.png"
            Image.new("RGB",(128,128)).save(outside)
            try:
                with self.assertRaisesRegex(ValueError,"traversal"): safe_media_path(root,"../outside.png")
                (root/"link.png").symlink_to(outside)
                with self.assertRaisesRegex(ValueError,"symlink"): safe_media_path(root,"link.png")
            finally:
                outside.unlink(missing_ok=True)

if __name__=="__main__":
    unittest.main()
