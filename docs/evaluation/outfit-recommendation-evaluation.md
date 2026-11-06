# Human-reviewed outfit recommendation evaluation

**Status: harness and protocol only. No human-labelled dataset has been supplied or scored.** Do not report relevance, diversity, or adoption metrics until annotation is complete.

## Metrics and comparison

Compare the daily-look ranker with a transparent rule-based baseline on the exact same candidate pool.

1. Outfit relevance: mean blinded human rating (1–5) among the top three.
2. Diversity: mean pairwise Jaccard distance between item-ID sets among the top three; higher means less repetition.
3. Exclusion violations: share of top-three looks containing any declared excluded tag; lower is better. This is a hard-safety metric, not a trade-off against relevance.
4. User edits: share of actually shown recommendations edited before acceptance/save.
5. Repeated rejection: share of rejected impressions belonging to a repeated (pseudonymous user, stable outfit-signature) pair.

The simple baseline first prioritizes candidates that do not violate declared exclusions, then ranks by overlap with explicit preference tags, category coverage and outfit completeness. The model ranks by its recorded score. Both use the same candidates and human labels.

## Runtime integration status

The active recommendation service in this repository currently implements Complementer advisory composition; it does not expose a daily three-look candidate generator/ranker. The harness is therefore a validated evaluation contract, not yet wired to a live daily-look runtime. There is also a naming/ownership conflict to resolve before integration: ADR-0005 says Xari is the single canonical assistant and Tari is a legacy compatibility name, while issue #108 describes Tari as the daily-look capability under Xari. Keep Xari as the only assistant; confirm whether "Tari" is intended only as a capability label. Before collecting labels or claiming a model-vs-baseline result, identify the authoritative active candidate generator, version its scores and candidate pool, and connect its real outputs to this schema. Do not promote recovered or staged source candidates into production merely to satisfy the evaluator.

## Dataset privacy and annotation

- Use an approved research protocol and explicit participant consent. Use consenting adults only; no child images or biometric data.
- Do not store photographs, face crops, face embeddings, names, emails, phone numbers, precise location or raw account IDs.
- Use keyed, access-controlled pseudonyms for participant and reviewer identifiers. Keep re-identification keys outside the evaluation store.
- Store only minimum outfit metadata: opaque item IDs, categories, declared style/colour/material tags, declared preferences/exclusions, scores, ratings and explicit interaction outcomes.
- Freeze candidate pool, algorithm version, baseline version, policy version and dataset snapshot before scoring.
- Split by participant, not outfit row, to prevent one person's wardrobe/preferences leaking across train, validation and test. The harness rejects a pseudonymous participant appearing in more than one split.
- Use at least two independent, blinded reviewers per candidate. Randomize candidate order and hide method identity. The JSONL schema records distinct reviewer keys and individual 1–5 ratings, plus an adjudicated human_relevance score. Adjudicate material disagreements and retain reviewer-level provenance.
- Rate relevance against declared occasion, preferences, wardrobe context and constraints, not reviewer taste alone.
- A confirmed exclusion violation remains a violation even if the outfit is attractive.
- User edits and rejections are behavioural observations, not human relevance labels. Do not infer baseline behaviour from offline ratings; use a randomized live baseline arm for causal behavioural comparison.

## JSONL contract

One JSON object per line. Required case fields: schema_version=1.0, case_id, pseudonymous user_key, ISO-8601 reviewed_at, algorithm_version, baseline_version, policy_version, split (train/validation/test), preferred_tags, excluded_tags, and candidate_pool.

Each candidate requires candidate_id, item_ids, categories, tags, finite model_score, adjudicated human_relevance (integer 1–5), at least two human_ratings entries with distinct pseudonymous reviewer_key values and relevance scores (1–5), and observed flags shown/user_edited/user_rejected. Set outcome flags only when supported by actual impression events. A rejected impression requires a stable pseudonymous rejection_key.

Do not add synthetic labels to the research dataset. Unit-test fixtures are arithmetic checks only and are not evaluation evidence.

## Run

From services/recommendation-service:

```bash
python -m pytest -q
python -m app.outfit_evaluation path/to/human-reviewed-outfits.jsonl --k 3 --output outfit-evaluation-report.json
```

Use the locked test split for final comparison. Train/validation are diagnostic only. Report sample counts, annotation agreement, algorithm/baseline versions, confidence intervals and dataset snapshot hash. The harness currently reports descriptive point estimates only; it does not calculate confidence intervals or statistical significance. Pre-register a power analysis and bootstrap confidence intervals before using small deltas as a launch decision.

## Release gates

- Zero confirmed hard-exclusion violations on the locked test set; any violation blocks release pending root-cause correction.
- Improve relevance without materially reducing diversity versus baseline. Set the non-inferiority margin before viewing locked-test results.
- High edit or repeated-rejection rates indicate missed intent or repetitive recommendations; segment only by declared, non-sensitive context.
- If the ranker does not beat baseline on held-out human relevance, do not claim it is more intelligent.
- No scores are currently available. The human-reviewed dataset must be collected and adjudicated first.
