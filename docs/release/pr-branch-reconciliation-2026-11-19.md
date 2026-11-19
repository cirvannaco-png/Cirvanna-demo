# PR and branch reconciliation — 19 November 2026

**Audit base:** `main` at `17b8a685a2d84e44d17ded2154b43f0f1921664d` (after PR #226; observed 19 November 2026).  
**Snapshot:** 16 open pull requests and 220 branch refs across three GitHub pages. Ahead/behind figures below compare each PR head with current `main`; they indicate divergence, not feature quality.  
**Policy:** `main` is the only production integration target. Never merge a stale/stacked branch wholesale or delete a branch solely because it has no open PR.

## Completed merges confirmed

| PR | Result | Notes |
|---|---|---|
| #219 | Merged 18 Nov 2026 | Twin structural validation and Marketplace UX. Structural mesh validation is not anatomical validation or a Registry attestation. |
| #222 | Merged 18 Nov 2026 | Candidate-bound CAL purchase proxy and immutable audit controls. Not evidence of live payment or production checkout. |
| #225 | Merged 19 Nov 2026 | Gateway discovery → CAL contract test. Exact head `c568d1546a59cd689fddbc23797ce50acc9d0211`; Architecture, Decision Gateway and Container image builds passed. Review finding on external CIL/NPL test calls was fixed/resolved. Synthetic CI only, not deployed staging. |
| #226 | Merged 19 Nov 2026 | Rollback evidence procedure/template/validator, operational evidence checks, and PR/branch snapshot. Exact PR head passed Architecture validation; template remains `not_executed`. No real rollback/restore drill is claimed. |

## Open pull requests

| PR | Area | Ahead / behind | Base branch | Assessment and next action |
|---|---|---:|---|---|
| #206 | DermalSight roadmap | 3 / 25 | main | Documentation-only delta (ADR, roadmap, README). Forward-port the useful roadmap to current DSI capabilities and licensed-provider status; do not merge stale head. |
| #204 | Provider evidence, privacy and operations | 49 / 27 | main | Large draft with Commerce/provider adapters, telemetry, runbook, privacy and gate/manifest changes. Split into independent current-main PRs; do not merge wholesale. |
| #202 | Merchant/privacy/operations remediation | 5 / 27 | main | Documentation-only and overlaps #204. Consolidate unique acceptance criteria into the canonical plan/runbooks; do not create competing sources of truth. |
| #197 | PNELLY + wardrobe + Complementer | 17 / 30 | main | Gateway/BFF/demo changes overlap current discovery path. Port only missing tested behavior; preserve advisory-only Complementer authority and consent-bound wardrobe. |
| #196 | CIL feedback + provider revocation | 14 / 32 | main | Gateway, Decision and Intelligence changes plus two migrations. High-priority narrow forward-port; reconcile migration ancestry, event semantics, subject/context binding and revocation before tests. |
| #195 | CIL runtime hardening | 25 / 33 | main | Overlaps the same 14 files as #196. Do not merge both. Compare unique commits/patches and produce one complete validated current-main line. |
| #182 | Click It BFF consent/rights | 2 / 51 | main | Only BFF main/test files differ; strongly stale. Port any missing authorization only after route-inventory review; Click It stays disabled pending independent privacy evidence. |
| #174 | Digest-bound privacy publication | 172 / 137 | feature/privacy-governance-service | Stacked privacy branch, 36-file divergence. Not a direct main merge candidate. Extract only independently reviewed publication/restore/syndication controls to a clean branch. |
| #111 | Outfit evaluation/publication guards | 165 / 137 | feature/privacy-governance-service | Stacked on the same privacy foundation and overlaps #107/#174. Reconcile unique guards against current route inventory; do not merge wholesale. |
| #107 | Privacy Governance foundation | 154 / 137 | main | Large old privacy service, BFF, Vision and Twin delta. Inventory code/migration not already present; port narrow pieces with complete public-media route tests. |
| #102 | Multi-market commerce | 85 / 138 | main | Commerce/BFF/Wardrobe and migration changes; old migration ancestry. Reconcile with current schema chain and provider-attested offer contracts; no direct merge. |
| #84 | Look It separation | 63 / 142 | main | Broad old BFF/Gateway/Consent/Twin/VTON/Vision delta. Preserve Look It vs Click It separation and port only missing consent-bound behavior; CAL remains the display authority. |
| #67 | Intelligent filters | 11 / 148 | main | Stale Catalog/Commerce/BFF/UI delta. Compare to current filters and forward-port only missing behavior with NPL hard-veto and CAL withholding tests. |
| #66 | Appearance specialist ecosystem | 51 / 148 | main | Stale orchestrator/appearance/identity delta. Reconcile with current contracts and source registry; port only supported, source-aligned functionality. |
| #64 | PAMASMMA / brand-auth | 42 / 576 | integration/source-reconstruction | Targets an old reconstruction branch, not main. Keep out of main; map any remaining business-tenant needs to REL-19/22 and restart only necessary work on current main. |
| #62 | Earlier CAL purchase governance | 119 / 150 | main | Core candidate-bound purchase-proxy objective is represented by #222. Audit unique remainder, then close as superseded only after proving no required unique code/tests remain. |

## Targeted non-PR branch inventory

The full branch listing is paginated (220 refs); only the branches below have been compared in this pass. This is not deletion approval.

| Branch | Current comparison | Assessment |
|---|---:|---|
| `feature/usi-explicit-alignment-core` | 0 ahead | Fully contained in main; no unique commits. |
| `feature/npl-hard-veto-core` | 0 ahead | Fully contained in main; no unique commits. |
| `feature/eepl-npl-cal-integration` | 0 ahead | Fully contained in main; no unique commits. |
| `feature/fci-cal-pipeline-integration` | 0 ahead | Fully contained in main; no unique commits. |
| `feature/pnelly-lookit-current-main-2026-11-09` | 0 ahead | Fully contained in main; no unique commits. |
| `feature/multimarket-integration-current-main-2026-11-09` | 0 ahead | Fully contained in main; no unique commits. |
| `integration/pnelly-evaluation-protocol-2026-11-18` | 0 ahead | Empty/stale integration branch; no unique commits. |
| `integration/provider-operations-forwardport-2026-11-18` | 0 ahead | Empty/stale integration branch; no unique commits. |
| `integration/dsi-challenge-forwardport-2026-11-18` | 0 ahead | Empty/stale integration branch; no unique commits. |
| `integration/cal-purchase-governance-forwardport-2026-11-18` | 0 ahead | Empty/stale integration branch; no unique commits. |
| `feature/human-reviewed-outfit-evaluation` | 19 ahead / 133 behind | Unique review-schema/tooling path. Candidate for a clean forward-port after checking against the alternate evaluator branches. |
| `feature/pnelly-evaluation-benchmark` | 9 ahead / 133 behind | Isolated evaluator/workflow/tests; compare with cleaner and reviewer-CI branches. |
| `feature/pnelly-outfit-evaluation-clean` | 5 ahead / 133 behind | Small evaluator subset; port candidate, not merge candidate. |
| `fix/pnelly-evaluation-reviewer-ci-current-main` | 19 ahead / 99 behind | Broader evaluator/reviewer CI; choose one canonical evaluator path after patch comparison. |
| `feature/pnelly-outfit-evaluation-benchmark` | 163 ahead / 136 behind | Mixed evaluation plus stale privacy/application code; do not merge wholesale. |
| `feature/wardrobe-pnelly-npl-eepl` | 44 ahead / 139 behind | Stale BFF/Gateway/Wardrobe delta; port only verified missing behavior. |
| `release/rollback-evidence-and-pr-reconciliation-2026-11-19` | 8 ahead / 2 behind | Superseded source branch; its useful work is merged through #226. Retain until no collaborator/release reference requires it; delete only after ownership check. |

## Branch and PR operating decisions

1. One current-main integration branch per workstream. Avoid parallel competing CIL (#195/#196), readiness (#202/#204) and privacy (#107/#111/#174) implementations.
2. Priority forward-ports: #196 (CIL review/revocation), #204 split into provider/operations/privacy slices, #206 DSI roadmap, then #197/#84 for PNELLY/Look It only where tests show a genuine gap.
3. Before porting a hunk, record source PR/commit, exact files carried forward, stale code intentionally omitted, migration ancestry, tests and new PR head SHA.
4. Merge only when exact-head checks pass, review threads are resolved, and no unique change is lost.
5. Complete all-page orphan-branch review before deletion. This pass is an inventory snapshot; 220 refs are not all individually compared or approved for deletion.

## Release-gate connection

- REL-01 now requires strict source-lineage audit. The ordinary architecture workflow still runs `--allow-unreconciled` during source migration; that is not release evidence.
- REL-10/16 require actual rollback and restore evidence; #226 provides the procedure/validator only.
- The 23-gate registry remains 23/23 blocked with empty evidence references and null verified commits.

This is a source-control snapshot, not production certification. It does not prove deployed rollback, database restore, provider readiness, real checkout, privacy verification, FCI calibration or complete source-lineage reconciliation.
