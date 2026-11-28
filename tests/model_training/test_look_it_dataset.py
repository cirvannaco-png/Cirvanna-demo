import hashlib, json, sys, tempfile, unittest
from pathlib import Path
from datetime import date, timedelta
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.model_training.look_it.validate_dataset import validate_sample, split_manifest_digest, safe_media_path

class LookItDatasetContractTests(unittest.TestCase):
    def test_rejects_cross_split_or_invalid_boxes(self):
        sample={"sample_id":"s1","cluster_id":"person-1","split":"train","image_sha256":"a"*64,"width":256,"height":256,"components":[{"category":"upper_body","bbox":[0.1,0.1,0.8,0.9]}]}
        self.assertEqual(validate_sample(sample,1,{"upper_body"})["sample_id"],"s1")
        sample["components"][0]["bbox"]=[0.8,0.1,0.2,0.9]
        with self.assertRaisesRegex(ValueError,"normalized"): validate_sample(sample,1,{"upper_body"})
    def test_split_digest_is_order_independent(self):
        a={"sample_id":"a","cluster_id":"c1","split":"train"}
        b={"sample_id":"b","cluster_id":"c2","split":"test"}
        self.assertEqual(split_manifest_digest([a,b]),split_manifest_digest([b,a]))
    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"traversal"): safe_media_path(Path(temp),"../escape.jpg")
    def test_rejects_symlink_media(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); outside=root.parent/"outside-lookit.jpg"
            Image.new("RGB",(128,128)).save(outside)
            try:
                (root/"link.jpg").symlink_to(outside)
                with self.assertRaisesRegex(ValueError,"symlink"): safe_media_path(root,"link.jpg")
            finally: outside.unlink(missing_ok=True)

if __name__=="__main__": unittest.main()

class LookItDatasetManifestTests(unittest.TestCase):
    def _fixture(self, root: Path, *, leak_cluster: bool = False):
        import datetime, json
        from tools.model_training.look_it.validate_dataset import validate_dataset
        from tools.model_evaluation.fashion_retrieval.data_rights import sha256_file
        media = root / "media"
        media.mkdir()
        rows = []
        for index, split in enumerate(("train", "validation", "test")):
            name = f"{split}.png"
            path = media / name
            Image.new("RGB", (128, 128), (40 + index * 30, 90, 120)).save(path)
            cluster = "same-person" if leak_cluster and split in {"train", "validation"} else f"person-{split}"
            rows.append({
                "sample_id": f"sample-{split}", "cluster_id": cluster, "split": split,
                "image_path": name, "image_sha256": sha256_file(path),
                "width": 128, "height": 128,
                "components": [{"category":"upper_body","bbox":[0.1,0.1,0.8,0.9]}],
            })
        annotations = root / "annotations.jsonl"
        annotations.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        evidence = root / "rights-evidence.txt"
        evidence.write_text("approved test fixture", encoding="utf-8")
        rights = {
            "schema_version":"1.0", "approval_status":"approved",
            "scope":"look_it_decomposition_evaluation", "reviewed_by":"reviewer-1",
            "reviewer_role":"data-rights-owner",
            "reviewed_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source_provenance":"test fixture", "evidence_path":str(evidence),
            "evidence_sha256":sha256_file(evidence), "commercial_evaluation_permitted":True,
            "human_review_permitted":True,
            "retention_until":(datetime.date.today()+datetime.timedelta(days=30)).isoformat(),
            "contains_personal_images":False, "depicted_person_consent_status":"not_applicable",
        }
        rights_path = root / "rights.json"
        rights_path.write_text(json.dumps(rights), encoding="utf-8")
        split_digest = split_manifest_digest(rows)
        manifest = {
            "schema_version":"1.0", "dataset_id":"lookit-test-dataset",
            "rights_manifest_sha256":sha256_file(rights_path),
            "annotations_sha256":sha256_file(annotations), "sample_count":len(rows),
            "categories":["upper_body"], "split_manifest_sha256":split_digest,
        }
        manifest_path = root / "dataset.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return validate_dataset(manifest_path, annotations, media, rights_path)

    def test_validates_full_rights_bound_subject_disjoint_dataset(self):
        with tempfile.TemporaryDirectory() as temp:
            result = self._fixture(Path(temp))
            self.assertEqual(result["status"], "validated_for_training_input_only")
            self.assertEqual(result["split_counts"], {"test":1,"train":1,"validation":1})

    def test_rejects_subject_cluster_leakage_between_splits(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "clusters leak"):
                self._fixture(Path(temp), leak_cluster=True)
