# Human-reviewed outfit recommendation evaluation

**Status:** evaluation harness and protocol are in source. No human-reviewed dataset has been collected or scored; no performance claim is supported yet.

## Compare

Compare the candidate ranker with a simple, transparent baseline on the same frozen candidate pool:
- Relevance: mean blinded human rating (1–5) among top-k (default k=3).
- Diversity: mean pairwise Jaccard distance between item-ID sets among top-k; higher means less repetition.
- Exclusion violations: share of top-k outfits containing a declared excluded tag. This is a hard release gate, not a trade-off.
- User edits: share of shown recommendations edited before acceptance/save.
- Repeated rejection: share of rejected impressions belonging to a repeated pseudonymous (user, outfit-signature) pair.

Baseline: first rank outfits with no declared exclusion violation, then explicit preferred-tag overlap, category coverage, and bounded outfit completeness. The model uses its stored ranking score. Both rank the same pool.

## Human annotation and privacy

- Approved research protocol and explicit participant consent; adults only for this study. No child photos, face crops, face embeddings, biometric data, or raw images.
- No names, email, phone, precise location, or raw account IDs. Use access-controlled keyed pseudonyms for participants and reviewers; keep re-identification keys separate.
- Store only minimum metadata: opaque item IDs, categories, declared tags/preferences/exclusions, model scores, human ratings, and actual impression outcomes.
- Freeze candidate pool, ranker/baseline/policy versions and dataset snapshot before evaluation. Split by participant, not outfit row, to prevent wardrobe leakage.
- At least two independent blinded reviewers per candidate. Randomize candidate order and hide method identity. Adjudicate disagreements and retain reviewer-level provenance.
- Judge against declared occasion, wardrobe context, explicit preferences and constraints. Reviewers must not infer sensitive traits from appearance.
- User edits/rejections are observed behavioural events, not human relevance labels. Do not pretend offline ratings predict baseline user behaviour; a causal comparison requires a randomized live baseline arm.
- Never fabricate user outcomes or human labels. Synthetic fixtures are test-only.

## JSONL schema

One case per line: schema_version=1.0, case_id, pseudonymous user_key, reviewer_key, ISO-8601 reviewed_at, split (train/validation/test), preferred_tags, excluded_tags, candidate_pool.

Each candidate: candidate_id, item_ids, categories, tags, finite model_score, human_relevance integer 1–5, and observed booleans shown/user_edited/user_rejected. Outcome flags must be supported by impression logs. A rejection requires a stable pseudonymous rejection_key.

## Run

From services/recommendation-service:
```bash
python -m pytest -q
python -m app.outfit_evaluation path/to/human-reviewed-outfits.jsonl --k 3 --output outfit-evaluation-report.json
```

Use the locked test split for final comparison. Train/validation are diagnostic. Report sample counts, annotation agreement, version identifiers, dataset snapshot hash and confidence intervals. The harness reports descriptive point estimates only; it does not calculate confidence intervals or significance. Pre-register power analysis and bootstrap intervals before using small deltas for launch decisions.

## Release gates

- Zero confirmed hard-exclusion violations on locked test; any violation blocks release and triggers root-cause correction.
- Improve relevance without material diversity regression; pre-register the non-inferiority margin.
- High edit/repeated-rejection rates signal missed intent or repetitive looks; segment only on declared, non-sensitive context.
- If held-out relevance does not beat the baseline, do not claim the model is more intelligent.
- No scores are available until humans annotate and adjudicate a real dataset.
