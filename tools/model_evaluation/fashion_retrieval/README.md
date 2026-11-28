# Fashion retrieval benchmark and execution tools

This directory contains two distinct tools:

1. `run_retrieval.py` — loads pinned model snapshots and generates matched rankings from a private, fixed query/candidate dataset.
2. `evaluate_retrieval.py` — evaluates supplied rankings against the same graded human relevance labels.

The runner does not upload source images. The evaluator does not download models. Keep both the input dataset and run outputs in an approved restricted evaluation workspace.

## Current Cirvanna task

The existing Vision Intelligence path uses the pinned FashionCLIP model to create query-image embeddings and compare them with text representations built from live Commerce/Catalog offers. Its current candidate path does **not** embed the Catalog product images.

The benchmark runner supports three explicitly separate tasks:

- `image_to_catalog_text`: query image → frozen Catalog offer text (parity with the current Click It/Look It retrieval representation).
- `text_to_catalog_text`: text query → frozen Catalog offer text (text-search parity).
- `image_to_catalog_image`: query image → frozen, rights-cleared Catalog product images (the dedicated Click It image-to-image track).

Do not combine task IDs in one run or pool their metrics. Image-to-image requires an explicit `candidate_image_paths` mapping for every candidate ID and a rights manifest that covers the source catalogue photographs and depicted people. Candidate images are read only from the restricted local `--media-root`; no remote URLs are fetched. The private run manifest records query and candidate image SHA-256 digests and sizes, never the image bytes or absolute media paths. This track is not a parity comparison with image-to-text; it gets a separate evaluation report and preregistered success gate.

## Safe, pinned model loading

The model registry in `run_retrieval.py` defines four model identities:

| Model ID | Hugging Face repository | Loader |
|---|---|---|
| `cirvanna-fashion-clip` | `patrickjohncyh/fashion-clip` | Transformers CLIP, matching the Vision service class |
| `marqo-fashionclip` | `Marqo/marqo-fashionCLIP` | OpenCLIP from a pinned local snapshot | `44f4c655124ed71e90cbf528d82f508d69d8a81b` |
| `marqo-fashionsiglip` | `Marqo/marqo-fashionSigLIP` | OpenCLIP from a pinned local snapshot | `c56244cc94f92419e8369fa71efdaf403b124ce8` |
| `zooclaw-fashionsiglip2` | `srpone/zooclaw-fashionsiglip2` | Standard Transformers/SigLIP model | **Unpinned; excluded from first run** |

Each model is downloaded at a full 40-character commit SHA. The baseline SHA is frozen to the exact revision in Cirvanna's current Vision Intelligence implementation. The two Marqo revisions above are defaults in the model registry and were verified against revision-qualified Hub repository/file paths. ZooClaw requires an explicit, independently verified full SHA before it may be added. A moving `main` reference and short SHA are rejected.

Marqo's model cards recommend OpenCLIP and their example Transformers loaders require `trust_remote_code=True`. The runner instead uses OpenCLIP's `local-dir:` loader with the pinned snapshot and does not execute remote model-repository Python. For FashionSigLIP, whose OpenCLIP config points to an external tokenizer repository, the runner redirects the tokenizer to the tokenizer files inside that same pinned model snapshot. It does not download an unpinned tokenizer from a second repository. ZooClaw and the baseline are also loaded with `trust_remote_code=False`.

The Hub snapshot download uses an explicit file allow-list for each model, avoiding duplicate PyTorch/Transformers/OpenCLIP copies of the same large checkpoint. The allow-list includes the model weight, model configuration, processor/tokenizer assets and README/licence notices where present.

Every downloaded snapshot file is SHA-256 hashed. The private run manifest records all model revisions, file sizes/hashes, runtime package versions, device, input JSONL digest, query/task counts, and per-query source-image SHA-256 digests (no image bytes or absolute paths). It also records model download/hash/load time, candidate-text encoding time, query-to-top-k P50/P95 and CUDA peak allocated/reserved memory where available.

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

