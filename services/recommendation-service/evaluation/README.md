# Human-reviewed outfit evaluation

## Why this exists

The current canonical Recommendation Service is Complementer: a stateless, advisory look-coordination API. It is not yet a validated three-outfit ranker. The Wardrobe service records explicit item-level feedback and forwards consented signals to TAL/NPL, but does not yet persist outfit-level edit histories or three-look exposure/rejection events. This evaluation harness therefore creates a strict offline contract without pretending those missing signals already exist.

The evaluator expects a capture adapter to supply each candidate's `algorithm_score`. The active Complementer response does not currently emit ranked complete-outfit candidates or that score; therefore the harness is not yet connected to a serving three-look ranker and cannot produce a valid algorithm-vs-baseline result until that product path exists.

## Paired experiment design

For each scenario, freeze one candidate pool and score every candidate with both:
1. **Current algorithm** — the candidate's `algorithm_score` emitted by the system under test.
2. **Simple baseline** — a transparent, non-personalized score calculated by the harness: 50% category completeness, 30% Jaccard overlap with user-declared context tags, and 20% Jaccard overlap with declared style preferences.

Both rankers see the same candidates, item facts and scenario. Do not compare different retrieval pools. The default slate size is three because Daily Looks is a three-look experience. Rank ties break by opaque `outfit_id` for deterministic replay.

The baseline is intentionally unsophisticated. It is a control, not a production replacement. The algorithm's score must be produced without seeing review labels or locked-test outcomes.

## Human review protocol

- Hide ranker name, score, rank and model version from reviewers. Randomize candidate order per reviewer.
- Require two independent reviewers per candidate; use a third adjudicator where relevance differs by two or more points or exclusion labels disagree.
- Rate relevance to the declared context, outfit coherence, and context fit independently from 1 (poor) to 5 (excellent).
- Record exclusion violations as a separate binary safety label, with a reason code. A reviewer may flag a violation even when the automatic detector did not.
- Record `accept`, `reject` or `edit`; an edit must enumerate replacement item IDs. Reviewer edits are annotations, **not** a substitute for real user edits.
- Review garment facts and approved masked previews only. Do not infer identity, age, culture, religion, body shape, skin tone or other sensitive attributes from a person or image. Use only expressly declared context and product metadata.
- Preserve reviewer blinding and randomization through adjudication. Retain reviewer pseudonyms and the minimum audit metadata needed for agreement analysis.

## Required metrics

| Metric | Definition |
|---|---|
| Relevance@3 | Mean of the two independent human relevance ratings across the three highest-ranked outfits |
| NDCG@3 | Discounted gain of human relevance ratings, normalized against the ideal order for the same candidate pool |
| Coherence / context fit | Mean human scores at the top three |
| Diversity@3 | Mean pairwise Jaccard distance across selected outfit categories, colors and style tags |
| Exclusion violation rate@3 | Fraction of displayed top-three outfits with any human-confirmed possible hard-exclusion violation; must be zero |
| Known exclusion-hit rate@3 | Fraction of top-three outfits with an upstream explicit-constraint hit |
| User edit rate | Unique exposed recommendation IDs with at least one `edited` event / unique exposed recommendation IDs; report changed item count per exposure |
| Rejection rate | Explicit `rejected` events / exposures |
| Repeated rejection rate | Share of subject–outfit pairs with at least two distinct rejected exposure IDs among pairs rejected at least once |
| Re-exposure after rejection | Count of exposures of the same subject–outfit pair after its first rejection; this should trend to zero |

The tool reports a missing user metric as `null`, not zero, when no user events have been instrumented. Rejection and edit rates must be computed only from purpose-consented user events, not inferred from dwell time, non-clicks or reviewer labels. Do not silently convert item-level NPL rejections into outfit-level rejections.

## Dataset split and leakage

- Capture scenarios across expressly declared contexts (occasion, climate, category, style and user-declared exclusions). Use stratified sampling; do not infer demographic strata from images.
- Keep a development split for iteration and a separately access-controlled, chronologically later locked test split. Freeze candidate generation and baseline definitions before opening locked-test labels.
- Do not tune weights on the locked test set. Record the recommender version, candidate pool, feature provenance, randomization seed, reviewer protocol version and evaluation timestamp in a run manifest.
- Human reviews require two independent annotators per candidate. Track disagreement and adjudication; the evaluator surfaces unresolved disagreement rather than hiding it in a single mean.
- Report both overall and declared-context slices. Suppress small cells; do not publish subgroup conclusions where sample size is inadequate. Sample-size and confidence-interval planning must be done before making accuracy or superiority claims.

## Release gates

1. Every displayed candidate passes the existing NPL, cultural-requirement and CAL hard gates. A score never overrides a veto.
2. Human exclusion violations in the top-three output: **zero**. Any violation blocks release and requires root-cause review.
3. The algorithm must improve or maintain human relevance/NDCG relative to the baseline on the locked test set; a training-only gain is not sufficient.
4. Diversity cannot regress materially while relevance improves; set a pre-registered non-inferiority margin before unblinding.
5. User edit, repeated rejection and post-rejection re-exposure rates must be measured from consented production events before claiming product-market fit or retention improvement.
6. Publish the dataset manifest, missing-data report, inter-rater disagreement/adjudication report and locked-test metrics with each recommendation-model release.

## Run

```bash
cd services/recommendation-service
python -m evaluation.outfit_eval /path/to/reviewed-outfits.jsonl --split locked_test --k 3 --output metrics.json
```

The checked-in template is only a blank intake header. There are no reviewed examples and no human performance claims until the dataset is populated and independently annotated.
