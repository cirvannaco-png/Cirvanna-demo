# Branch reconciliation — 22 November 2026 (graph pass + PR delta)

Repository: `cirvannaco-png/Cirvanna-demo`  
Current main observed: `210e9e370782a13bc69b93286bf8d3cd8ab3cc69`  
Method: GitHub branch-ref inventory and commit-ancestry comparisons. This is a graph-level audit, not a code-quality review of every diverged branch.

## Inventory

- Last complete inventory: **304 branch refs** total, including `main` (303 non-main refs).
- **301 unique commit heads** across those refs; three duplicate-head pairs reduce the unique count by three.
- **300 unique non-main commit heads**.
- `main` reports `protected: false`; required PR/review/check enforcement remains an administrator blocker tracked by [#271](https://github.com/cirvannaco-png/Cirvanna-demo/issues/271).
- The counts are a timestamped snapshot. Re-run the full paginated inventory before any branch deletion or archival operation.

## Ancestry classification and changes since the last full pass

The last complete graph pass classified the 300 unique non-main heads as **231 diverged**, **67 behind-only**, and **2 ahead-only** against main `856fb986b5c626911137028a2c40f469dc4d8bb6`.

Since that pass, PR #315 was merged. Its branch head `8d0253c57055f3f5c0bb5da9070bad3f5b2301ae` is now reachable from main through merge commit `210e9e370782a13bc69b93286bf8d3cd8ab3cc69`; its retained branch ref is therefore behind-only, not ahead-only. PR #314 remains open and is now **10 ahead / 1 behind** main. This produces a reconciled classification of **231 diverged**, **68 behind-only**, and **1 ahead-only** across the same 300 unique non-main heads, assuming no intervening branch-ref changes. This is a delta reconciliation, not a fresh 300-head rescan.

A behind-only branch contains no commit absent from main; it is an archival/deletion candidate, not an automatic deletion. A diverged branch may contain useful work, already-squash-merged work, superseded work, or unsafe/obsolete code. Ahead/behind counts alone do not determine merge or deletion eligibility.

## Duplicate branch-head pairs

| Branches | Shared head | PR/dependency observations | Disposition |
|---|---|---|---|
| `feature/cal-candidate-gating-current-main-2026-11-09` and `feature/cal-offer-bound-boundary-2026-11-09` | `dfce1c7d4d4040acd83f7714e830ad7be3e64f5c` | No PR returned by head search. | Duplicate-ref candidate; inspect automation/workflow references before retirement. |
| `integration/privacy-rights-ci-rerun-2026-11-21` and `integration/privacy-rights-current-main-2026-11-21` | `fd89fcbea4931008cefb2e73fc64a85445081935` | PRs #259 and #262 closed unmerged; later privacy work includes merged PR #265. | Likely superseded; preserve until content and workflow dependency checks complete. |
| `security/twin-click-it-policy-ci-rerun-2026-11-21` and `security/twin-click-it-policy-current-main-2026-11-21` | `6c905bd8efa7be7ed8cba4ca9e4821263c3ff110` | PR #261 merged; PR #260 closed unmerged on the same head. | Likely redundant alias; confirm no external dependency before retirement. |

## High-risk diverged families requiring content review

These branches contain substantial commits not reachable from the earlier main snapshot. Do not merge them wholesale; inspect file-level diffs, tests, licenses, service boundaries and current-main equivalents before selective promotion:

- Twin / Try-On / evaluation: `feat/pnelly-runtime-persistent-twin-tryon`, `feature/outfit-evaluation-publication-guards`, `feature/pnelly-outfit-evaluation-benchmark`, `feature/privacy-governance-service`.
- CAL / commerce: `feature/end-to-end-cal-purchase-governance`, `feature/cirvanna-feature-spine`, `feature/commerce-multimarket-offers-rebased`, `feat/shopify-inventory-reservation-saga`.
- Wardrobe / identity / DSI: `feat/daily-look-retention-experiments-v2`, `feature/living-filters-mvp`, `feat/dsi-p0-capture-provenance`, `feature/wardrobe-pnelly-npl-eepl`.
- Retrieval / appearance research: `research/model-competition-and-logic-transfer`, `feature/primal-atelier-living-couture`, `feature/appearance-look-sessions`.

These are examples, not a complete priority list. Their commit counts are not quality scores. Main already contains selected later implementations in several areas; content-level comparison is required to avoid duplicate or regressive promotion.

## Selective branch-review findings

- `feat/pnelly-runtime-persistent-twin-tryon` is 128 ahead / 206 behind main and has no open PR. Its unique diff includes a standalone Twin store that persists a `pose_skeleton_3d` representation. Its persistence tests stub consent verification, asset upload and vision inference; they do not prove real Identity Consent, Asset Service, provider provenance or a validated full-body mesh. The branch explicitly reports `full_surface_mesh_available=false`. Do not merge it wholesale; any useful work must be re-evaluated against the current Twin Registry / Asset Service / independent-validator contract.
- `feature/outfit-evaluation-publication-guards` is 165 ahead / 206 behind and its PR #111 is closed unmerged as superseded by current-main publication and Click It controls. Do not revive the branch without a new gap analysis.
- `feature/end-to-end-cal-purchase-governance` is 119 ahead / 219 behind; PR #62 is closed unmerged. Its historical PR description records missing real evidence/FCI providers, live PostgreSQL deployment and staging checkout proof. Current main has since evolved; do not promote this branch wholesale.
- `feature/commerce-multimarket-offers-rebased` is 85 ahead / 207 behind; PR #102 is closed unmerged. Its contract work is not live provider operation; compare any still-needed details against current main before selective extraction.
- `feature/wardrobe-pnelly-npl-eepl` is 44 ahead / 209 behind; PR #96 is merged. Its Wardrobe/PNELLY work is already integrated; no re-merge is warranted.

## Current PR and release context

- PR #302 is merged. Its provider hold revalidation and Stripe-expiry-safe cleanup changes are on main; its exact-head Commerce, Architecture, Privacy Governance and container-image checks passed.
- PR #303 was closed unmerged after its Architecture secret scan failed. PR #314 is the current scanner retry. Its exact-head Architecture, Commerce, Intelligence and Privacy Governance workflows all passed on `c9e3037c7be5f6b97ee60441935eb0d48b3b394a`. It remains open and has no submitted reviews; it is 10 ahead / 1 behind main. Reconcile the one mainline commit and rerun exact-head checks before merge.
- PR #315 merged at `210e9e370782a13bc69b93286bf8d3cd8ab3cc69`. Its final strict source-lineage audit reported 544 candidates, 519 exact matches, 5 documented syntax repairs, 19 path-specific approved exceptions, 1 trailing-whitespace-only difference, 0 missing source blocks and 0 unresolved content differences. Six archive/snapshot differences remain hash-pinned and documented. The review states the source-lineage subtask is closed on that exact commit; this does not pass the entire REL-01 gate for a release candidate or certify production.
- PR #311's previous branch accumulated conflicting/stale documentation and is being replaced by this clean, current-main-based documentation PR. No production or runtime code changes are included.
- The release ledger still records **23 required gates, all 23 blocked**, with empty evidence references and null verified commits. The source-lineage subtask merge does not change that ledger state.

## Disposition and next actions

1. Preserve diverged heads while performing file-level classification and checking open/closed PRs, workflows, release references and source lineage.
2. For the 68 behind-only heads, verify no external automation or recovery process depends on each ref; then prepare a separate, reviewable archival/deletion plan.
3. Review the three duplicate implementation pairs. Do not delete either side until the superseding implementation and dependency references are confirmed.
4. Configure and independently verify branch protection for `main` under #271.
5. Refresh the full paginated inventory before any destructive ref operation; the repository is actively changing.

**No branch deletion or force-push was performed. All 23 production release gates remain blocked.**
