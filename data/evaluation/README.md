# Restricted outfit evaluation data

The outfit evaluation schema and runner are versioned in this repository. The actual human-reviewed JSONL dataset is **not stored in GitHub**: it contains participant-level behaviour and should live in an encrypted, access-controlled evaluation workspace with a separate participant-key mapping.

Use outfit-review.schema.json to validate exports. Every candidate requires exactly two independent blinded reviews; duplicate reviewer entries are rejected and disagreements require an independent adjudicator. The evaluator reports raw exact agreement and Cohen's kappa within stable reviewer pairs. Do not populate this dataset with invented or AI-generated human labels. The repository's unit tests use synthetic fixtures solely to test metric calculations and are not evaluation evidence.
