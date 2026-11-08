# PNELLY human-reviewed outfit evaluation

This is one canonical offline evaluator and trace-preparation path. It is a measurement tool, not a recommendation runtime and not evidence that PNELLY quality has improved.

## Case contract

One JSONL record represents one pseudonymous participant/session and contains:
- the complete, non-truncated candidate outfit pool and declared context;
- the ordered Cirvanna ranking and the deterministic baseline ranking derived from that exact pool;
- exactly two independent blinded human reviews for every candidate;
- a separate independent adjudication when the two reviewers disagree;
- any real user exposure/outcome events from the participant's randomized assigned arm only.

The schema lives at `data/evaluation/outfit-review.schema.json`. The actual reviewed JSONL dataset must remain outside GitHub in an encrypted, access-controlled study workspace. Never put names, account IDs, wardrobe item IDs, photos, URLs, image assets, storage keys, raw location or sensitive inferred traits in the study dataset.

The preparation tool additionally requires a source trace with:
- a validated consent assertion;
- no raw user/account identity or media fields;
- no truncated candidate pool;
- a pseudonymous participant key and stable random arm assignment across sessions.

The joiner verifies that each candidate has two distinct reviewer keys. It cannot authenticate real reviewer identities or prove independence; a study coordinator must verify and document that outside the code.

## Metrics and safety gates

For both systems over the same frozen candidate pool: human relevance, nDCG@k, within-slate diversity, hard-exclusion violation rate, no-result rate and top-k fill rate.

Only for the randomized system arm actually shown to each participant: observed exposures, edits, edit counts, explicit rejection and repeated rejection of the same opaque garment signature in distinct sessions.

The evaluator also reports raw reviewer agreement and kappa within stable pseudonymous reviewer pairs, participant-cluster percentile bootstrap intervals (2,000 resamples) and paired Cirvanna-minus-baseline intervals. **At least two distinct participant clusters are required** to report a sampling-uncertainty interval; with one participant, the interval is null rather than a misleading zero-width range. These intervals are descriptive, not a pre-registered superiority test.

Any hard-exclusion violation is a release-blocking safety failure. It cannot be offset by relevance, engagement, diversity or retention. Empty baseline slates are reported as no-result with zero top-k fill, not as zero violations.

## Run from a restricted study workspace

Prepare cases from a consented, pseudonymized trace export, independent review rows and (only when available) genuine user exposure events:

```sh
python tools/pnelly_evaluation/prepare_pnelly_cases.py \
  --traces /secure/study/pnelly-traces.jsonl \
  --reviews /secure/study/pnelly-reviews.jsonl \
  --exposures /secure/study/pnelly-exposures.jsonl \
  --output /secure/study/prepared-cases.jsonl
```

Then produce the overall report and the Everyday / Elevated / Explore breakdown:

```sh
python tools/pnelly_evaluation/evaluate_pnelly_cases.py \
  --cases /secure/study/prepared-cases.jsonl \
  --output /secure/study/report.json \
  --k 3
```

You can also run the frozen core evaluator directly:

```sh
python tools/pnelly_evaluation/evaluate_outfits.py \
  --input /secure/study/prepared-cases.jsonl \
  --output /secure/study/core-report.json \
  --k 3
```

## Current release boundary

The evaluator, schema, joiner, tests and empty template are source/CI foundations only. No human-reviewed dataset is checked in. The product does not yet provide the complete consented study collector, randomized assignment service, look-level exposure/edit/rejection telemetry or an approved reviewer UI. Therefore there are no measured performance results, behavioural rates or causal uplift claims. CI fixtures are synthetic and test calculations only; they must never be included in real reports.
