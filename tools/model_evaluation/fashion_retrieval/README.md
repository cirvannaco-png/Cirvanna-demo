# Fashion retrieval evaluation harness

This evaluator compares rankings from different encoders on the same query cases and fixed candidate universe. It deliberately does not download data or load models. Model-specific inference adapters must write rankings using the JSONL contract below; all systems are then scored on the same human-reviewed qrels.

## JSONL input

One record per query:

    {
      "schema_version": "1.0",
      "query_id": "query-000001",
      "cluster_id": "independent-source-cluster-01",
      "task_id": "image_to_catalog_text",
      "split": "test",
      "candidate_ids": ["product-a", "product-b", "product-c"],
      "qrels": {"product-a": 4, "product-b": 2, "product-c": 0},
      "rankings": {
        "cirvanna-fashion-clip": ["product-b", "product-a", "product-c"],
        "marqo-fashionsiglip": ["product-a", "product-b", "product-c"]
      },
      "excluded_product_ids": [],
      "subgroups": {"source_type": "studio", "query_type": "image"}
    }

- Qrels are human-reviewed grades from 0 to 4. Do not treat LLM labels as human ground truth.
- Candidate IDs define the same eligible candidate universe for every model on that query.
- Each ranking is an ordered subset of candidate IDs with no duplicates.
- Cluster ID must be the highest defensible independent resampling unit; justify it in the run manifest.
- Do not mix image-to-text, text-to-text, and image-to-image tasks in one run.
- Excluded product IDs are hard constraints. Any excluded item in the evaluated top-k fails that model's exclusion gate.
- Subgroups must be task-relevant and non-sensitive.

Do not put images, personal identifiers, account mappings, or user-level traces in this JSONL file or GitHub. Keep private source mappings and review records in a restricted evaluation workspace.

## Run

Pre-register the primary metric before evaluating the final test split:

    python tools/model_evaluation/fashion_retrieval/evaluate_retrieval.py       --input /secure/evaluation/fashion-retrieval-test.jsonl       --output /secure/evaluation/report.json       --baseline-model-id cirvanna-fashion-clip       --split test --k 10 --primary-metric ndcg_at_k       --bootstrap-samples 2000 --seed 20261120

Metrics include Recall@k, Precision@k, MRR@k, nDCG@k, top-1 hit rate, no-result rate, top-k fill, candidate coverage and hard-exclusion violations. Reports include paired challenger-minus-baseline deltas, 95% cluster-bootstrap intervals and subgroup slices. Fewer than two independent clusters yields no confidence interval rather than a degenerate interval.

This evaluates supplied rankings only. It does not prove inference ran, verify model/data licences, create labels, or establish production readiness. Pin model revisions, artifact hashes, processors, dependencies, dataset snapshots, inference commands, hardware and rights decisions in a separate run manifest.

## Tests

    python -m unittest discover -s tests/model_evaluation -v
