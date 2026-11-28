# Fashion retrieval challenger benchmark

- **Status:** Benchmark specification; execution pending approved compute and rights-cleared data
- **Date:** 2026-11-20
- **Governing protocol:** [AI model competition and logic transfer](ai-model-competition-and-logic-transfer.md)
- **Product surface:** Marketplace visual discovery, Click It retrieval, and PNELLY Look It retrieval (separate routes and datasets)

## 1. Objective

Determine whether fashion-specific external encoders perform better than Cirvanna's existing FashionCLIP implementation on the exact retrieval tasks Cirvanna needs. If a challenger wins, isolate the technical reason and independently implement the useful principle within Cirvanna. Then prove the adapted Cirvanna version beats the frozen Cirvanna baseline.

This is not a proposal to replace FashionCLIP. Marqo FashionCLIP, Marqo FashionSigLIP and ZooClaw-FashionSigLIP2 are challengers. None is selected.

## 2. Current Cirvanna baseline — exact behavior to preserve

The current source of truth is services/vision-intelligence/app/main.py.

| Element | Current implementation |
|---|---|
| Model | patrickjohncyh/fashion-clip |
| Reviewed revision pin | afacf5e5851d5979ab030e228eab60e2c95a912c |
| Model family | CLIP ViT-B/32 |
| Image path | _image_embedding() uses the pinned Transformers model processor and normalized image features |
| Text path | _text_embedding() uses the same model's normalized text features, max length 77 |
| Product representation | _offer_description() combines product name, description, category, brand, SKU, structured attributes and offer options |
| Candidate ranking | _rank_offers() computes cosine similarity between the query embedding and each offer's text embedding |
| Catalog boundary | _live_offers() fetches current Commerce offers and enriches them with active Catalog product descriptions/attributes; the worker bounds the candidate pool at 1,000 offers |
| Score semantics | Similarity ranking only; not a probability, calibrated confidence or fit grade |
| Result authority | Candidate results only; the downstream policy and CAL path remains required |

### Important task distinction

Despite product image URLs being present in the enriched Catalog records, the current _rank_offers() path does **not** fetch or embed those catalog product images. The existing visual search is image-to-catalog-text similarity. It is not a true image-to-image product retrieval benchmark.

Therefore run two separate tracks:

- **Track A — parity track:** reproduce current Cirvanna image-to-text metadata retrieval and text-to-text search. This is the valid apples-to-apples comparison with the current baseline.
- **Track B — image-to-image track:** query-image to licensed catalog-product-image retrieval. The benchmark runner now supports the `image_to_catalog_image` task with one pinned local catalogue image per candidate and a separate digest manifest. This is a separate capability experiment. It may reveal a stronger architecture, but it cannot be reported as a direct win over Track A. No approved Cirvanna catalogue-image corpus or final human qrels have yet been supplied, so the experiment has not been run and no model is selected.

Do not merge the metrics of these tracks.

## 3. Challenger set

The exact model revision, model files, processor files, dependency lock, and SHA-256 digests must be pinned in the run manifest before inference. Do not use floating main revisions.

