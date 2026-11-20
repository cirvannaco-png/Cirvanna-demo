# Cirvanna AI model competition and logic-transfer programme

- **Status:** Governing research and engineering protocol
- **Established:** 2026-11-20
- **Scope:** Every model-backed or learned capability in Cirvanna
- **Decision rule:** Compare first; understand the source of any advantage; independently implement the useful principle; prove the Cirvanna implementation beats its own frozen baseline before integration.

## 1. Purpose

Cirvanna will not select models because they are newer, larger, popular, highly rated on a public leaderboard, or accompanied by attractive model-card claims.

The programme exists to build durable Cirvanna-owned intelligence. External models are challengers and research instruments. Their results may reveal a stronger representation, training objective, data strategy, ranking method, preprocessing approach, calibration technique, or inference architecture. Cirvanna should extract and independently implement the useful principle—not copy source code, weights, proprietary datasets, or restricted assets.

This programme creates two separate proof obligations:

1. **External challenge:** establish whether a challenger actually outperforms the current Cirvanna implementation on the same task and evidence.
2. **Logic transfer:** establish whether a clean, Cirvanna-owned implementation of the identified principle outperforms Cirvanna's own frozen baseline.

A challenger winning the first comparison does not automatically pass the second. A public benchmark win does not establish product suitability, legal clearance, safety, or production readiness.

## 2. Non-negotiable principles

1. **Cirvanna is the baseline.** Freeze the current production-intended implementation before changing it. Record its source commit, model identifier and immutable revision, artifact hashes, preprocessing, dependencies, configuration, retrieval/ranking logic, and runtime.
2. **The task must be identical.** Baseline and challenger receive the same eligible inputs, query cases, candidate universe, relevance labels, policy constraints, and evaluation split. Differences required by the model's documented processor must be recorded rather than hidden.
3. **No leaderboard substitution.** A model-card score, paper result, vendor demonstration, hosted API claim, or a result on a different dataset is a research lead—not Cirvanna evidence.
4. **No leakage.** Keep training, tuning, validation, and final test data separate. Prevent product, SKU, image, outfit, brand, user, and near-duplicate leakage across splits where relevant.
5. **No score laundering.** Cosine similarity, logits, distance, or ranking scores are not probabilities or confidence unless calibrated and independently validated for the exact task and population.
6. **Hard controls are not tradeable.** NPL exclusions, consent, ownership, privacy, child-safety, CAL display authorization, legal restrictions, and other safety invariants cannot be offset by better relevance or engagement.
7. **Clean-room transfer.** Read public papers and model cards to identify methods. Write a Cirvanna-owned technical hypothesis and implementation from first principles. Do not transplant third-party source files, weights, training data, or restricted prompt/code assets.
8. **Evidence before integration.** No candidate replaces a baseline and no transferred method is promoted merely because an offline metric improves. Product-flow, subgroup, cost, security, privacy, and operational tests still apply.
9. **Reproducibility is mandatory.** Every reported result must identify exact data, code, model, dependencies, seeds, hardware, run configuration, and evaluator versions.
10. **Unknown means unknown.** Missing provenance, rights, ground truth, deployment evidence, subgroup coverage, or test results are marked `REVIEW_REQUIRED` or `BLOCKED`, never assumed to pass.

## 3. Standard research lifecycle

### Stage 0 — Capability and baseline inventory

For the capability being studied, document:

- user problem and exact task definition;
- current route/service, canonical owner, consumers, and downstream policy gates;
- current model or deterministic baseline, including immutable pins;
- the actual input and output contract;
- current preprocessing, candidate construction, score interpretation, thresholds, caching, failure modes, and fallback behavior;
- proven behavior versus mocked, partially implemented, or disabled behavior;
- latency, memory, throughput, availability, and deployment constraints;
- existing tests, human evaluation, safety controls, and release blockers.

Do not describe a model as the complete capability. For example, a pose skeleton is not a persistent full-body Twin, and a garment image renderer is not proof of calibrated fit.

### Stage 1 — Challenger discovery and due diligence

For each candidate, record:

- exact repository/model/API identity and immutable revision;
- architecture, processor, input/output contract, modalities, dimensions, parameter count, and runtime requirements where verifiable;
- model-weight licence and any separate code licence;
- base-model licence, tokenizer/processor licence, parser/detector dependencies, custom code, and all transitive dependencies;
- training-data source, collection method, consent/rights/provenance evidence, demographic or geographic coverage, and known contamination;
- evaluation dataset licence and underlying image/text rights;
- restrictions on commercial use, hosted inference, redistribution, derivative works, training, retention, and attribution;
- published claims, their original test protocol, independent reproduction status, and known limitations.

