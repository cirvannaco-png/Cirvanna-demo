# PNELLY outfit evaluation dataset

This is an evaluation contract and evaluator, not a dataset or evidence of ranking quality. Populate the JSONL only with consented, de-identified sessions and trained reviewers. Do not include identity, contact details, raw photos, exact location, or free-text personal data.

## One adjudicated row per candidate outfit per recommendation session

Required fields:

- `session_id`: random session identifier; no account ID.
- `user_pseudonym`: stable random pseudonym for measuring repeated rejection.
- `outfit_id`: opaque outfit ID.
- `algorithm_rank`: original 1-based algorithm rank.
- `human_relevance`: adjudicated blinded rating 1–5 against the declared occasion, user constraints and style request.
- `hard_exclusion_violation`: adjudicated reviewer finding for a user-declared hard exclusion, cultural constraint, dress code or other hard rule.
- `edited`, `rejected`: explicit user events, not reviewer guesses.
- `occasion_match`, `preference_match_count`: grounded in declared request and consented preferences only.
- `garment_categories`, `style_tags`: normalized non-sensitive labels for diversity.
- `human_reviewed`: must be true.
- `reviewer_ids`: at least two distinct pseudonymous reviewer IDs.
- `review_rubric_version`: non-empty rubric version used for independent scoring and adjudication.

Two reviewers independently assess relevance and exclusion violations while blinded to algorithm rank. A documented adjudication resolves disagreements into the two adjudicated label fields. The evaluator validates that two distinct reviewers are recorded; it cannot independently prove that the review process occurred.

## Sampling and split protocol

1. Sample across occasions, climate/context availability, wardrobe completeness, price bands, fit constraints explicitly supplied by the user, and target markets. Report subgroup failures separately.
2. Keep a chronological holdout split by user pseudonym. No user may appear in both development and final holdout partitions.
3. Report algorithm and baseline on identical candidate sets and sessions. Do not use evaluation labels for training or tuning.
4. A repeated rejection is the same user pseudonym rejecting the same outfit ID in at least two distinct sessions. Duplicate events within one session do not count twice.
5. Never infer sensitive traits or preferences from exposure. Do not treat impressions as consent or rejection.

## Metrics at K (default K=3)

- Human relevance: mean adjudicated 1–5 score in top K.
- Diversity: mean pairwise Jaccard distance over garment categories and style tags in top K.
- Hard-exclusion violation: share of top-K candidates violating a hard rule. Any violation is release-blocking.
- User edit and explicit rejection rates: shares of top-K looks with those explicit events.
- Repeated rejection: share of unique rejected user/outfit pairs rejected in two or more distinct sessions.

The simple baseline is deterministic and safety-first: hard-exclusion-violating outfits rank last, then occasion match, then explicit preference overlap, then outfit ID. This order is intentional; safety cannot be traded for preference relevance.

The evaluator reports percentile-bootstrap 95% confidence intervals over sessions for session-level metrics and paired algorithm-minus-baseline intervals. These intervals are descriptive, not proof of generalization, especially for small samples. The evaluator does not calculate inter-rater reliability; retain reviewer-level scores and report agreement separately before adjudication.

## Run

```sh
python tools/pnelly_evaluation/evaluate_outfits.py path/to/reviewed.jsonl --k 3
```

The committed template is empty. Do not claim quality, improvement, or market readiness until a real human-reviewed dataset exists, the locked chronological holdout is evaluated, subgroup results are inspected, and safety gates pass.
