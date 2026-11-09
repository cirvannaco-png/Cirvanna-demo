# Inter-model recommendation calibration protocol

**Status:** protocol specified; no production inter-model calibration is certified and the human-reviewed evaluation dataset remains empty.

## Purpose

Compare PNELLY, Complementer-assisted ranking, any future recommendation model, and the deterministic baseline without treating their raw scores as interchangeable. Ranking quality, probability calibration, user outcomes and CAL authorization are distinct concepts.

## Canonical study unit

One case is one pseudonymous participant/session, one fixed candidate pool, one declared context and market, and the outputs of every evaluated model over that exact pool. Candidate identity and product facts must be frozen to the same Catalog version. Do not compare models run against different inventory, merchant offers, price snapshots, candidate pools or context.

Required case provenance:
- pseudonymous participant and session keys;
- stable model ID, model version, prompt/config version and output timestamp for each evaluated model;
- common candidate IDs and canonical Catalog/product versions;
- declared context and market slice, with no inferred protected traits;
- explicit hard exclusions and cultural requirements as user-declared inputs;
- candidate scores/rankings and model-specific score semantics;
- two blinded independent human reviews for every evaluated candidate;
- third independent adjudication when reviewers disagree;
- source trace, consent scope, candidate-pool completeness and data snapshot hashes.

The real evaluation dataset belongs in a restricted encrypted study workspace, not Git. Do not store account IDs, names, photos, image URLs, storage keys, raw body measurements or inferred sensitive traits.

## Separate calibration and final holdout

1. Freeze an evaluation protocol and the relevance target (for example, human relevance rating 4–5 on a 1–5 rubric) before examining model results.
2. Split by participant and time. No participant or session used for final holdout may leak into a model's calibration fit. Keep calibration and final holdout datasets, candidate pools and hashes separate.
3. Calibrate each model's raw score independently onto the same relevance target using only its calibration split. Keep each calibrator version, training data hash and method. Do not calibrate on the final holdout.
4. Use the untouched holdout to compare calibrated probabilities and ranking outcomes. Raw scores remain private to each model's rank ordering and are never directly blended across models.
5. Re-evaluate when model weights, prompt policy, candidate generation, ranking logic, Catalog features or market coverage changes.

## Metrics

Report each model separately and paired against the same cases:
- nDCG@k and pairwise ranking accuracy;
- Brier score, expected calibration error and reliability bins for calibrated relevance probability;
- within-slate diversity and category coverage;
- no-result rate, top-k fill and candidate-pool coverage;
- per-market and per-category sample counts, confidence intervals and missingness;
- explicit user approval, edits, rejections and repeated rejections from real randomized exposures only;
- model latency and provider failure rate.

A model that produces an empty slate must not receive a fabricated zero-violation success. Unknown outcomes remain unlabelled, not failures. Do not claim improvement from synthetic fixtures, a single user, or unpaired samples.

## Safety and decision separation

Hard exclusions, legal/safety evidence, explicit cultural requirements and CAL remain independent gates. Any hard-exclusion violation is release-blocking; it cannot be offset by relevance, diversity, acceptance or conversion. Recommendation calibration never authorizes a product display. Every product candidate must pass the canonical CAL decision path, and only CAL SHOW may release product/offer details.

Complementer is an advisory collaborator, not an independent user profile, Catalog or display authority. If a model suggests a product not in the frozen canonical pool, that is an unsupported candidate and must be excluded from the scored comparison until Catalog identity and required evidence are resolved.

## Acceptance gate

No cross-model score blending or superiority claim until:
- the rubric, calibration algorithm and thresholds are pre-registered;
- the human-reviewed dataset meets the study's sample and inter-rater requirements;
- participant/time holdout integrity is verified;
- every model has its own calibration artifact and frozen version;
- hard-constraint violations are zero;
- holdout metrics include uncertainty and relevant market/category slices;
- real randomized exposure/outcome capture is operating with consent and deletion controls;
- the signed report is reviewed by an accountable model-risk owner.

The existing PNELLY evaluator can provide human-review and baseline ranking metrics, but does not yet provide this multi-model calibration study. Its empty dataset means there are no empirical inter-model results today.
