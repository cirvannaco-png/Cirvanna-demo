# Fashion retrieval benchmark and execution tools

This directory contains two distinct tools:

1. `run_retrieval.py` — loads pinned model snapshots and generates matched rankings from a private, fixed query/candidate dataset.
2. `evaluate_retrieval.py` — evaluates supplied rankings against the same graded human relevance labels.

The runner does not upload source images. The evaluator does not download models. Keep both the input dataset and run outputs in an approved restricted evaluation workspace.

## Current Cirvanna task

The existing Vision Intelligence path uses the pinned FashionCLIP model to create query-image embeddings and compare them with text representations built from live Commerce/Catalog offers. Its current candidate path does **not** embed the Catalog product images.

That is why the first benchmark supports:

- `image_to_catalog_text`: query image → frozen Catalog offer text.
- `text_to_catalog_text`: text query → frozen Catalog offer text.

Do not combine these with a future `image_to_catalog_image` benchmark. That will be a separate task with licensed catalogue images and a separate comparison report.

## Safe, pinned model loading

The model registry in `run_retrieval.py` defines four model identities:

| Model ID | Hugging Face repository | Loader |
|---|---|---|
| `cirvanna-fashion-clip` | `patrickjohncyh/fashion-clip` | Transformers CLIP, matching the Vision service class |
| `marqo-fashionclip` | `Marqo/marqo-fashionCLIP` | OpenCLIP from a pinned local snapshot |
| `marqo-fashionsiglip` | `Marqo/marqo-fashionSigLIP` | OpenCLIP from a pinned local snapshot |
| `zooclaw-fashionsiglip2` | `srpone/zooclaw-fashionsiglip2` | Standard Transformers/SigLIP model |

Each model is downloaded at a full 40-character commit SHA. The baseline SHA is frozen to the exact revision in Cirvanna's current Vision Intelligence implementation. Challenger SHA values are explicit command-line inputs; a moving `main` reference and short SHA are rejected.

Marqo's model cards recommend OpenCLIP and their example Transformers loaders require `trust_remote_code=True`. The runner instead uses OpenCLIP's `local-dir:` loader with the pinned snapshot and does not execute remote model-repository Python. For FashionSigLIP, whose OpenCLIP config points to an external tokenizer repository, the runner redirects the tokenizer to the tokenizer files inside that same pinned model snapshot. It does not download an unpinned tokenizer from a second repository. ZooClaw and the baseline are also loaded with `trust_remote_code=False`.

The Hub snapshot download uses an explicit file allow-list for each model, avoiding duplicate PyTorch/Transformers/OpenCLIP copies of the same large checkpoint. The allow-list includes the model weight, model configuration, processor/tokenizer assets and README/licence notices where present.

Every downloaded snapshot file is SHA-256 hashed. The private run manifest records all model revisions, file sizes/hashes, runtime package versions, device, input JSONL digest and query/task counts.

## Input JSONL

One record per query:

    {
      "schema_version": "1.0",
      "query_id": "query-000001",
      "cluster_id": "product-source-cluster-01",
      "task_id": "image_to_catalog_text",
      "split": "test",
      "query_image_path": "queries/query-000001.jpg",
      "candidate_ids": ["variant-a", "variant-b"],
      "candidate_texts": {
        "variant-a": "Fashion or beauty marketplace product. Navy cotton shirt ...",
        "variant-b": "Fashion or beauty marketplace product. Red wool coat ..."
      },
      "qrels": {"variant-a": 4, "variant-b": 0},
      "excluded_product_ids": [],
      "subgroups": {"source_type": "studio", "query_type": "image"}
    }

For `text_to_catalog_text`, provide `query_text` instead of `query_image_path`.

Candidate text must come from the same frozen Catalog/Commerce snapshot. For parity with current code, its content should match the Vision service's `_offer_description()` and be truncated to 1,000 characters before tokenization. The text query path uses the same prefix as the current production-intended description-search route.

The input contract requires the same candidate IDs and qrels for every model. Use human-reviewed graded labels; do not describe LLM-generated labels as human ground truth. Split and deduplicate by product/source/near-duplicate clusters before the run. Do not tune on final-test qrels.

Image paths must be relative to `--media-root` and remain inside that directory. The runner rejects path traversal. The source images are read locally and are not written into the ranking output, manifest, or GitHub.

## Install dependencies

Use a locked Python 3.11+ research environment. At minimum, the runtime needs PyTorch, Transformers, Hugging Face Hub, Safetensors, Pillow, NumPy, and OpenCLIP with support for the `local-dir:` schema. `requirements-research.txt` declares the runtime families, but its ranges are **not** a reproducibility lock. Generate and retain an exact lockfile with hashes before any official comparison, and attach its digest to the experiment record.

## Generate rankings

The baseline alone is not a comparison. Include the baseline and at least one challenger. Example:

    python tools/model_evaluation/fashion_retrieval/run_retrieval.py \
      --input /secure/evaluation/fashion-retrieval-test.jsonl \
      --media-root /secure/evaluation/media \
      --output /secure/evaluation/fashion-retrieval-rankings.jsonl \
      --models cirvanna-fashion-clip zooclaw-fashionsiglip2 \
      --revision zooclaw-fashionsiglip2=<FULL_40_CHAR_COMMIT_SHA> \
      --device auto --batch-size 16

Add the Marqo model IDs and their full immutable revision arguments when those SHAs have been independently recorded. Models are loaded sequentially to reduce peak memory. If using CPU, measure runtime and memory; do not treat a CPU smoke run as production throughput evidence.

## Score rankings

Pre-register the primary metric before opening final-test results:

    python tools/model_evaluation/fashion_retrieval/evaluate_retrieval.py \
      --input /secure/evaluation/fashion-retrieval-rankings.jsonl \
      --output /secure/evaluation/fashion-retrieval-report.json \
      --baseline-model-id cirvanna-fashion-clip \
      --split test --k 10 --primary-metric ndcg_at_k

Metrics include Recall@k, Precision@k, MRR@k, nDCG@k, top-1 hit rate, no-result rate, top-k fill, candidate coverage and hard-exclusion violations. Reports include paired challenger-minus-baseline deltas, 95% cluster-bootstrap intervals and subgroup slices. Fewer than two independent clusters yields no confidence interval rather than a degenerate interval.

The runner ranks the full supplied candidate pool and applies no calibrated no-match threshold. Therefore its no-result rate is not a meaningful quality signal in this initial version. Similarity outputs are ranking scores, never probabilities or calibrated confidence.

## Tests

    python -m unittest discover -s tests/model_evaluation -v

Tests cover the schema, fixed candidate metadata, strict revision pins, deterministic ranking, invalid vectors and media path traversal. CI compiles the runners and runs these offline unit tests; CI does not download model weights or claim model inference executed.
