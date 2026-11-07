# Restricted outfit evaluation data

The outfit evaluation schema and runner are versioned in this repository. The actual human-reviewed JSONL dataset is **not stored in GitHub**: it contains participant-level behaviour and should live in an encrypted, access-controlled evaluation workspace with a separate participant-key mapping.

Use outfit-review.schema.json to validate exports. Every candidate requires exactly two independent blinded reviews; duplicate reviewer entries are rejected and disagreements require an independent adjudicator. The evaluator reports raw exact agreement and Cohen's kappa within stable reviewer pairs. Do not populate this dataset with invented or AI-generated human labels. The repository's unit tests use synthetic fixtures solely to test metric calculations and are not evaluation evidence.


## PNELLY trace ingestion

PNELLY traces are generated only when the Recommendation Service evaluation
flag and HMAC pseudonymization key are enabled. The public BFF strips the trace;
collection is restricted to the authenticated internal API Gateway. The trace
is role-specific and includes the full candidate pool plus NPL exclusion
context. Raw account IDs, wardrobe item IDs, display names and images are not
exported.

1. Collect trace JSONL from the controlled study collector.
2. Have two independent reviewers rate every candidate using
   `apps/demo-web/outfit-review.html`.
3. Export their review JSONL files separately. Do not reveal system ranking or
   system assignment to reviewers.
4. The study coordinator verifies reviewer independence; the joiner checks distinct reviewer keys but cannot authenticate real people. Join reviews and any genuine exposure records with
   `scripts/evaluation/prepare_pnelly_cases.py`.
5. Run the overall and role-stratified reports with
   `scripts/evaluation/evaluate_pnelly_cases.py`.

The review tool is metadata-only. It does not establish visual styling,
fit, or try-on accuracy. Human-labelled data and live outcome records must be
collected before any adoption, relevance or retention claim is reported.
