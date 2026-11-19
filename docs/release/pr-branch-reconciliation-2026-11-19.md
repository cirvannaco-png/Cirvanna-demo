# PR and branch reconciliation — 19 November 2026

**Audit base:** main at 10627a63b7669fb8e94581642ab2b1ac7cc0c9df (observed 19 November 2026).  
**Policy:** do not merge a branch merely because its PR is open or its branch name sounds current. Compare against this exact main, inspect unique changes, resolve review findings, and rerun all required checks on the final PR head.

## Completed merges confirmed

| PR | Result | Notes |
|---|---|---|
| #219 | Merged 18 Nov 2026 | Twin structural validation and Marketplace UX slice. Its validator is not proof of anatomical validation or a Registry attestation. |
| #222 | Merged 18 Nov 2026 | Candidate-bound CAL cart/checkout proxy and immutable audit controls. Does not prove a live payment or production checkout. |

## Open pull requests

The live GitHub open-PR listing contained 17 items. The comparison below uses each current PR head SHA against the audit main SHA. “Ahead/behind” is commit divergence, not a measure of feature completeness.

| PR | Area | Ahead / behind | Current assessment | Reconciliation action |
|---|---|---:|---|---|
| #225 | Gateway discovery → CAL contract test | 2 / 0 at audit start | Clean main-based integration candidate; 1 changed test file. Review found provider calls could escape the test process when CI credentials are configured. | Forward-fix the test helper to stub CIL feedback signals and persisted NPL preferences. Re-run exact-head CI; resolve review only after verifying the new head. Merge only if every required check passes. |
| #206 | DermalSight roadmap | 3 / 23 | Documentation-only unique delta across ADR, roadmap and service README; diverged. | Do not merge stale head. Forward-port the roadmap to current main as a documentation-only PR after checking it against current DSI capabilities and provider evidence. |
| #204 | Production readiness: commerce, privacy, operations | 49 / 25 | Large draft with both code and operational/docs changes; diverged. Includes merchant/fulfilment adapters, telemetry hooks, runbook and privacy-verification work. | Do not merge wholesale. Split into separately reviewable forward-ports: operations/telemetry, provider adapters, privacy verification, and gate/manifest updates. Re-test each slice. |
| #202 | Release-readiness remediation docs | 5 / 25 | Documentation-only, diverged; overlaps in subject with #204. | Consolidate unique current acceptance criteria into one forward-port; do not create a second competing runbook or release-gate source. |
| #197 | PNELLY + wardrobe + Complementer | 17 / 28 | Gateway, BFF and demo-web changes; diverged and overlaps current marketplace/discovery code. | Port only demonstrated missing functionality after current-main contract review; preserve separate Complementer advisory authority and wardrobe consent boundaries. |
| #196 | CIL human CAL feedback + provider revocation | 14 / 30 | Important gateway, Decision Service and Intelligence Service changes including migrations; diverged. | Treat as a high-priority forward-port candidate. Reconcile schema/migration ancestry and provider revocation semantics first; port narrow changes with migration, replay, subject/context binding and fail-closed tests. |
| #195 | CIL runtime hardening | 25 / 31 | Overlaps the same gateway, Decision Service and Intelligence Service files as #196; diverged. | Do not merge alongside #196. Compare the two heads and select/compose the complete validated change set on current main; retire the duplicate only after unique changes are accounted for. |
| #182 | Click It consent and image-rights BFF | 2 / 49 | Only BFF main/test files differ; strongly stale. | Do not merge directly. Audit whether any route/consent checks are missing from current main; forward-port only missing safeguards. Keep Click It disabled until independent route and masking evidence passes. |
| #174 | Click It privacy publication hardening | 172 / 135 | Stacked on the privacy-governance feature branch, not main; massive divergence. | Not a direct main merge candidate. Extract independently reviewed publication/restore/syndication route controls into a clean current-main PR with source-lineage and privacy tests. |
| #111 | Outfit evaluation/publication guards | 165 / 135 | Stacked on privacy-governance feature branch; large overlapping delta. | Not a direct main merge candidate. Reconcile unique evaluation guards with #107/#174 and current image-publication inventory before porting. |
| #107 | Privacy-governance service foundation | 154 / 135 | Old main-based privacy stack with extensive overlap against later PRs and current files. | Do not merge as-is. Inventory its unique service/migration/security changes; port only those still absent from main and validate every public media route. |
| #102 | Multi-market commerce | 85 / 136 | Large old commerce/BFF/wardrobe delta and migration history; diverged. | No direct merge. Compare current migration chain and canonical offer contracts. Port missing provider-authenticated FX, tax, fulfilment and market/checkout capabilities as small forward-ports. |
| #84 | Look It separation | 63 / 140 | Broad old delta across BFF, Gateway, Identity Consent, Twin Registry, VTON and Vision; diverged. | No direct merge. Confirm Look It remains separate from Click It and port only missing consent-bound PNELLY behavior; keep image/media details behind CAL and privacy gates. |
| #67 | Intelligent marketplace filters | 11 / 146 | Stale multi-file delta across Catalog, Commerce, BFF and demo UI. | No direct merge. Re-check current filter/ranking contracts and forward-port any missing behavior with NPL hard-veto and CAL withholding tests. |
| #66 | Appearance specialist ecosystem | 51 / 146 | Stale multi-service delta across orchestrator, appearance package and identity core. | No direct merge. Reconcile against current appearance-intelligence contracts and source registry; port only supported, source-aligned pieces. |
| #64 | PAMASMMA / brand-auth | 42 / 574 | Targets integration/source-reconstruction ancestry, not current main; extremely stale. | Keep out of main. Inventory any independently required brand/distributor identity requirements against REL-19/22 before deciding whether to restart the work on a clean branch. |
| #62 | Earlier candidate-bound CAL purchase governance | 119 / 148 | Large old branch; its core purchase-proxy objective is now represented by merged PR #222. | Do not merge. Audit for unique non-overlapping work; close as superseded only after confirming no required unique code/tests remain. |

## Branch handling rules

1. main is the sole integration target for production-bound work. Stacked PRs must be forward-ported to a clean branch based on current main.
2. For each feature area, maintain one active integration PR. In particular, avoid parallel competing changes to CIL feedback (#195/#196), production readiness (#202/#204), and privacy publication (#107/#111/#174).
3. Every forward-port must identify source PR/commit, exact files/hunks carried forward, intentionally omitted stale changes, migration lineage, tests, and the new target head SHA.
4. A PR with unresolved review threads, failing/pending checks, or stale check results is not merge-ready.
5. Branches already fully contained in main should be recorded as incorporated; branches with no unique commits may be deleted only after confirming no open PR, release artifact, or collaborator dependency points to them.
6. Do not delete every stale-looking branch automatically. The branch listing is paginated and can contain active work without an open PR; branch deletion requires a complete inventory and ownership confirmation.

## Evidence still required

This audit is a source-control reconciliation snapshot, not a production certification. It does not prove deployed rollback, provider readiness, backup/restore, real customer checkout, photo privacy, FCI calibration, or full source-lineage completeness. Those remain governed by the 23-gate registry.
