# Outfit evaluation: human-reviewed benchmark and baseline

## Purpose

This benchmark measures whether Cirvanna's outfit-ranking system produces looks that people find relevant, varied, and safe against their explicit exclusions. It compares Cirvanna with a transparent rule-based baseline over the same candidate pool. It is an evaluation protocol, not evidence that the recommender is already validated.

**There are no human-labelled results in this repository.** Do not create synthetic labels or describe the algorithm as outperforming a baseline until the restricted dataset has been reviewed and the evaluator has run.

## Dataset boundary

Use the versioned contract at data/evaluation/outfit-review.schema.json and the evaluator at scripts/evaluation/evaluate_outfits.py.

One case represents one participant/session context and contains:
- user-declared occasion, style/color preferences, required categories and explicit hard exclusions;
- the candidate outfit pool before ranking;
- Cirvanna's ordered look IDs;
- two independent human reviews for every candidate;
- actual user exposures and outcomes from the randomly assigned experiment arm.

The dataset must not contain photographs, face data, names, email addresses, account IDs, inferred age/skin tone/ethnicity/religion/body traits, or free-form personal notes. Use random study keys and opaque wardrobe/look IDs. Keep the participant-key mapping separately in a restricted system. Do not commit identifiable or raw participant-level observations to this repository; store the reviewed JSONL export in an encrypted, access-controlled evaluation workspace and run the tool there.

Capture only the context needed to evaluate the user-declared constraints. A missing or unknown field is not permission to infer it.

## Human review protocol

1. Freeze the candidate pool, wardrobe snapshot and preference/context version for each case.
2. Generate Cirvanna's ranked list and the baseline ranking from the same candidate pool.
3. Randomize candidate presentation order for reviewers. Hide system name, algorithm score and rank. Use exactly two independent reviewers per candidate. Duplicate reviews from one reviewer are rejected.
4. Review each look against the declared occasion/context and wardrobe coherence. Rate relevance from 1 (not relevant) to 5 (highly relevant). Separately flag any violation of an explicit hard exclusion.
5. Require an independent adjudicator whenever reviewers disagree on either label. Never resolve a hard-exclusion disagreement by averaging it away.
6. Randomly assign each participant to one live arm (Cirvanna or baseline) for the study period. Persist that assignment for the participant to prevent cross-arm contamination. Record actual impressions, edits and rejections only for the arm they saw.
7. Keep candidate generation, wardrobe snapshot, algorithm version, baseline version and annotation rubric version in the controlled study manifest so results are reproducible.

Reviewers must not assess attractiveness, identity conformity, body shape, skin tone, religion or cultural identity. Cultural requirements are evaluated only when users explicitly declared them and the requirement is represented as an auditable product/look attribute.

## Baseline

The evaluator's intentionally simple baseline:
- hard-filters candidate outfits containing a declared excluded garment ID or exclusion tag;
- scores required-category coverage (weight 3.0);
- scores an exact declared-occasion match (weight 2.0);
- adds Jaccard overlap with declared style tags (weight 1.0);
- adds half-weight Jaccard overlap with declared color tags (weight 0.5);
- uses stable look ID as a deterministic tie-break.

It does not use learned user history, embeddings, popularity, demographic proxies or opaque model scores. Its weights are a fixed control, not tuned on the evaluation labels.

## Metrics

For both systems, using the top k looks (default 3):
- **Human relevance:** mean adjudicated 1–5 score and nDCG@k.
- **Diversity:** mean pairwise Jaccard distance across garment, category, style and color feature sets in the top-k slate.
- **Exclusion violations:** fraction of returned top-k looks flagged by human adjudication or found to contain an explicitly excluded item/tag. Target is zero; average relevance must never compensate for a violation.
- **No-result rate / top-k fill:** report how often a system returns no eligible look and how many of the requested top-k slots it fills. An empty slate is not counted as a zero-violation success.

For the randomly assigned live arm only:
- **User edits:** edited-look rate and mean edit count per exposed look.
- **Rejection:** rejected impressions divided by observed exposures.
- **Repeated rejection:** proportion of rejected participant/look signatures rejected in at least two distinct sessions. Look signatures are SHA-256 hashes of sorted opaque garment IDs; raw user identity is never part of the key.

The evaluator also enforces one randomized system arm per participant across all sessions and one exposure outcome per look per session. It reports descriptive metrics, no-result rate, top-k fill and Cirvanna-minus-baseline deltas. It calculates percentile-bootstrap 95% confidence intervals by resampling participant clusters (2,000 resamples, fixed seed), including paired Cirvanna-minus-baseline intervals. It also reports exact reviewer agreement and Cohen's kappa within stable pseudonymous reviewer pairs (quadratic-weighted for relevance, nominal for hard exclusions). These are descriptive intervals and agreement summaries, not a substitute for a pre-registered statistical analysis. Before launch decisions, pre-register sample size and analysis plan, inspect subgroup errors, and report results stratified by declared occasion/climate and other non-sensitive context where sample sizes permit. Do not average away hard-exclusion failures.

## How to run

From a restricted evaluation workspace with the approved JSONL export:

    python scripts/evaluation/evaluate_outfits.py --input /secure/evaluation/outfit-review.jsonl --output /secure/evaluation/outfit-report.json --k 3

The command rejects cases without exactly two distinct independent reviews per candidate, unresolved reviewer disagreements, duplicate per-look exposure outcomes, invalid references, or exposure events outside the assigned arm's top-k. An empty dataset reports insufficient_human_reviewed_data; it does not produce a performance claim.

Run contract tests locally with:

    python -m unittest discover -s scripts/evaluation -p 'test_*.py' -v

## Release gate

Do not promote outfit ranking based on model-only metrics or synthetic data. Require:
- human-reviewed, blinded candidate labels and documented reviewer agreement;
- identical candidate-pool comparisons with the fixed baseline;
- zero hard-exclusion violations in the release evaluation;
- acceptable relevance and diversity with confidence intervals;
- observed edit and repeated-rejection rates from a randomized live arm;
- reproducible dataset, algorithm, baseline and annotation versions;
- separate privacy review for the dataset and its retention/deletion policy.

A failing exclusion gate blocks promotion even when relevance or engagement improves.
