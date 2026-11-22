# Branch reconciliation — 22 November 2026 (graph pass)

Repository: `cirvannaco-png/Cirvanna-demo`  
Reviewed main: `029d96637023b2e120619c7ab3219bdb4a0aa3cd`  
Method: GitHub's paginated branch-ref inventory and commit-ancestry comparisons. This is a graph-level audit, not a code-quality review of every diverged branch.

## Inventory

- **300 branch refs** total, including `main` (299 non-main refs).
- **296 unique commit heads** across those refs.
- Three actual duplicate-head pairs are present; this reduces the unique head count by three. The audit branch created for this report also points at the same commit as `main`, so it is a deliberate temporary alias rather than a duplicate implementation.
- **295 unique non-main commit heads**.
- `main` currently reports `protected: false`. Required PR/review/check enforcement remains an administrator blocker tracked by [#271](https://github.com/cirvannaco-png/Cirvanna-demo/issues/271).

## Ancestry classification

A complete comparison was performed for the original 290 unique non-main heads against main at `74e153dfbc2911770670ec171ad2b31092047b8b`: 223 were diverged and 67 were behind-only. Main subsequently advanced through the Shopify reservation fix (#302), its documentation follow-up (#307), and the combined cross-service evidence clarification (#310). Those three mainline commits post-date the original branch-head snapshot; none of the original branch heads contains those later mainline commits, so their status classes remain unchanged and their behind counts increase by three.

Five additional unique PR branch heads were then compared against the later mainline snapshots:
- PR #305 branch: 1 ahead / 5 behind; merged.
- PR #306 branch: 4 ahead / 4 behind; closed unmerged.
- PR #307 branch: 3 ahead / 1 behind; merged.
- PR #308 branch: 5 ahead / 1 behind at the comparison snapshot; open.
- PR #310 branch: 1 ahead / 1 behind; merged.

The combined current classification is therefore **228 diverged** and **67 behind-only** across 295 unique non-main heads. A behind-only branch contains no commit absent from main; it is an archival/deletion candidate, not an automatic deletion. A diverged branch may contain useful work, already-squash-merged work, superseded work, or unsafe/obsolete code. Ahead/behind counts alone do not determine merge or deletion eligibility.

## Duplicate branch-head pairs

| Branches | Shared head | PR/dependency observations | Disposition |
|---|---|---|---|
| `feature/cal-candidate-gating-current-main-2026-11-09` and `feature/cal-offer-bound-boundary-2026-11-09` | `dfce1c7d4d4040acd83f7714e830ad7be3e64f5c` | No PR returned by head search. | Duplicate-ref candidate; inspect automation/workflow references before retirement. |
| `integration/privacy-rights-ci-rerun-2026-11-21` and `integration/privacy-rights-current-main-2026-11-21` | `fd89fcbea4931008cefb2e73fc64a85445081935` | PRs #259 and #262 both closed unmerged; later privacy work includes merged PR #265. | Likely superseded; preserve until content and workflow dependency checks complete. |
| `security/twin-click-it-policy-ci-rerun-2026-11-21` and `security/twin-click-it-policy-current-main-2026-11-21` | `6c905bd8efa7be7ed8cba4ca9e4821263c3ff110` | PR #261 merged; PR #260 closed unmerged on the same head. | Likely redundant alias; confirm no external dependency before retirement. |

## High-risk diverged families requiring content review

The following branches contain substantial commits not reachable from current main. They must not be merged wholesale; inspect their file-level diffs, tests, licenses, service boundaries and current-main equivalents before selective promotion:

- Twin / Try-On / evaluation: `feat/pnelly-runtime-persistent-twin-tryon` (128 ahead at the original comparison), `feature/outfit-evaluation-publication-guards` (165), `feature/pnelly-outfit-evaluation-benchmark` (163), `feature/privacy-governance-service` (154).
- CAL / commerce: `feature/end-to-end-cal-purchase-governance` (119), `feature/cirvanna-feature-spine` (101), `feature/commerce-multimarket-offers-rebased` (85), `feat/shopify-inventory-reservation-saga` (63).
- Wardrobe / identity / DSI: `feat/daily-look-retention-experiments-v2` (118), `feature/living-filters-mvp` (96), `feat/dsi-p0-capture-provenance` (60), `feature/wardrobe-pnelly-npl-eepl` (44).
- Retrieval / appearance research: `research/model-competition-and-logic-transfer` (107), `feature/primal-atelier-living-couture` (94), `feature/appearance-look-sessions` (97).

These are examples of high-ahead branches, not a complete priority list. Their commit counts are not quality scores. Main already contains selected later implementations in several of these areas; content-level comparison is still required to avoid duplicate or regressive promotion.

## Current PR and release context

- PR #302 is merged. Its provider hold revalidation and Stripe-expiry-safe cleanup changes are on main; its exact-head Commerce, Architecture, Privacy Governance and container-image checks passed.
- PR #303 remains open with a failed Architecture secret scan. The expanded broker-URI matcher exposed legacy candidate/intake defaults; additional review found that driver-qualified SQLAlchemy URIs such as `postgresql+asyncpg://` also need coverage. Do not weaken the scanner to obtain green CI.
- PR #308 is open for source-lineage header reconciliation. PR #306 was closed unmerged; PRs #305, #307 and #310 were merged documentation changes.
- The production release ledger still records **23 required gates, all 23 blocked**. This graph audit does not change production readiness.

## Disposition and next actions

1. Preserve all 229 diverged heads while performing file-level classification and checking open/closed PRs, workflows, release references and unique source lineage.
2. For the 66 behind-only heads, verify no external automation or recovery process depends on the ref; then prepare a separate, reviewable archival/deletion plan.
3. Review the three duplicate implementation pairs. Do not delete either side until the superseding implementation and dependency references are confirmed.
4. Configure and independently verify branch protection for `main` under #271.
5. Refresh this inventory before any destructive ref operation; the repository is actively changing.

**No branch was deleted, force-pushed, or merged as part of this audit.**