For the separate `image_to_catalog_image` task, omit `candidate_texts` and provide one rights-cleared relative image path per candidate:

    {
      "schema_version": "1.0",
      "query_id": "clickit-image-query-000001",
      "cluster_id": "catalog-source-cluster-01",
      "task_id": "image_to_catalog_image",
      "split": "test",
      "query_image_path": "queries/query-000001.jpg",
      "candidate_ids": ["variant-a", "variant-b"],
      "candidate_image_paths": {
        "variant-a": "catalog/variant-a-front.jpg",
        "variant-b": "catalog/variant-b-front.jpg"
      },
      "qrels": {"variant-a": 4, "variant-b": 0},
      "excluded_product_ids": [],
      "subgroups": {"source_type": "studio", "query_type": "image"}
    }

All candidate image paths are resolved under `--media-root`; path traversal, missing files and symlink escapes are rejected. Keep query/candidate images and the approved data-rights evidence in the restricted evaluation workspace. The evaluator receives opaque candidate IDs and qrels, not image paths.

Candidate text must come from the same frozen Catalog/Commerce snapshot. For parity with current code, its content should match the Vision service's `_offer_description()` and be truncated to 1,000 characters before tokenization. The text query path uses the same prefix as the current production-intended description-search route.

The input contract requires the same candidate IDs and qrels for every model. Preserve the frozen Commerce offer order in each `candidate_ids` array; the production ranker uses a stable score-only sort, so the runner preserves that order for exact-score ties. Use human-reviewed graded labels; do not describe LLM-generated labels as human ground truth. Split and deduplicate by product/source/near-duplicate clusters before the run. Do not tune on final-test qrels.

Image paths must be relative to `--media-root` and remain inside that directory. The runner rejects path traversal. Query images and (for `image_to_catalog_image`) candidate catalogue images are read locally and are not written into the ranking output, manifest, or GitHub. Their SHA-256 digests and byte sizes are recorded in the private run manifest for reproducibility.

## Install dependencies

Use the committed, hash-locked **CPython 3.11 / Linux x86_64 / CPU-only** research environment for the first controlled pilot. The Marqo adapters require `open_clip_torch==4.2.2`, which supports the `local-dir:` loader used to load pinned snapshots without remote code. That OpenCLIP release requires PyTorch 2.6 or newer; the research environment is deliberately separate from the Vision service's production requirements. The runner fails fast if a different OpenCLIP version is installed. The runtime also needs Transformers, Hugging Face Hub, Safetensors, Pillow, NumPy, timm, setuptools and OpenCLIP's tokenizer dependencies.

Install the exact locked environment on the supported target:

    python3.11 -m venv .venv
    . .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install --require-hashes --only-binary=:all: -r tools/model_evaluation/fashion_retrieval/requirements-research-py311-linux-x86_64-cpu.lock
    python -m pip check

The lock pins every direct and transitive dependency and includes SHA-256 hashes. It uses the official PyTorch CPU wheel index and PyPI. It is intentionally CPU-only: it does not validate GPU kernels, CUDA driver compatibility, VRAM capacity, or GPU throughput. Do not use its latency results as production GPU evidence. A separate CUDA-specific lock must be generated and validated against the approved GPU image, driver, CUDA runtime and target architecture before GPU benchmarking.

The source ranges remain in `requirements-research.txt`. The target-specific constraints are in `requirements-research-py311-linux-x86_64-cpu.constraints.txt`. To regenerate the committed lock, use uv 0.13.9 and this exact command:

    uv pip compile tools/model_evaluation/fashion_retrieval/requirements-research.txt --constraint tools/model_evaluation/fashion-retrieval/requirements-research-py311-linux-x86_64-cpu.constraints.txt --python-version 3.11 --python-platform x86_64-manylinux_2_28 --generate-hashes --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple --index-strategy unsafe-best-match --emit-index-url -o tools/model_evaluation/fashion_retrieval/requirements-research-py311-linux-x86_64-cpu.lock

Record the lock's SHA-256 digest in the private experiment preregistration and data manifest. CI installs the hash-locked CPU environment, runs `pip check`, and imports the pinned model-runtime packages; it does not download model weights or run inference.

## Lock the final-test preregistration

Before opening final-test qrels or generating final rankings, complete a private copy of `preregistration.template.json`. The template is intentionally invalid until the owner/research lead replaces every placeholder and approves the minimum practical effect and sample/cluster requirements.

Validate it with:

    python tools/model_evaluation/fashion_retrieval/validate_preregistration.py \\
      --input /secure/evaluation/final-preregistration.json