A model card's licence field is not a complete rights opinion. Model weights, source code, training data, evaluation data, image content, and dependencies have separate rights. Any unresolved commercial restriction blocks commercial training, deployment, or customer-facing inference as applicable.

### Stage 2 — Matched external benchmark

Run the current Cirvanna baseline and challengers against the same frozen benchmark.

The protocol must pre-register:

- task, primary metric, secondary metrics, hard safety gates, practical improvement threshold, sample-size rationale, and analysis method;
- exact model/data/runtime revisions and hashes;
- query and candidate construction;
- preprocessing and model-specific processor handling;
- candidate universe and catalogue snapshot;
- relevance rubric and human-review procedure;
- split strategy, deduplication rules, exclusions, and subgroup slices;
- hardware, concurrency, warm/cold conditions, resource ceilings, and cost accounting.

A challenger is a winner only within the defined task and test scope. Report uncertainty, failure cases, coverage, and resource cost—not just one aggregate score.

### Stage 3 — Explain the advantage

Do not stop at "model B scored higher." Determine why.

Use controlled diagnostics and ablations to distinguish, where applicable:

- training objective and negative-sampling strategy;
- multi-attribute supervision and attribute completeness;
- hard-negative mining and false-negative handling;
- data quality, source diversity, temporal freshness, and domain coverage;
- image/text resolution, tokenization, crop policy, and text truncation;
- representation dimensionality and normalization;
- candidate generation, retrieval depth, hybrid search, and reranking;
- personalization/context integration and constraint enforcement;
- calibration, abstention, confidence margins, and no-result behavior;
- latency, caching, batching, quantization, and deployment architecture.

Separate evidence from interpretation. A model card may suggest a mechanism; only a controlled ablation can attribute a measured gain to that mechanism.

### Stage 4 — Clean-room logic transfer

For each useful mechanism, create a short engineering proposal with:

- the observed failure of Cirvanna's baseline;
- the public technical principle and source references;
- the exact hypothesis for why the principle should help Cirvanna;
- the independently designed Cirvanna implementation;
- data and legal basis required for implementation;
- isolated ablation plan;
- expected benefit, risk, complexity, and resource cost;
- rollback path.

Keep the original model and policy path intact. Implement one material change at a time. Where a method needs learning, train or tune only with data and base components cleared for Cirvanna's intended commercial use. Do not import a challenger checkpoint merely because it provided the inspiration.

### Stage 5 — Prove the adapted Cirvanna system

Compare the adapted Cirvanna implementation with the **same frozen Cirvanna baseline**, using the same test cases and policy gates.

A transferred method passes only when:

- the pre-registered primary metric improves by the pre-registered practical margin;
- the confidence interval and statistical analysis support the improvement;
- no hard safety, privacy, consent, ownership, or exclusion gate regresses;
- subgroup results do not conceal a material failure;
- coverage, abstention, and no-result behavior remain acceptable;
- latency, memory, availability, and unit cost fit the declared operating budget;
- integration and regression tests pass.

A method that only improves the external leaderboard but not Cirvanna's task is not transferred. A method that improves relevance while increasing exclusion violations is rejected.

### Stage 6 — Full product-system validation

Validate the whole user journey, not an isolated model endpoint. Exercise upstream data, Identity/consent, Catalog/Commerce, Wardrobe, PNELLY, NPL, FCI where applicable, CAL, private asset handling, audit events, revocation/deletion, operational alerts, and fallback behavior.

The final report must say whether the change is:

- `RESEARCH_ONLY`
- `BENCHMARKED`
- `LOGIC_HYPOTHESIS_SUPPORTED`
- `ADAPTED_NOT_VALIDATED`
- `VALIDATED_FOR_SCOPED_PILOT`
- `PRODUCTION_ELIGIBLE`
- `REJECTED`
- `BLOCKED`

Passing one stage never implies that a later stage passed.

## 4. Evidence and decision record

Each experiment must preserve a versioned manifest and a report containing:

| Evidence | Required content |
|---|---|
| Baseline identity | Repository commit, source path, model ID/revision, artifact digest, config and dependencies |
| Challenger identity | Repository/API, immutable revision, licence/provenance review and artifact digest |
| Dataset identity | Source, version, immutable snapshot, file digests, rights decision, split and exclusions |
| Run identity | Timestamp, runner, hardware, runtime, dependency lock, seed and exact command |
| Quality | Primary/secondary metrics, confidence intervals, error taxonomy, examples reviewed under approved controls |
| Safety | Hard-gate results, subgroup errors, consent/privacy checks and failure/abstention behavior |
| Operations | Cold/warm latency, P50/P95, throughput, memory/VRAM, startup, failures and cost |
| Decision | What is supported, what remains unknown, owner, approval and next gate |

