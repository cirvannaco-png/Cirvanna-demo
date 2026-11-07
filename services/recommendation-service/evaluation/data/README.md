# Human-review dataset intake

This directory intentionally contains **no synthetic human labels** and no personal photos. Start from `annotation-template.csv` and create a versioned JSONL evaluation dataset outside source control unless each record has been approved for repository storage.

Each JSONL row represents one de-identified recommendation scenario:

- `dataset_version`: schema version, currently `1.0`.
- `case_id`: random opaque case identifier; never a user ID.
- `split`: `development` or `locked_test`.
- `scenario`: `context_tags`, explicitly declared `style_preferences`, and explicitly declared `hard_exclusions`.
- `candidate_outfits`: same candidate pool presented to both rankers, with item IDs, categories, colors, style/context tags, the current algorithm score, and any machine-detected hard-exclusion hits.
- `human_reviews`: at least two independent, blinded reviewer records per candidate. Ratings are integer 1–5 for relevance, coherence and context fit; exclusion violation is a conservative boolean; edit disposition must include proposed replacement item IDs.
- `user_outcomes`: optional consented production events. Every action refers to one `exposure_id` so edits/rejections are deduplicated against actual impressions. Use a rotating, keyed pseudonymous `subject_key`; never store a raw account ID, name, email, face image, exact address or free-text sensitive information here.

A row is not evaluation-ready until every candidate has two independent reviews. Conflicting exclusion labels or a relevance disagreement of at least two points must go to an adjudicator; the metric script conservatively counts any exclusion flag as a possible violation even before adjudication.

Keep source images out of the dataset by default. Review garment metadata and approved, already-masked previews only. If a human reviewer needs an image, use a separate access-controlled review store with explicit purpose/retention consent and publication-safe image assets. Never check raw portraits into Git.
