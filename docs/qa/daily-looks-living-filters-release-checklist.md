# Daily Looks and Living Filters — Release Checklist

Status is intentionally evidence-based. A code path or automated emulation is not considered proof that the corresponding product behavior works in production.

## Implemented in the current change set

- [x] Daily Looks is reachable from the authenticated Wardrobe page through the Marketplace BFF.
- [x] The UI renders Everyday, Elevated, and Explore results and reports incomplete looks explicitly.
- [x] The UI does not claim that a recommendation is a Virtual Twin render. It shows the Twin preview as unavailable unless the backend returns a ready, safe preview URL.
- [x] Evaluation trace is disabled by default and fails closed when its HMAC key is missing or too short.
- [x] The trace carries role-specific candidate pools, ranking order/scores, NPL-blocked candidate references, and keyed pseudonyms.
- [x] The public BFF strips the internal evaluation trace before returning a browser response.
- [x] The trace handoff includes a two-reviewer joiner, schema validation, a blinded metadata-review page, role-level evaluation, and no-result rates.
- [x] Baseline comparison is replayed offline against the same candidate pool; it is not represented as a randomized live experiment.
- [x] CI includes responsive Chromium viewport checks for the demo Marketplace/Wardrobe pages, including a dedicated Living Filters page if one exists.
- [x] A physical Android acceptance sheet covers blur timing, permissions, orientation, gestures, keyboard, network, accessibility, and performance.

## Evidence and deployment gates still open

- [ ] Two actual independent reviewers complete every candidate rating. The joiner checks different reviewer keys; the study coordinator must verify real reviewer identities.
- [ ] Visual review is still separate. The current reviewer page judges metadata/tags only; it does not validate the appearance of the assembled garments, physical fit, or try-on realism.
- [ ] Live user exposures are not yet collected by the composer. The trace explicitly reports `user_exposure_state=not_collected_by_composer`.
- [ ] Look-level user edits, accepted/worn looks, and repeated rejections need an authenticated event pipeline keyed to the look reference. Do not substitute garment-level likes/dislikes for outfit-level outcomes.
- [ ] The baseline is not yet a randomized live control arm. Current comparisons support offline ranking analysis only, not causal uplift claims.
- [ ] Persistent Twin retrieval and preview generation remain open under issue #108. The integration contract is documented; the existing Twin service API and asset lifecycle must be confirmed before implementation.
- [ ] Physical Android QA remains unperformed. CI viewport emulation cannot validate touch behavior, camera permissions, GPU/rendering, memory pressure, or a brief privacy-blur flash on the actual handset.
- [ ] Evaluation secrets must be created in the secret manager and configured only in a controlled research environment. Keep the trace flag disabled for normal production.
- [ ] Production database migrations, asset storage, deletion-worker readiness, signed preview URLs, and cross-device Twin persistence require end-to-end verification before promotion.

## Promotion rule

Do not report an outfit relevance win, user-retention improvement, lower rejection rate, working persistent Twin, or completed Android QA until the corresponding evidence above is attached and reviewed. The current deliverable is an integrated Daily Looks UI plus guarded offline-evaluation and QA scaffolding, not a completed experiment or production Twin preview.
