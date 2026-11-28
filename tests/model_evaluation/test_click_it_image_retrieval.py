import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.model_evaluation.click_it_image_retrieval.run import validate_record, ranking_metrics, safe_image_path

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
if __name__=="__main__": unittest.main()