| Candidate | Publicly described method | Why it is worth testing | Current decision |
|---|---|---|---|
| [Cirvanna FashionCLIP baseline](https://huggingface.co/patrickjohncyh/fashion-clip) | CLIP ViT-B/32, fashion fine-tuning | Current pinned baseline; model card describes training on more than 800,000 Farfetch products and notes product-image/long-caption distribution limits | Baseline only; not assumed superior |
| [Marqo FashionCLIP](https://huggingface.co/Marqo/marqo-fashionCLIP) | ViT-B/16; Generalised Contrastive Learning (GCL) over category, style, colour, material, keywords and detail signals | Tests whether richer multi-attribute supervision improves the same cross-modal task | Challenger; not selected |
| [Marqo FashionSigLIP](https://huggingface.co/Marqo/marqo-fashionSigLIP) | SigLIP ViT-B/16; GCL multi-attribute supervision | Tests a different contrastive objective/backbone and Marqo's reported retrieval improvements | Challenger; model-card gain is vendor-reported, not Cirvanna evidence |
| [ZooClaw-FashionSigLIP2](https://huggingface.co/srpone/zooclaw-fashionsiglip2) | SigLIP2 ViT-B/16 at 384px; paper describes full fine-tuning, distillation and WiSE-FT interpolation | Tests a higher-resolution, larger fashion-specialized encoder and a knowledge-distillation route | Challenger; provenance, data rights and resource costs require review |

Marqo's model cards report improvements over FashionCLIP on their evaluation protocol. Those figures are hypotheses to reproduce, not expected Cirvanna results. ZooClaw's published paper/model card also reports benchmark gains; independently reproduce them before using them in a decision. Do not compare a vendor's reported MRR/recall with a Cirvanna result from a different test set.

A hosted Marqo FashionSigLIP 2 offering mentioned by the FashionSigLIP model card is not automatically an available open checkpoint. Treat hosted API testing as a separate vendor evaluation with a pinned API/model release, contractual terms, retention, geography, DPA and per-request cost review.

## 4. Data plan and rights gate

### 4.1 Primary benchmark candidates

1. **LookBench** — https://huggingface.co/datasets/srpone/look-bench  
   Intended to evaluate product retrieval under studio and street-style conditions, including multi-item queries. Use only after pinning an immutable dataset revision and reviewing image source provenance, underlying image rights, permitted commercial use, redistribution, and any consent/retention conditions. A dataset-card licence declaration alone does not resolve the rights to each underlying photograph. Separate real/street-style and studio/image-source slices in reports.

2. **Fashion200K pooled evaluation** — https://huggingface.co/datasets/srpone/fashion200k-pooled-eval  
   Supplementary retrieval benchmark only. Its graded judgments are model-generated/LLM-assisted rather than a fully human ground-truth set; report it separately and never use it as the sole basis for selection. Audit the referenced corpus-image rights independently; the pooled qrels do not themselves grant rights to the original images.

3. **Cirvanna controlled catalogue benchmark** — primary product-relevance gate for a Cirvanna decision. For the first parity track, build from an approved frozen Commerce/Catalog snapshot containing exact variant IDs, the exact `_offer_description()` text consumed by Vision Intelligence, current eligibility state, and documented rights to the text/metadata source. Product images are **not required** for the current image-query-to-Catalog-text comparison. A rights-cleared product-image corpus is required only for the separate future image-to-image track. Use opaque identifiers in evaluation exports. Candidate generation must be offline against a fixed snapshot, not a live marketplace whose inventory or offers change between runs.

4. **Human-reviewed query set** — create a consented, rights-cleared set of realistic product/outfit queries. Include short keyword queries, detailed natural-language descriptions, attribute combinations, image queries, and multi-item outfit queries. Every candidate in each fixed query pool must receive an explicit 0–4 relevance grade from two independent blinded reviewers, including zero-grade items. Reviewers separately flag an explicit exclusion/constraint violation. A third independent adjudicator must resolve any disagreement in either field. Use `tools/model_evaluation/fashion_retrieval/build_qrels.py` to aggregate the review records; do not generate human labels with an LLM and present them as human ground truth. The output carries complete qrels and human-adjudicated violation IDs without reviewer keys or raw annotations.

### 4.2 Datasets not approved for commercial development

- [ZooClaw fashion evaluation dataset](https://huggingface.co/datasets/srpone/zooclaw-fashion-eval) displays a CC BY-NC 4.0 licence. Do not use it for Cirvanna commercial evaluation, training, or derivative data work without separate written permission that covers the intended use.
- Any public dataset whose image rights, people/photographer rights, source terms, redistribution rights or commercial use are unresolved remains REVIEW_REQUIRED, even when the Hugging Face repository has permissive metadata.
- Do not use scraped marketplace content or private user photos as a substitute for rights-cleared test data.

### 4.3 Split and leakage controls

Freeze a dataset manifest containing every source revision and file digest. Split by product identity and near-duplicate image cluster—not random rows alone. Where source structure allows, also hold out brands and a later time window. Keep all variants, crops, alternate views and duplicate images for the same product in one split. Keep validation data available for prompt/template or threshold selection; do not tune on final test labels.

Report every split's query count, unique product count, category composition, source composition, image type, query type, language and known limitations. If the dataset cannot support a reliable slice, mark the slice underpowered rather than extrapolating.

### 4.4 First benchmark phasing

Use two distinct phases:

- **Engineering pilot:** validate the fixed candidate snapshot, query/image decoding, model loading, processor outputs, artifact manifests, failure handling, annotation quality and latency/resource collection on a rights-cleared development split. Pilot metrics are diagnostic; do not select a winner from this stage.
- **Final matched evaluation:** freeze an untouched query/product-cluster holdout. Before exposing final qrels, declare `nDCG@10` as the primary ranking metric, record the minimum practically important effect, and retain MRR@10, Recall@10, Precision@10, top-1 hit rate and hard-constraint violations as secondary measures/gates. Use query/source-clustered paired bootstrap intervals. The practical effect threshold must be defined from the product decision before unblinding final-test results, not chosen after seeing which model wins.

For an initial pilot, size the human-reviewed sample and candidate pool using reviewer capacity and the available rights-cleared catalogue, and document the resulting limitations. Do not extrapolate underpowered subgroup slices to the full market.

## 5. Matched experiment design

### 5.1 Freeze the common conditions

All models must receive:

- the same query text or exact decoded query-image bytes;
- the same frozen catalogue snapshot and eligible candidate IDs;
- the same relevance labels and hard constraints;
- the same top-k cutoffs and evaluation code;
- the same split and excluded examples;
- the same runtime class and concurrency settings for operational comparison.

Use each model's official processor and tokenizer, because forcing one model's preprocessing onto another is invalid. Record exact processor revision, resize/crop/normalization and text-tokenization behavior. Keep user-written query text unchanged. If a query template is required, use a small pre-registered template set and do not tune on final test data.

### 5.2 Track A: current-path parity

Test separately:

1. text query → Catalog offer text;
2. image query → Catalog offer text.

For image-to-text, compare the current Cirvanna FashionCLIP route with each challenger's own aligned image and text encoders. Do not compare embeddings from different model spaces directly; each model ranks with its own image/text space.

For every case, freeze the candidate list at the same size. Include the production-relevant range around the current service's 1,000-offer ceiling, plus smaller fixed candidate pools to understand rank sensitivity. Preserve current Catalog/Commerce eligibility rules before ranking. The benchmark does not authorize any offer for display.

### 5.3 Track B: true visual retrieval

Only run after a rights-cleared catalogue image corpus exists.

Test query image → product image, with the same image candidate set for every model. Keep this result distinct from image-to-text. Also report multi-view aggregation as its own ablation rather than silently giving one model more product images or metadata.

### 5.4 Click It and Look It stay separate

- **Click It** benchmark inputs are product-reference photos. The production privacy pipeline must mask people before quality scoring, embedding, retrieval or downstream publication. Benchmark privacy correctness separately from retrieval relevance. Never add face recognition, identity search, age estimation or face embeddings.
- **Look It** benchmark inputs are user-supplied outfit references and use the separate PNELLY consent/route. Evaluate outfit decomposition and item-component retrieval as separate stages. Do not reuse Click It's labels or merge the two endpoints into one product metric.

No real customer image enters a benchmark until the image's exact purpose-specific consent, resource binding, masking, retention/deletion, access controls and approved evaluation basis are verified. Prefer controlled, consented and rights-cleared benchmark media.

## 6. Metrics and error taxonomy

### 6.1 Retrieval quality

Report at minimum:

- Recall@1, Recall@5 and Recall@10;
- MRR@10;
- nDCG@10 using graded relevance judgments;
- Precision@1 and Precision@5;
- exact product/SKU/variant top-1 accuracy where exact identity is a valid ground truth;
- no-result rate and eligible-candidate coverage.

Do not substitute raw cosine values for retrieval metrics.

### 6.2 Product usefulness and policy correctness

Report category correctness and declared attribute agreement for colour, material, silhouette, garment type, occasion and other available Catalog facts. Record confusions such as similar category/different product, correct garment/wrong colour, correct style/wrong material, wrong variant, brand shortcut, background/pose shortcut, and failure on street/occluded/multi-item images.

Explicit NPL exclusions, human-adjudicated constraint violations, unsupported products, inactive/out-of-stock offers, ownership, consent and CAL failures are hard gates. The ranking evaluator fails a model if a returned top-k candidate is flagged either by a declared excluded-product ID or by independent human adjudication. A ranker must never bypass these. The evaluation must verify that model changes cannot expose product/merchant details before CAL authorization.

### 6.3 Subgroup and robustness analysis

Pre-register slices by task-relevant, non-sensitive evidence such as:

- studio versus street-style images;
- short keyword versus long descriptive query;
- single item versus multi-item outfit;
- garment/product category;
- image resolution, lighting, blur, occlusion and viewpoint;
- language and spelling variation where supported;
- declared climate/occasion context where represented in the task.

Do not infer ethnicity, religion, age, gender identity, skin tone, body traits or cultural identity from a photograph. If a user explicitly supplies a cultural requirement, test it as a declared constraint, not as a visual demographic classifier.

### 6.4 Statistical analysis

Pre-register the primary metric and minimum practically important improvement before opening the final test set. Use paired query-level comparisons with a query/product/source-clustered bootstrap; use 95% confidence intervals and state the resampling unit. Where queries share participants, products, outfits or near-duplicate sources, cluster at the highest relevant independent unit. Report full distributions and failures, not only averages.

Human review must be blinded to model identity, ranking score and rank. Use two independent reviewers per query-candidate pair and an adjudicator for disagreement. Document the rubric and reviewer agreement. Keep private per-reviewer records outside GitHub.

## 7. Operational benchmark

Run each model under the target deployment classes: CPU fallback if required, and the intended GPU class. Pin framework, CUDA, driver, tokenizer, processor, ONNX/runtime and dependency versions.

Measure:

- model and processor download/startup time and offline cold-start behavior;
- weight and cache storage size;
- peak host RAM and GPU VRAM;
- image and text embedding latency;
- complete query-to-top-k latency at P50/P95;
- throughput at declared concurrency and batch sizes;
- error/timeout rate and recovery behavior;
- cost per 1,000 queries, including model hosting, compute, storage and API charges.

Measure both warm and cold conditions. Separate encoding cost from catalogue/index build cost. The production service currently embeds offer text on demand and uses a bounded in-process cache; record the cost of this architecture and test any proposed precomputed-index strategy as a separate systems change.

## 8. Logic-transfer experiments to consider after external results

Only pursue a method when the diagnostic evidence supports it. Candidate hypotheses include:

| Hypothesis | Cirvanna-owned experiment | Required ablation |
|---|---|---|
| Richer attribute supervision improves retrieval | Build a canonical multi-view offer representation from approved Catalog category, colour, material, fit/silhouette, style and product text | Current single concatenated description vs structured attribute views vs late fusion |
| False negatives and broad similarity harm fine-grained ranking | Use human-graded relevance and carefully defined positive/negative pairs for a Cirvanna-owned ranking objective | Binary vs graded labels; random negatives vs reviewed hard negatives |
| One-stage retrieval misses exact details | Use a two-stage candidate retrieval then a lightweight Cirvanna reranker over structured product facts | Current cosine ordering vs candidate+reranker; keep candidate recall fixed |
| Multiple images improve exact visual match | Aggregate licensed product views or crops in a product-level representation | Single primary image vs multi-view; same number of images per product |
| Generalization is overstated by random splits | Use product/brand/time-held-out evaluation and train/validation-only selection | Random split diagnostic vs leakage-resistant split |
| Retrieval quality can improve without increasing model size | Distill a Cirvanna-owned smaller encoder/ranker using commercially cleared teacher outputs and approved labels | Teacher vs student quality, subgroup error, latency and cost |

The table contains hypotheses, not approved changes. In particular, do not train on a competitor's restricted evaluation data or reproduce its code. Distillation requires an independent legal review of teacher-output terms, data rights, and intended derivative use.

## 9. Acceptance and stop conditions

A challenger may be marked BENCHMARKED only when the model, processor, code, data, and runner are pinned; the rights review is recorded; the exact matched test has run; and the report includes uncertainty, errors, subgroups, and resource cost.

A logic transfer may be marked VALIDATED_FOR_SCOPED_PILOT only when it beats the frozen Cirvanna baseline on the pre-registered primary metric and practical threshold, with acceptable uncertainty, zero hard policy violations, no material subgroup regression, and acceptable operational cost. The full product-system release gates remain separate.

Stop and mark BLOCKED when provenance, commercial rights, dataset rights, model weights, compute, ground truth, human-review capacity, privacy approval or exact baseline reproducibility is missing. Do not interpret a blocked run as a failed model or a successful model.

## 10. Executable inference runner and ranking evaluator

The repository now includes four connected data/evaluation stages:

1. `tools/model_evaluation/fashion_retrieval/build_qrels.py` validates two independent blinded reviews for every query-candidate pair and requires independent adjudication on disagreement.
2. `services/vision-intelligence/app/retrieval_snapshot_export.py` calls the Vision service's actual `_live_offers()` implementation and exports only variant ID plus exact offer search text, preserving Commerce order. It must be run from an isolated build of this reviewed branch inside a trusted Vision service environment; it is not a public endpoint and does not require deploying the research branch to production.
3. `tools/model_evaluation/fashion_retrieval/prepare_cases.py` joins complete reviewed qrels to the exact frozen, eligible Catalog/Commerce offer text and candidate order.
4. `tools/model_evaluation/fashion_retrieval/run_retrieval.py` loads pinned model snapshots and generates rankings over the common query/candidate JSONL set.
4. `tools/model_evaluation/fashion_retrieval/evaluate_retrieval.py` scores those rankings on the same full qrels and applies both declared-exclusion and human-adjudicated hard gates.

The inference runner supports the current Cirvanna FashionCLIP baseline, Marqo FashionCLIP, Marqo FashionSigLIP and ZooClaw-FashionSigLIP2. Model snapshots are loaded sequentially. The baseline uses the same Transformers CLIP class as the production-intended Vision service. Marqo models use OpenCLIP from the pinned local snapshot; ZooClaw uses standard Transformers/SigLIP. All loaders disable remote model-repository code execution.

Every challenger requires a full 40-character immutable commit SHA. The runner rejects short hashes and moving branch names, and it freezes Cirvanna's FashionCLIP baseline to the existing production-reviewed pin. It hashes every file in each downloaded model snapshot and writes a private manifest with file digests, model revisions, runtime versions, hardware/device, input digest, query count and task identity.

Input media is read from a caller-supplied local directory, with path traversal rejected. Source images are not uploaded or included in the rankings/manifest. Only opaque candidate IDs, rankings, cosine similarity diagnostics, qrels and task-grounded subgroup metadata are written. Similarity remains a ranking score, never a probability.

The evaluator requires one relevance grade per candidate in the fixed pool and computes Recall@k, Precision@k, MRR@k, nDCG@k, top-1 hit rate, no-result rate, top-k fill, candidate coverage, declared-exclusion and human-adjudicated constraint violations, paired challenger-minus-baseline deltas, cluster-bootstrap 95% intervals and subgroup reports. It rejects mixed tasks, inconsistent model sets, out-of-pool results, invalid grades and malformed exclusions.

The runner deliberately supports only image-to-Catalog-text and text-to-Catalog-text in this first increment. True image-to-image retrieval remains a separate future track. Since the runner ranks every supplied candidate and applies no calibrated no-match threshold, its no-result rate is not a meaningful quality signal yet.

The runner, evaluator, README, dependency-family declaration, unit tests and GitHub Actions workflow are in this PR. CI compiles both scripts, runs the offline contract tests and validates both CLIs. CI does not download model weights or prove any real inference has run.

## 11. Current status

- Cirvanna baseline and route semantics have been inspected in `services/vision-intelligence/app/main.py`.
- The exact Cirvanna FashionCLIP revision is pinned to `afacf5e5851d5979ab030e228eab60e2c95a912c`; the service's model quality and live weight/GPU operation remain unvalidated.
- Marqo FashionCLIP and Marqo FashionSigLIP are the first pinned challengers, not selected replacements. ZooClaw-FashionSigLIP2 remains a later challenger pending its full immutable SHA.
- **Two challengers are now immutably pinned and Hub-verified:** Marqo FashionCLIP `44f4c655124ed71e90cbf528d82f508d69d8a81b` and Marqo FashionSigLIP `c56244cc94f92419e8369fa71efdaf403b124ce8`. The exact revision trees and OpenCLIP checkpoint files were verified through revision-qualified Hub paths; those pins are frozen in `run_retrieval.py`. ZooClaw-FashionSigLIP2 remains unpinned and is excluded from the first run until its 40-character SHA is verified.
- The runner records per-model download/hash/load time, candidate-text embedding time, query-to-top-k P50/P95, and CUDA peak memory when available. The run manifest also stores query-image SHA-256 digests without storing image bytes.
- The runner's dependency ranges are not an environment lock. Generate a complete lock with hashes and retain its digest before official evaluation.
- No matched inference benchmark, human relevance evaluation, GPU/CPU comparison, or logic-transfer result has been run.
- A previous Hugging Face CPU job attempt returned HTTP 402 before job creation. No paid job was started. Do not retry paid compute without approved credits/payment.
- LookBench image-level rights/provenance and the ZooClaw evaluation dataset's non-commercial restriction remain explicit gates. The Fashion200K pooled qrels are supplementary and model-assisted, not human ground truth.
- The private Cirvanna catalogue snapshot, rights-cleared query corpus, independent human qrels and approved compute path are still required for a product-level decision.
