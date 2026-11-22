# Branch reconciliation — 22 November 2026

Repository: `cirvannaco-png/Cirvanna-demo`  
Comparison base: `main` at `81580b26034e0cf424172d5b96eead4a1c22f840`.

## Inventory and method

Paginated GitHub branch search returned **261 refs including main**, so 260 non-main branches were compared against the exact main SHA. All 260 comparisons returned successfully. Exactly one non-main branch is strictly ahead-only: `integration/appearance-specialist-current-main-v2` (30 ahead, 0 behind), the head of PR #269. No non-main branch is identical to main. The other 259 are either behind-only or diverged.

A diverged branch is not a merge recommendation. Squash-merged branches can appear ahead because their original commits are not ancestors of the squash commit. Many older branches are hundreds of commits behind and contain no unique commits. No mass merge, force-push or deletion was performed.

## Canonical dispositions

| Workstream | Current-main evidence | Decision |
|---|---|---|
| Shopify | #242 and #243 merged; #254 merged. #243 exact-head workflows 4/4 pass; #254 workflows 6/6 pass. | Do not merge old Shopify branches or closed PRs #245/#247/#248/#251. Live Shopify/Stripe operations and PostgreSQL restore remain release gates. |
| PNELLY + Wardrobe | #197 merged; 7/7 workflows pass. Authenticated wardrobe-aware discovery, three daily-look roles, Complementer advisory, saved outfits and explicit feedback contracts exist. | USI profile + current-consent TAL wardrobe like/wear signals and NPL vetoes feed code-level recommendation paths. Complementer reaction TAL events are not yet shown to affect ranking. Production Wardrobe PostgreSQL, asset-deletion worker and real-user end-to-end validation remain incomplete. |
| CAL | #196 merged; #266 merged with exact product/catalog-version/CIL/policy binding; #266 workflows 5/5 pass. | Code-level display and candidate-bound purchase gates exist. Real staging route-coverage and purchase receipt evidence remain missing. |
| Click It / Look It | #255, #261 and #265 merged; relevant workflows pass. Look It uses request-scoped consent; Click It BFF rejects before multipart parsing. | Click It remains disabled pending detector evaluation, independent attestation, publication/restore/CDN route proof and deletion evidence. |
| Twin / Try-On | #249 and #250 merged; #249 workflows 7/7; #250 workflows 3/3. | SAM 3D Body is research-only and not connected to public Twin/Asset/Registry. BFF reports `try_on_available=false`; FASHN is flat-lay-only pending GPU/visual acceptance. |
| Multi-market | #239/#244 and follow-up commerce changes merged. Versioned FX/tax/fulfilment/payment evidence contracts exist. | No live KYC or fulfilment vendor is connected; Stripe/card only, no completed seller payouts or provider-booked shipments. |
| Production | `docs/release/release-gates.json`: 23 required gates, 23 blocked, no exact-release-commit evidence. | No production promotion based on CI alone. |

## High-risk divergent families — do not merge wholesale

- PNELLY/Twin: `feat/pnelly-runtime-persistent-twin-tryon` (128 ahead / 167 behind), `integration/current-main-pnelly-cil-gates-2026-11-12-v2` (125 / 60), `feature/outfit-evaluation-publication-guards` (165 / 167), `feature/pnelly-outfit-evaluation-benchmark` (163 / 167).
- CAL/commerce: `feature/end-to-end-cal-purchase-governance` (119 / 180), `feature/cirvanna-feature-spine` (101 / 184), `feature/commerce-multimarket-offers-rebased` (85 / 168), `feat/shopify-inventory-reservation-saga` (63 / 28).
- Privacy/media: `feature/privacy-governance-service` (154 / 167), `reconcile/privacy-publication-gate-hardening-2026-11-08` (172 / 167), `feature/twin-clickit-live-inference` (61 / 181).
- DSI capture/calibration branches remain research candidates until representative consented evaluation and independent calibration evidence exist.

These are graph counts, not quality scores or proof that code is absent from main. Inspect file-level behavior and tests before selectively porting commits.

## Open PRs and branch retention

- #269 is the current-main appearance-specialist/orchestrator candidate; 8/8 exact-head workflows pass, final review still required.
- #267 was closed as a duplicate/superseded base for #269.
- #206 remains an evidence-led DermalSight research roadmap, not production implementation.
- #67 is an older intelligent-marketplace-filter PR and needs explicit compatibility/supersession review.
- Keep main, open-PR heads, active dependencies and unique source material. Behind-only branches are archival candidates only after dependency, PR and source-lineage checks.
- No branch was deleted or rewritten.

## Limitations

This is a repository-level graph and implementation review, not a third-party penetration test, live deployment certification, external CDN/cache deletion proof or real GPU quality evaluation.
