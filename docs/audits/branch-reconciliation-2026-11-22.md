# Branch reconciliation — 22 November 2026

## Snapshot and method

- Repository: `cirvannaco-png/Cirvanna-demo`
- Comparison base: `main` at `81580b26034e0cf424172d5b96eead4a1c22f840`
- Paginated branch inventory: **261 refs total**, including `main`; **260 non-main branches**.
- Each non-main branch was compared to the exact main SHA with GitHub's commit comparison endpoint.
- All 260 comparisons returned successfully. No ref was force-updated or deleted during this pass.

## Graph-level results

- Exactly one non-main branch is strictly ahead of main with no behind commits: `integration/appearance-specialist-current-main-v2` (30 ahead, 0 behind). It is the head of PR #269.
- No non-main branch is identical to main.
- The remaining 259 branches are either behind-only or diverged. A diverged graph is not a merge recommendation: squash-merged branches may appear ahead because their original commits are not ancestors of the squash commit.
- Many older branches are hundreds of commits behind main and contain no unique commits. They are archive candidates, not integration candidates.
- No bulk merge, force-push, or deletion was performed. This preserves source history and prevents old service boundaries, stale policy contracts, and duplicated migrations from re-entering main.

## Canonical dispositions

| Workstream | Current-main evidence | Disposition |
|---|---|---|
| Shopify compensation and catalogue sync | #242 and #243 merged; #254 merged as the current-main compensation/catalogue/Wardrobe reconciliation. PR #243 exact-head workflows: Commerce, Privacy Governance, Architecture and Container Image Builds — all passed. PR #254 exact-head workflows: Sync Worker, Wardrobe Persistence, Commerce, Privacy Governance, Architecture and Container Image Builds — all passed. | Do not merge old Shopify branches or closed PRs #245/#247/#248/#251. #243 is already complete and merged; live Shopify/Stripe operations and PostgreSQL restore remain release gates. |
| PNELLY + Wardrobe | #197 merged; its seven exact-head workflows passed. Current BFF exposes wardrobe-aware conversational discovery, three daily-look roles, Complementer advisory, saved outfits and explicit wear/dislike feedback. | The integration foundation is present. Durable cross-session learning/ranking, live provider hydration, production Wardrobe PostgreSQL, object-store deletion worker and end-to-end deployed identity/consent acceptance remain incomplete. |
| CAL and purchase authorization | #196 merged; #266 merged with exact product/catalog-version/CIL/policy binding. #266's five exact-head workflows passed. BFF cart/checkout proxy is default-off and requires live Commerce readiness/capability checks and candidate-bound purchase receipts. | Do not merge old CAL candidate-binding branches wholesale. Code-level gates exist; full staging route-coverage and real purchase/receipt evidence remain required. |
| Click It and Look It | #255, #261 and #265 merged; exact-head workflows passed. Look It is a separate request-scoped consent flow. Click It BFF rejects with 503 before multipart parsing. | Click It remains disabled. No independent masking/false-negative evaluation, deployed attestation, full publication/restore/CDN route proof, or deletion-propagation evidence is recorded. |
| Virtual Twin and Try-On | #249 and #250 merged. #249's seven exact-head workflows passed; #250's worker/architecture/privacy workflows passed. | #250 is research-only and not connected to public Twin/Asset/Registry. BFF reports `try_on_available=false`; the current Twin journey does not provide persistent customer reconstruction. FASHN is flat-lay-only pending GPU and visual-quality acceptance. |
| Multi-market commerce | #239/#244 and later commerce work are merged; provider evidence contracts and market activation checks exist. | FX/tax/fulfilment/payment records are not proof of live providers. Merchant KYC, carrier booking/tracking, seller payouts, live market acceptance and quote-bound staging checkout remain blocked. |
| Production readiness | `docs/release/release-gates.json` contains 23 required gates; the current registry has 23/23 blocked and no exact-release-commit evidence references. | No production promotion, public Click It/Twin enablement or checkout switch-on based only on CI. |

## High-risk branch families: do not merge wholesale

The current graph comparison highlights large divergent histories in the feature families below. These branches must be treated as source material and compared semantically against current ownership/contracts; they are not safe merge candidates simply because they contain useful commits.

- PNELLY/Twin: `feat/pnelly-runtime-persistent-twin-tryon` (128 ahead / 167 behind), `integration/current-main-pnelly-cil-gates-2026-11-12-v2` (125 / 60), `feature/outfit-evaluation-publication-guards` (165 / 167), `feature/pnelly-outfit-evaluation-benchmark` (163 / 167).
- CAL/commerce: `feature/end-to-end-cal-purchase-governance` (119 / 180), `feature/cirvanna-feature-spine` (101 / 184), `feature/commerce-multimarket-offers-rebased` (85 / 168), `feat/shopify-inventory-reservation-saga` (63 / 28).
- Privacy/media: `feature/privacy-governance-service` (154 / 167), `reconcile/privacy-publication-gate-hardening-2026-11-08` (172 / 167), `feature/twin-clickit-live-inference` (61 / 181).
- DSI: the capture, calibration and DermalSight branches remain research candidates until consented, representative, independently reviewed validation and deployment evidence exists.

The comparison numbers above are branch graph counts, not quality scores or proof that the implementation is absent from main. Merged PRs use squash commits in several places; compare file-level behavior and tests before porting.

## Open PR reconciliation

- #269 is the current-main appearance-specialist/orchestrator candidate. Its eight exact-head workflows passed. It is the only strictly-ahead non-main branch in this snapshot. It still requires final review before merge.
- #267 was closed as a duplicate/superseded base for #269. It carried the same specialist implementation files but targeted an older main SHA.
- #206 remains an evidence-led DermalSight research roadmap; it is not production implementation.
- #67 remains an older intelligent-marketplace-filter PR and needs explicit supersession/compatibility review before any merge.

## Retention policy

1. Keep `main`, open-PR heads, active dependency branches and branches containing unique source material.
2. Port useful commits selectively onto a fresh branch from current main; rerun exact-head tests and review dependency/migration/authorization changes.
3. Treat behind-only branches as archive candidates only after checking open PRs, branch dependencies and source-lineage references.
4. Close duplicate PRs only when the replacement PR has the verified superset diff and current base.
5. Preserve historical branches until the owner explicitly approves archival/deletion. This audit did not delete or rewrite any branch.

## Limitations

This is a repository-level graph and implementation review, not a third-party audit. It does not prove live provider operation, customer-data safety in deployed infrastructure, external CDN/cache deletion, real GPU output quality, or production disaster recovery. Those require environment evidence and independent assessors.