The validator requires:
- `nDCG@10` as the fixed primary metric and `k=10`;
- a predeclared minimum practically important paired delta;
- minimum query and independent-cluster counts;
- fixed candidate-pool sizes including the current 1,000-offer Vision ceiling;
- a fixed bootstrap count and seed;
- immutable baseline/challenger revisions; and
- SHA-256 digests for the data, qrels, complete dependency lock and approved data-rights manifest.

The sample values in unit tests are synthetic examples only, not recommended power calculations or a Cirvanna success threshold. Set the effect threshold and minimum sample/cluster counts from the intended product decision, reviewer capacity and a documented power/precision analysis before final-test unblinding. If the final dataset cannot meet the declared minimums, report the study as underpowered; do not silently lower the gates. Keep the completed registration and its source manifests in the restricted evaluation workspace, not GitHub.

## Data-rights approval gate (mandatory)

Before any catalogue snapshot export, human-qrels aggregation, case preparation or model inference, create a private `data-rights` manifest from `data-rights.template.json` and retain the referenced approval evidence in the restricted evaluation workspace. All four stages require the same canonical validator and bind its manifest/evidence digests into their private output manifests. Replace every placeholder only after review; the template is intentionally invalid and must never be treated as approval. The manifest must record `approval_status=approved`, `scope=fashion_retrieval_evaluation`, reviewer identity/role and timestamp, source provenance, evidence path and SHA-256, explicit commercial-evaluation and human-review permissions, a future retention expiry, and whether personal images are present. If personal images are present, depicted-person consent must be recorded as `verified`. Missing, pending, expired, out-of-scope, mismatched or inaccessible evidence blocks inference. The runner requires `--rights-manifest`; it validates this before importing the model runtime or reading query inputs. The rights-manifest digest is written to the private run manifest and must also be locked in final preregistration.

This is an evidence-integrity control, not a legal determination. It does not authenticate signatures, determine copyright or privacy-law compliance, or replace approval by the responsible legal/data-rights owner. Never create an approval record merely to bypass the gate.

## Generate rankings

The baseline alone is not a comparison. Include the baseline and at least one challenger. Example:

    python tools/model_evaluation/fashion_retrieval/run_retrieval.py \
      --input /secure/evaluation/fashion-retrieval-test.jsonl \
      --rights-manifest /secure/evaluation/data-rights.manifest.json \
      --media-root /secure/evaluation/media \
      --output /secure/evaluation/fashion-retrieval-rankings.jsonl \
      --models cirvanna-fashion-clip marqo-fashionclip marqo-fashionsiglip \
      --device auto --batch-size 16

Add --overwrite only when deliberately replacing both rankings and their manifest.

This first run uses the two frozen Marqo revisions from the model registry. Add ZooClaw only after its full commit SHA has been verified, using `--revision zooclaw-fashionsiglip2=<FULL_40_CHAR_COMMIT_SHA>`. Models are loaded sequentially to reduce peak memory. If using CPU, measure runtime and memory; do not treat a CPU smoke run as production throughput evidence.

## Score rankings

Pre-register the primary metric before opening final-test results:

    python tools/model_evaluation/fashion_retrieval/evaluate_retrieval.py \
      --input /secure/evaluation/fashion-retrieval-rankings.jsonl \
      --output /secure/evaluation/fashion-retrieval-report.json \
      --baseline-model-id cirvanna-fashion-clip \
      --split test --k 10 --primary-metric ndcg_at_k \
      --bootstrap-samples 2000 --seed 20261121 \
      --preregistration /secure/evaluation/final-preregistration.json \
      --run-manifest /secure/evaluation/fashion-retrieval-rankings.jsonl.manifest.json

Metrics include Recall@k, Precision@k, MRR@k, nDCG@k, top-1 hit rate, no-result rate, top-k fill, candidate coverage and hard-exclusion violations. Reports include paired challenger-minus-baseline deltas, 95% cluster-bootstrap intervals and subgroup slices. Fewer than two independent clusters yields no confidence interval rather than a degenerate interval.

For final-test runs, the evaluator also requires `--run-manifest`. The locked registration must include private paths and SHA-256 digests for the prepared-data manifest, human-qrels manifest and complete dependency lock. The evaluator verifies those file digests, verifies that the runner consumed the exact prepared JSONL recorded by the data manifest, verifies the ranking-output digest, and checks every baseline/challenger revision against the pinned model commits before scoring. Keep all paths and artifacts in the restricted evaluation workspace.

