# Human-reviewed outfit recommendation evaluation

**Status:** harness and protocol are implemented. No human-reviewed dataset has been collected or scored; no performance claim is supported.

## Metrics and comparison
Compare the daily-look ranker with a transparent baseline on the same frozen candidate pool:
- Relevance: mean of at least two independent blinded human ratings (1–5) per outfit, averaged across top-k (default 3).
- Diversity: mean pairwise Jaccard distance between item-ID sets among top-k; higher means less repetition.
- Exclusion violations: share of top-k outfits containing a declared excluded tag. This is a hard safety metric, not a trade-off.
- User edits: share of actually shown recommendations edited before save/acceptance.
- Repeated rejection: share of rejected impressions in a repeated (pseudonymous user, stable outfit-signature) pair.

Baseline: rank outfits without declared exclusions first, then explicit preferred-tag overlap, category coverage and outfit completeness. The candidate ranker uses its recorded score. Both rank the exact same pool.

## Human review and privacy
1. Recruit consenting adults under an approved research protocol. No child images, biometric data, face crops/embeddings, or raw photos in this dataset.
2. Store only opaque item IDs, categories, declared style/colour/material tags, declared occasion, explicit preferences/exclusions, ranking scores, reviewer ratings and actual interaction events.
3. Never store names, email, phone, precise location or raw account IDs. Use keyed pseudonyms; keep re-identification keys separately access-controlled.
4. Two independent reviewers rate every candidate. Randomize presentation order and hide algorithm identity and score. Preserve reviewer-level ratings and adjudicate material disagreements.
5. Review against declared occasion, wardrobe context, preferences and constraints—not personal taste. Never infer sensitive traits from appearance.
6. Freeze candidate pool and algorithm, baseline and policy versions. Split by participant, not outfit row; the evaluator rejects participant leakage across splits.
7. Capture edits/rejections only from actual consented impressions. Offline ratings are not user behaviour. A causal baseline comparison requires a randomized live baseline arm.
8. Never fabricate human labels or interaction outcomes. Unit-test fixtures are not evaluation evidence.

## JSONL contract
One object per line. Case fields: schema_version=1.0, case_id, pseudonymous user_key, ISO-8601 reviewed_at, split (train/validation/test), preferred_tags, excluded_tags, candidate_pool.

Each candidate requires candidate_id, item_ids, categories, tags, finite model_score, at least two human_reviews objects (unique pseudonymous reviewer_key and integer relevance 1–5), and evidence-backed shown, user_edited, user_rejected flags. A rejection requires a stable pseudonymous rejection_key.

## Run
From services/recommendation-service:
```bash
python -m pytest -q
python -m app.outfit_evaluation path/to/human-reviewed-outfits.jsonl --k 3 --output outfit-evaluation-report.json
```

Use the locked test split for final comparison. Report sample counts, reviewer agreement, algorithm/baseline versions, dataset snapshot hash and confidence intervals. The harness reports descriptive point estimates only; it does not calculate confidence intervals or significance. Pre-register power analysis and bootstrap intervals before interpreting small deltas.

## Release gates
- Zero confirmed hard-exclusion violations on locked test; any violation blocks release and triggers root-cause correction.
- Improve relevance without material diversity regression; pre-register the non-inferiority margin.
- High edit/repeated-rejection rates signal missed intent or repetitive looks; segment only on declared, non-sensitive context.
- If held-out relevance does not beat baseline, do not claim the candidate algorithm is superior.
- No scores exist until real data is collected, independently reviewed and adjudicated.