Store private images, human-review records, user-level traces, account mappings, and sensitive raw observations only in an approved restricted evaluation environment. Do not commit them to GitHub. Commit only schemas, non-identifying aggregate reports approved for publication, code, and provenance metadata.

## 5. Cirvanna workstream map

| Workstream | Cirvanna baseline to challenge | External research scope | Non-negotiable boundary |
|---|---|---|---|
| Marketplace visual retrieval | Pinned FashionCLIP image/text embeddings and _rank_offers over live Commerce/Catalog text | Fashion-specific multimodal encoders, multi-attribute contrastive learning, hard-negative and graded-relevance methods | Same task/candidate set; candidate-only output; NPL and CAL remain authoritative |
| PNELLY + Wardrobe | Existing recommendation/composition and learning trace path plus the documented human-reviewed outfit baseline | Context-aware retrieval, preference learning, slate ranking, diversity and feedback learning | Reuse the existing blind human-review protocol; explicit user exclusions remain hard |
| Click It privacy | Pinned MediaPipe BlazeFace detector and fail-closed masking flow | Licensed face-region detectors and segmentation/mask quality methods | Face masking only; no identity, recognition, age estimation or face search; uncertain means reject |
| Look It | Separate PNELLY consent-gated outfit-image route and current retrieval/decomposition path | Multi-item outfit parsing, component retrieval and cross-modal search | Must remain distinct from Click It; user image privacy and consent gates remain separate |
| Virtual Try-On | Existing private FASHN VTON 1.5 worker and its pinned inference contract | Commercially cleared parsers, garment/person conditioning, alignment and rendering methods | Full dependency rights, image quality, identity preservation, consent and GPU validation |
| Virtual Twin | Partial MediaPipe pose skeleton and provider-neutral generation/validation contracts | 3D body/mesh recovery, geometry, rigging and measurement research | Pose is not a mesh; appearance is not measurement; independent geometry/privacy validation required |
| DermalSight | Existing DSI landmarks/segmentation and experimental colour-validation foundations | Task-specific segmentation, calibration, uncertainty and robust visual inference | Non-diagnostic; no unsupported skin-tone, clinical, or demographic claims; calibration is mandatory |

## 6. Existing controls that must be reused

- **Marketplace retrieval:** services/vision-intelligence/README.md and services/vision-intelligence/app/main.py. Treat ranking scores as similarities, not calibrated probabilities. Preserve active Commerce/Catalog sourcing and candidate-only semantics.
- **PNELLY/Wardrobe:** docs/evaluation/outfit-evaluation-protocol.md, its schema, and the existing pseudonymous trace preparation/evaluation tools. The current trace is not a randomized live-arm study and does not contain real human ratings or verified exposure outcomes.
- **Virtual Try-On:** docs/architecture/adr/ADR-0011-vton-model-provenance-and-license-gate.md. The complete model stack, not only the top-level model, must be commercially cleared.
- **Virtual Twin:** docs/research/twin-provider-pilot-scorecard.md, the provider qualification assessment and the generation/validation trust-chain contract. Provider diligence is not approval.
- **Click It / Look It:** the independent privacy verification plan and the Vision service privacy boundary. Do not use user images as benchmark material without the exact consent, masking, access, retention and deletion basis.

## 7. First execution priority

Start with fashion retrieval because it has a pinned, inspectable Cirvanna baseline, an identifiable comparison task, and candidate datasets that can be assessed before touching higher-risk customer-facing capabilities.

The first benchmark is defined in [the fashion-retrieval challenger benchmark](fashion-retrieval-challenger-benchmark.md). The current candidates and unresolved gates are tracked in [the model candidate register](model-candidate-register.md).

**Current experiment status:** research and protocol preparation only. No matched model benchmark, human relevance evaluation, GPU inference test, or logic-transfer result is claimed by this document. A prior attempt to start a Hugging Face CPU job was rejected by the service with HTTP 402 before a job began; no paid compute job was launched. Do not retry paid compute without enabled credits/payment approval. Prepare the runner and manifests, then execute when an approved compute path and rights-cleared data are available.

## 8. Change control

Any change to the baseline model pin, retrieval logic, candidate construction, training data, policy boundary, score interpretation, or evaluation protocol requires a versioned change record and re-running the affected benchmark. A PR must include the experiment report or explicitly state why the work is documentation/research only. No research branch may silently change main or production model configuration.
