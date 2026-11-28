# Cirvanna Click It image-to-image benchmark

This runner evaluates the Cirvanna-owned ResNet-50 image embedding candidate against a fixed, rights-cleared catalogue image pool. It is separate from the existing image-to-catalog-text benchmark and never represents retrieval similarity as a probability.

## Frozen input contract

Use one JSONL row per test query. Every query must contain the exact same candidate pool and candidate image digests.

    {
      "schema_version": "1.0",
      "query_id": "query-000001",
      "cluster_id": "opaque-subject-session-001",
      "split": "test",
      "query_image_path": "queries/query-000001.png",
      "query_image_sha256": "<64 lowercase hex>",
      "face_masked_before_inference": true,
      "subgroups": {"lighting": "studio", "garment_category": "dress"},
      "candidates": [
        {
          "candidate_id": "variant-001",
          "product_id": "product-001",
          "image_path": "catalog/variant-001.png",
          "image_sha256": "<64 lowercase hex>",
          "face_masked_before_inference": true,
          "relevance": 4
        }
      ]
    }

Relevance is an independently adjudicated integer from 0 to 4. Candidate IDs and product IDs must be unique within a query. Query and candidate media paths must be relative to the restricted media root, remain inside it, and match their exact SHA-256. All images must be preprocessed under the approved face-masking protocol before inference. The current runner checks the declared masking gate and rights evidence; it does not independently prove the pixel-level mask.

The same query subject/source cluster, product family, or duplicate image must not cross training, validation and test. Candidate pool identity must be identical for every query in the final run. Keep images, labels, rights receipts and manifests in the restricted workspace, never in Git.

## Run

First train the model using the Click It training guide. The training report must bind the checkpoint digest and full source commit. Run evaluation from that same clean source revision:

    python tools/model_evaluation/click_it_image_retrieval/run.py \
      --input /restricted/click-it/test-queries.jsonl \
      --media-root /restricted/click-it/media \
      --rights-manifest /restricted/click-it/data-rights.manifest.json \
      --checkpoint /restricted/click-it/run-001/clickit-image-encoder-state.pt \
      --training-report /restricted/click-it/run-001/training-report.json \
      --output /restricted/click-it/run-001/image-to-image-report.json \
      --device cuda

CUDA is the default and fails closed if unavailable. CPU may be used only for diagnostic smoke runs, not production throughput claims. The evaluator loads only a local state dictionary with weights_only=True; it does not download pretrained weights or execute remote model code.

## Report

The report binds the exact checkpoint, training report, source revision, test JSONL, rights manifest and candidate-pool digest. It includes query-macro Recall@1/5/10, Precision@1/5/10, nDCG@1/5/10, MRR, top-1 hit rate and subgroup means. Scores are ranking similarities, not calibrated confidence.

This first version does not compute cluster-bootstrap confidence intervals, calibrated abstention, latency/throughput, or independent privacy certification. The runner's declared face-mask flag is not a substitute for signed preprocessing attestation or a visual audit. Do not enable Click It from this report alone.