A challenger passes the preregistered selection gate only if its nDCG@10 paired point improvement is at least the declared minimum practically important delta, the 95% paired cluster-bootstrap interval's lower bound is above zero, and the hard-exclusion gate has zero violations. Passing this retrieval gate is necessary, not sufficient, for production adoption; latency, cost, safety, privacy, rights and end-to-end CAL checks remain separate release gates.

The evaluator refuses final `--split test` scoring unless `--preregistration` is supplied. It checks the locked metric, k, bootstrap settings, task, baseline/challenger model set, minimum query/cluster counts and candidate-pool sizes before computing final-test metrics. Use a non-final split such as `pilot` for diagnostic runs without a final preregistration. The runner ranks the full supplied candidate pool and applies no calibrated no-match threshold. Therefore its no-result rate is not a meaningful quality signal in this initial version. Similarity outputs are ranking scores, never probabilities or calibrated confidence.

## Private artifact handling

The runner, qrels builder, and case-preparation tool write rankings, prepared
cases, qrels, and manifests through the shared private-artifact writer. Writes
are staged in the destination directory, flushed, and atomically published.
On POSIX, files are created with mode 0600; newly created output directories
are restricted to 0700. An existing destination directory with group/other
permissions is rejected rather than silently writing private data into it.

Existing output or manifest files are never replaced by default. Pass
--overwrite to each of the three commands only when replacement is intended;
each file replacement is atomic, but the output/manifest pair is not a single
transaction. The tools preflight both names before starting, then publish each
file separately. Choose a dedicated encrypted,
restricted evaluation directory, not a shared directory such as /tmp.
On Windows and other non-POSIX platforms, Python chmod does not establish an
equivalent ACL guarantee: the writer emits a warning, and operators must use a
workspace whose OS ACLs restrict access to the intended account. Do not
generate real human qrels or private catalogue snapshots until those ACLs have
been verified.

## Tests

    python -m unittest discover -s tests/model_evaluation -v

Tests cover the schema, fixed candidate metadata, strict revision pins, deterministic ranking, invalid vectors and media path traversal. CI compiles the runners and runs these offline unit tests; CI does not download model weights or claim model inference executed.

## Create qrels from blinded human reviews

Do not hand-author incomplete qrels. Create a private query-case JSONL with the full fixed candidate IDs for each query. For each query-candidate pair, collect exactly two independent blinded review records:

    {"query_id":"query-000001","candidate_id":"variant-a","reviewer_key":"reviewer-a","relevance":4,"exclusion_violation":false}

The relevance grade is 0–4. The separate exclusion flag is boolean. Every candidate must be reviewed, including candidates reviewers consider non-relevant. When either relevance or the exclusion flag differs between the two reviewers, provide an independent adjudication:

    {"query_id":"query-000001","candidate_id":"variant-a","adjudicator_key":"adjudicator-c","relevance":3,"exclusion_violation":false}

Run the aggregator:

    python tools/model_evaluation/fashion_retrieval/build_qrels.py \
      --queries /secure/evaluation/query-cases.jsonl \
      --reviews /secure/evaluation/blinded-reviews.jsonl \
      --adjudications /secure/evaluation/adjudications.jsonl \
      --rights-manifest /secure/evaluation/data-rights.manifest.json \
      --output /secure/evaluation/reviewed-query-cases.jsonl

Add --overwrite only when deliberately replacing both the output and its manifest.

Omit `--adjudications` only when no candidate pair has reviewer disagreement. The script validates the approved rights manifest before reading annotation files, then rejects missing/duplicate reviewers, missing candidate reviews, unresolved disagreements, and adjudicators who are not independent of both reviewers. Its output manifest carries the rights and evidence digests but never reviewer IDs or evidence paths. It writes complete qrels and the adjudicated `human_exclusion_violation_ids`, but not reviewer keys or raw reviewer records. Keep source reviews, adjudications, output, and manifests encrypted and restricted; they must never be committed to GitHub.

Then join those qrels to the exact frozen eligible Commerce/Catalog offer text with `prepare_cases.py` as described below. Human violation IDs remain a hard evaluation gate even when no user exclusion ID was supplied.

## Export the exact active Vision catalogue text

