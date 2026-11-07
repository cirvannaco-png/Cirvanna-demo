# PNELLY outfit evaluation dataset

This directory contains the evaluation contract and evaluator, not fabricated
training/evaluation labels. Populate the JSONL only with consented, de-identified
sessions reviewed by trained human evaluators. Keep identity, contact details,
photos, and raw free-text out of this benchmark.

## One row per candidate outfit per recommendation session

Required fields:

- `session_id`: random evaluation-session identifier; no account ID.
- `user_pseudonym`: stable random pseudonym for repeated-rejection measurement.
- `outfit_id`: stable opaque outfit ID, not a person identifier.
- `algorithm_rank`: algorithm's original 1-based rank.
- `human_relevance`: blinded human rating 1–5 against the declared occasion,
  weather/context, wardrobe constraints and style request.
- `hard_exclusion_violation`: reviewer-confirmed violation of a user-declared
  hard exclusion, cultural constraint, dress-code requirement or other hard rule.
- `edited`: user changed garment(s) in the displayed outfit.
- `rejected`: user explicitly rejected the outfit.
- `occasion_match`: whether the outfit satisfies the declared occasion.
- `preference_match_count`: count of explicit, consented preference matches;
  do not derive sensitive traits or infer preferences from exposure alone.
- `garment_categories`, `style_tags`: normalized, non-sensitive labels used
  only to calculate within-session diversity.
- `human_reviewed`: must be true.
- `reviewer_id`: pseudonymous reviewer identifier.

Optional metadata may include locale, climate freshness bucket, catalog version,
wardrobe snapshot version, algorithm version, and review disagreement. Do not
include raw images or exact location. Record the review rubric/version separately.

## Review protocol

1. Sample sessions across occasions, weather/context availability, wardrobe
   completeness, price bands, body/fit constraints supplied by the user, and
   target markets. Do not collapse subgroup failures into one average.
2. Two reviewers independently score relevance and exclusion violations while
   blinded to algorithm rank. Adjudicate disagreements; record reviewer IDs and
   rubric version. Any hard-exclusion violation is release-blocking.
3. Keep a chronological holdout split by user pseudonym. No user may appear in
   both development and final holdout partitions.
4. Capture edits and rejections as explicit events. A repeated rejection means
   the same user pseudonym rejects the same outfit ID in at least two distinct
   sessions. Do not count repeated impressions as independent people.
5. Report the algorithm and baseline on exactly the same sessions and candidate
   sets. Baseline is intentionally simple: occasion match first, then explicit
   preference overlap, with hard-exclusion violations ranked last.
6. Report sample size and confidence intervals before making product claims.
   A zero-violation observed sample is not proof of zero risk.

## Metrics

- Human relevance@3: mean blinded 1–5 score for the top three.
- Diversity@3: mean pairwise Jaccard distance across garment categories and
  style tags in the top three.
- Hard-exclusion violation@3: share of top-three looks violating a hard rule.
- User edit@3 and explicit rejection@3: shares of top-three looks edited/rejected.
- Repeated rejection: share of unique rejected user/outfit pairs rejected in
  two or more distinct sessions.

Run:

```sh
python tools/pnelly_evaluation/evaluate_outfits.py path/to/reviewed.jsonl --k 3
```

The repository intentionally ships an empty dataset template. Do not report
algorithm quality or claim an improvement until a real human-reviewed dataset
has been collected and the same-session baseline comparison has been run.
