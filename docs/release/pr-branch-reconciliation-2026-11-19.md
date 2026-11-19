# PR and branch reconciliation — 19 November 2026

**Audit base:** `main` at `3267003d6669e937869b3859bd4f03442721e6ec` (after the PR #225 merge; observed 19 November 2026).  
**Snapshot:** GitHub returned 218 branch refs across three pages and 16 open pull requests.  
**Policy:** do not merge a branch merely because its PR is open or its name sounds current. Compare against this exact main, inspect unique changes, resolve review findings, and rerun required checks on the final PR head.

## Completed merges confirmed

| PR | Result | Notes |
|---|---|---|
| #219 | Merged 18 Nov 2026 | Twin structural validation and Marketplace UX slice. The validator is not proof of anatomical validation or a Registry attestation. |
| #222 | Merged 18 Nov 2026 | Candidate-bound CAL cart/checkout proxy and immutable audit controls. Does not prove live payment or production checkout. |
| #225 | Merged 19 Nov 2026 | Gateway discovery → CAL contract test. Exact head `c568d1546a59cd689fddbc23797ce50acc9d0211`; Architecture validation, Decision gateway checks and Container image builds all passed. A review finding about external CIL/NPL calls was fixed and the thread resolved. Synthetic CI only; not deployed staging or REL-11 evidence. |

## Open pull requests

Ahead/behind counts below are current comparisons against main at the audit base. They measure commit divergence, not feature completeness or merge readiness.

| PR | Area | Ahead / behind | Current assessment | Reconciliation action |
|---|---|---:|---|---|
| #206 | DermalSight roadmap | 3 / 24 | Documentation-only delta across ADR, roadmap and service README; diverged. | Do not merge stale head. Forward-port the roadmap after checking claims against current DSI capability, licences and provider evidence. |
| #204 | Production readiness: commerce, privacy, operations | 49 / 26 | Large draft with code and operational/docs changes; diverged. | Do not merge wholesale. Split into separately reviewable current-main PRs: operations/telemetry, provider adapters, privacy verification, and gate/manifest updates. |
| #202 | Release-readiness remediation docs | 5 / 26 | Documentation-only, diverged; overlaps #204. | Consolidate unique current acceptance criteria into one runbook and one gate source; do not create competing operational procedures. |
| #197 | PNELLY + wardrobe + Complementer | 17 / 29 | Gateway, BFF and demo-web changes; diverged and overlaps current discovery/marketplace code. | Port only demonstrably missing behavior after current-main contract review. Preserve Complementer advisory-only authority and wardrobe consent boundaries. |
| #196 | CIL human CAL feedback + provider revocation | 14 / 31 | Gateway, Decision Service and Intelligence Service changes, including two migrations; diverged. | High-priority forward-port candidate. Reconcile migration ancestry and provider-revocation semantics; port narrowly with subject/context binding, replay and fail-closed tests. |
| #195 | CIL runtime hardening | 25 / 32 | Overlaps the same gateway, Decision and Intelligence files as #196; diverged. | Do not merge alongside #196. Compare both patches and select one complete validated change set on current main; retire duplicate only after accounting for unique work. |
| #182 | Click It consent and image-rights BFF | 2 / 50 | Two BFF files; strongly stale. | Do not merge directly. Audit for safeguards absent from main and port only those. Click It remains disabled pending independent route and masking evidence. |
| #174 | Click It privacy publication hardening | 172 / 136 | Stacked on the privacy-governance feature branch rather than main; massive divergence. | Not a direct main merge candidate. Extract independently reviewed publish/restore/syndication route controls into a clean current-main PR with source-lineage and privacy tests. |
| #111 | Outfit evaluation/publication guards | 165 / 136 | Stacked on privacy-governance ancestry; large overlapping delta. | Reconcile unique evaluation guards with #107/#174 and the current publication inventory before porting. |
| #107 | Privacy-governance service foundation | 154 / 136 | Old privacy stack with extensive overlap against later PRs and current files. | Do not merge as-is. Inventory unique service/migration/security changes; port only those still absent from main and validate every public media route. |
| #102 | Multi-market commerce | 85 / 137 | Large old Commerce/BFF/Wardrobe delta and migration history; diverged. | No direct merge. Compare current migration chain and canonical offer contracts. Port missing provider-attested FX, tax, fulfilment and market/checkout capabilities as small forward-ports. |
| #84 | Look It separation | 63 / 141 | Broad old delta across BFF, Gateway, Identity Consent, Twin Registry, VTON and Vision; diverged. | No direct merge. Preserve Look It / Click It separation; port only missing consent-bound PNELLY behavior. Product and offer details remain behind CAL. |
| #67 | Intelligent marketplace filters | 11 / 147 | Stale Catalog, Commerce, BFF and demo UI delta. | No direct merge. Re-check current filter/ranking contracts and add NPL hard-veto and CAL withholding tests to any port. |
| #66 | Appearance specialist ecosystem | 51 / 147 | Stale multi-service delta across orchestrator, appearance package and identity core. | No direct merge. Reconcile with current appearance-intelligence contracts and source registry; port only supported, source-aligned parts. |
| #64 | PAMASMMA / brand-auth | 42 / 575 | Targets `integration/source-reconstruction`, not current main; extremely stale. | Keep out of main. Map any remaining brand/distributor identity requirements to REL-19/22 and restart only the necessary scope on a clean branch. |
| #62 | Earlier candidate-bound CAL purchase governance | 119 / 149 | Large old branch; core purchase-proxy objective is represented by merged PR #222. | Do not merge. Audit for unique non-overlapping code/tests; close as superseded only after confirming no required unique work remains. |

## Non-PR branch audit

The branch listing contains 218 refs, so branch cleanup must not be based on age or naming alone. The following targeted comparisons were made against current main:

| Branch | Ahead / behind | Assessment |
|---|---:|---|
| `feature/usi-explicit-alignment-core` | 0 / 524 | Fully contained in main; no unique commits. |
| `feature/npl-hard-veto-core` | 0 / 531 | Fully contained in main; no unique commits. |
| `feature/eepl-npl-cal-integration` | 0 / 533 | Fully contained in main; no unique commits. |
| `feature/fci-cal-pipeline-integration` | 0 / 528 | Fully contained in main; no unique commits. |
| `integration/pnelly-evaluation-protocol-2026-11-18` | 0 / 5 | Empty/stale relative to main; no unique commits. |
| `integration/provider-operations-forwardport-2026-11-18` | 0 / 18 | Empty/stale relative to main; no unique commits. |
| `integration/dsi-challenge-forwardport-2026-11-18` | 0 / 18 | Empty/stale relative to main; no unique commits. |
| `integration/cal-purchase-governance-forwardport-2026-11-18` | 0 / 6 | Empty/stale relative to main; no unique commits. |
| `feature/pnelly-lookit-current-main-2026-11-09` | 0 / 37 | Fully contained in main; no unique commits. |
| `feature/multimarket-integration-current-main-2026-11-09` | 0 / 42 | Fully contained in main; no unique commits. |
| `feature/human-reviewed-outfit-evaluation` | 19 / 133 | Unique evaluation protocol/schema/tooling; candidate for a clean reviewable forward-port. |
| `feature/pnelly-evaluation-benchmark` | 9 / 133 | Isolated evaluation runner/workflow/tests; review for overlap with cleaner evaluation branches. |
| `feature/pnelly-outfit-evaluation-clean` | 5 / 133 | Small isolated evaluation subset; inspect as a port candidate, not a merge candidate. |
| `fix/pnelly-evaluation-reviewer-ci-current-main` | 19 / 99 | Broader evaluator + reviewer workflow; compare against the human-reviewed evaluation branch before selecting one canonical path. |
| `feature/pnelly-outfit-evaluation-benchmark` | 163 / 136 | Mixed evaluation and stale privacy/application changes; do not merge wholesale. |
| `feature/wardrobe-pnelly-npl-eepl` | 44 / 139 | Stale BFF/Gateway/Wardrobe integration delta; port only verified missing behavior. |

No branch was deleted in this audit. Branches with zero unique commits are cleanup candidates only after confirming there is no active collaborator, release, or external reference dependency. Remaining refs require paginated comparison before deletion.

## Reconciliation rules and next execution order

1. `main` is the sole integration target for production-bound work. Stacked PRs must be forward-ported to a clean branch based on current main.
2. Maintain one active integration PR per feature area: avoid competing changes to CIL feedback (#195/#196), production readiness (#202/#204), and privacy publication (#107/#111/#174).
3. For each forward-port, record source PR/commit, carried files/hunks, intentionally omitted stale changes, migration lineage, tests and exact target head SHA.
4. Merge only after required exact-head workflows pass and blocking review threads are resolved.
5. Prioritize #196 for a narrow CAL feedback/provider-revocation forward-port; split #204/#202 into discrete operations/provider/privacy changes; port #206 as a corrected DSI roadmap. Do not merge #62 because #222 supersedes its core purchase-governance objective.
6. Continue the orphan-branch inventory across all 218 refs before deleting any branch. Containment is not the same thing as deletion approval.

## Evidence boundary

This report is a source-control snapshot, not production certification. It does not prove deployed rollback, provider readiness, backup/restore, real customer checkout, photo privacy, FCI calibration, or complete source-lineage reconciliation. Those remain governed by the 23-gate release registry.