The first parity track needs a frozen candidate snapshot of the exact offer text the current Vision service ranks. Do not reconstruct `_offer_description()` in a separate script. The service now contains a restricted CLI that invokes its own `_live_offers()` implementation and writes only `variant_id` plus the exact `search_text` value.

Run this from an **isolated full Cirvanna source checkout**, with the Vision service's trusted read-only Commerce/Catalog environment explicitly supplied to the isolated process. Do not run it in a public deployment or against a production environment. The canonical rights validator is loaded from the checkout; a stripped service image without the repository tooling fails closed. Mount a restricted evaluation volume and use an unused destination:

    cd services/vision-intelligence
    python -m app.retrieval_snapshot_export \
      --rights-manifest /restricted-evaluation/data-rights.manifest.json \
      --output /restricted-evaluation/catalog-offers.jsonl

It validates the approved rights manifest before importing the Vision service or making Commerce/Catalog calls. It emits a sibling `.manifest.json` and records the snapshot SHA-256, model pin, candidate count, whether the service's 1,000-offer ceiling truncated the Commerce offer list, the rights-manifest/evidence digests, and that this was a sequential point-in-time Commerce/Catalog read (not a cross-service transaction). Both files are created with mode `0600` inside a directory restricted to the owner on POSIX. Existing files are never overwritten; choose a new versioned output path for each snapshot.

The exporter excludes product image URLs, raw Commerce/Catalog payloads, names as separate fields, service URLs, and credentials. It preserves the Commerce offer order and refuses duplicate/invalid variant IDs. The text is commercial catalogue information, so the resulting file and manifest must remain in the restricted evaluation workspace and must not be committed, attached to the PR, or sent to unapproved model endpoints.

## Prepare matched input from frozen snapshots

The runner input is assembled from two private JSONL files. The first is a fixed, eligible Commerce/Catalog snapshot captured from the same release of the service, after the existing active-product / purchasable-offer rules have been applied. Each row must contain:

    {"variant_id":"variant-a","search_text":"Fashion or beauty marketplace product. ...exact _offer_description() output..."}

The `search_text` must be the exact output of the Vision service's `_offer_description(offer, product)`. Do not rebuild it with a different template. The runner/evaluator use the variant ID because the production `_rank_offers()` keys results by `variant_id`.


The qrels builder output (`reviewed-query-cases.jsonl`) is the second input. It contains one record per query with query metadata, candidate variant IDs, human-reviewed qrels, any declared excluded variant IDs, and task-grounded subgroup values. Its sidecar manifest is mandatory and must match the approved rights digest:

    {"schema_version":"1.0","query_id":"query-000001","cluster_id":"source-cluster-001","task_id":"image_to_catalog_text","split":"test","query_image_path":"queries/query-000001.jpg","candidate_ids":["variant-a","variant-b"],"qrels":{"variant-a":4,"variant-b":0},"excluded_product_ids":[],"subgroups":{"source_type":"studio"}}

For text queries use `task_id=text_to_catalog_text` and provide `query_text`. The script validates the approved rights manifest and both source sidecars before reading either input. It verifies snapshot and qrels digests, matching rights-manifest digests, snapshot row count, and every candidate against the frozen snapshot; it rejects duplicate IDs, empty/invalid qrels, unsupported tasks and missing query data, then writes runner input plus a digest manifest bound to both source manifests and the rights approval:

    python tools/model_evaluation/fashion_retrieval/prepare_cases.py \
      --catalog-snapshot /secure/evaluation/catalog-offers.jsonl \
      --queries /secure/evaluation/reviewed-query-cases.jsonl \
      --rights-manifest /secure/evaluation/data-rights.manifest.json \
      --output /secure/evaluation/fashion-retrieval-test.jsonl

Add --overwrite only when deliberately replacing both the output and its manifest.

The 1,000 candidate bound matches the current Vision worker cap. Prepare one task and one split per run. Use exact eligible variant IDs, not product names or generated row numbers. The source snapshot, query/review/adjudication inputs, prepared JSONL and manifests are private research records and must remain outside GitHub. Every candidate must have a complete grade; no unjudged candidate is silently treated as irrelevant. Human-adjudicated constraint violations remain hard ranking gates.

## End-to-end local tests

    python -m unittest discover -s tests/model_evaluation -v
