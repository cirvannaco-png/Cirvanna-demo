# Restricted outfit evaluation data

The versioned case contract is `outfit-review.schema.json`. Actual participant-level reviewed JSONL must **not** be stored in this repository. Keep it in an encrypted, access-controlled evaluation workspace with participant-key mapping stored separately.

Each case freezes one participant/session, user-declared context, the complete candidate pool, the Cirvanna ranking, exactly two independent blinded human reviews per candidate, any independent adjudication, and actual exposures/outcomes from the participant's assigned system arm.

The joiner enforces:
- consent assertion on the source trace and absence of raw account IDs, wardrobe IDs, names, image URLs, assets and storage keys;
- complete, non-truncated candidate pools;
- exactly two distinct reviewers per candidate;
- one randomized experiment arm per participant across sessions;
- exposures only for the assigned arm's top-k, with at most one outcome per look per session.

The test fixtures are synthetic and exist only to validate code. They are not user data, human labels, or model-quality evidence. The data directory intentionally contains no real reviewed records.

Use the documented workflow in `docs/evaluation/outfit-evaluation-protocol.md`. The current product does not yet ship a consented study collector, randomized assignment service, full look-level exposure/edit/rejection telemetry, or approved reviewer UI. Therefore observed user-behaviour metrics remain unavailable until those systems are implemented and verified.

The reviewer joiner checks pseudonymous reviewer keys but does not authenticate the real-world identity or independence of reviewers. A separate study coordinator must verify and document reviewer independence outside the dataset.
