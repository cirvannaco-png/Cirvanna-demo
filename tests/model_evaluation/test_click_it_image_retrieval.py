import hashlib, json, sys, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.model_evaluation.click_it_image_retrieval.run import validate_record, ranking_metrics, safe_image_path, validate_privacy_preprocessing_manifest

class ClickItImageRetrievalTests(unittest.TestCase):
    def row(self):
        return {"schema_version":"1.0","query_id":"q1","cluster_id":"person-session-a","split":"test",
          "query_image_path":"queries/q1.png","query_image_sha256":"a"*64,"face_masked_before_inference":True,
          "subgroups":{"lighting":"studio","garment_type":"dress"},
          "candidates":[
            {"candidate_id":"p1-v1","product_id":"p1","image_path":"catalog/p1.png","image_sha256":"b"*64,"face_masked_before_inference":True,"relevance":4},
            {"candidate_id":"p2-v1","product_id":"p2","image_path":"catalog/p2.png","image_sha256":"c"*64,"face_masked_before_inference":True,"relevance":0}]}
    def test_requires_test_split_masking_and_unique_products(self):
        row=self.row(); self.assertEqual(validate_record(row,1)["query_id"],"q1")
        row=self.row(); row["face_masked_before_inference"]=False
        with self.assertRaisesRegex(ValueError,"face-masked"): validate_record(row,1)
        row=self.row(); row["candidates"][1]["product_id"]="p1"
        with self.assertRaisesRegex(ValueError,"unique"): validate_record(row,1)
    def test_ranking_metrics_reward_relevant_top_candidate(self):
        metrics=ranking_metrics(["p1","p2"],{"p1":4,"p2":0})
        self.assertEqual(metrics["recall@1"],1.0)
        self.assertEqual(metrics["ndcg@1"],1.0)
        self.assertEqual(metrics["mrr"],1.0)
        self.assertTrue(metrics["top1_hit"])
    def test_rejects_no_positive_qrel(self):
        row=self.row()
        for candidate in row["candidates"]: candidate["relevance"]=0
        with self.assertRaisesRegex(ValueError,"relevant"): validate_record(row,1)
    def test_rejects_path_traversal(self):
        with self.assertRaisesRegex(ValueError,"traversal"): safe_image_path(Path("/tmp/media"),"../private.png")

    def test_requires_reviewed_masking_manifest_bound_to_every_image_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            media=root/"media"
            (media/"queries").mkdir(parents=True)
            (media/"catalog").mkdir()
            query=media/"queries/q1.png"; query.write_bytes(b"masked-query")
            p1=media/"catalog/p1.png"; p1.write_bytes(b"masked-product-one")
            p2=media/"catalog/p2.png"; p2.write_bytes(b"masked-product-two")
            row=self.row()
            row["query_image_sha256"]=hashlib.sha256(query.read_bytes()).hexdigest()
            row["candidates"][0]["image_sha256"]=hashlib.sha256(p1.read_bytes()).hexdigest()
            row["candidates"][1]["image_sha256"]=hashlib.sha256(p2.read_bytes()).hexdigest()
            records=[validate_record(row,1)]
            evidence=root/"privacy-review.txt"; evidence.write_text("reviewed mask evidence",encoding="utf-8")
            manifest={
              "schema_version":"1.0","approval_status":"approved",
              "scope":"click_it_retrieval_evaluation","reviewed_by":"privacy-reviewer",
              "reviewed_at_utc":datetime.now(timezone.utc).isoformat(),
              "evidence_path":"privacy-review.txt",
              "evidence_sha256":hashlib.sha256(evidence.read_bytes()).hexdigest(),
              "face_masked_before_inference":True,"face_recognition":False,
              "detector_model_id":"cirvanna-face-masker","detector_source_revision":"a"*40,
              "detector_weights_sha256":"b"*64,
              "images":{
                "queries/q1.png":{"processed_image_sha256":row["query_image_sha256"],"faces_masked":1},
                "catalog/p1.png":{"processed_image_sha256":row["candidates"][0]["image_sha256"],"faces_masked":2},
                "catalog/p2.png":{"processed_image_sha256":row["candidates"][1]["image_sha256"],"faces_masked":0},
              },
            }
            manifest_path=root/"masking.json"; manifest_path.write_text(json.dumps(manifest),encoding="utf-8")
            result=validate_privacy_preprocessing_manifest(manifest_path,records,media)
            self.assertEqual(result["image_count"],3)
            self.assertEqual(result["faces_masked_total"],3)
            self.assertFalse(result["face_recognition"])
            p2.write_bytes(b"changed-after-review")
            with self.assertRaisesRegex(ValueError,"bytes do not match"):
                validate_privacy_preprocessing_manifest(manifest_path,records,media)

if __name__=="__main__": unittest.main()
