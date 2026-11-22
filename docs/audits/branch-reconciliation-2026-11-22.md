# Branch reconciliation — 22 November 2026

Repository: `cirvannaco-png/Cirvanna-demo`  
Reviewed code main before this documentation PR: `81df302848468f1e744252e435cbbd75d579b7f3`. Prior audit main: `eca1a7349daef730a9e1ac43c72fec91712cb8b8`. Original code comparison base: `81580b26034e0cf424172d5b96eead4a1c22f840`.

## Inventory and method

Paginated GitHub branch search now returns **268 refs including main** (267 non-main). The prior audit covered 263 refs including main (262 non-main). Four implementation/research refs were created after that audit; this documentation-audit branch is the fifth new ref. Main advanced by six commits from `eca1a7349daef730a9e1ac43c72fec91712cb8b8` to `81df302848468f1e744252e435cbbd75d579b7f3`: appearance-specialist orchestration (#269), audit refresh (#274), private benchmark artifact-write hardening (#275), CAL checkout regression coverage (#276), the hash-locked CPU retrieval research environment (#277), and PNELLY/Wardrobe Complementer feedback-to-TAL integration (#278).

For the 260 original non-main refs compared against `81580b26034e0cf424172d5b96eead4a1c22f840`, ahead counts remain unchanged and behind counts are now eight greater than that original comparison (two intervening audit-only main commits to `eca1...`, plus six subsequent main commits). The two audit branches previously compared directly against `eca1...` have six additional behind commits. Four new implementation/research refs were compared directly against current main:
- `security/private-benchmark-artifact-writes`: 1 ahead / 4 behind (merged PR #275).
- `test/cal-display-checkout-regression-matrix-2026-11-22`: 5 ahead / 4 behind (merged PR #276).
- `research/fashion-retrieval-hashed-lock`: 1 ahead / 3 behind (merged PR #277).
- `feature/pnelly-wardrobe-complementer-feedback-2026-11-22`: 3 ahead / 3 behind (merged PR #278).

The appearance-specialist branch `integration/appearance-specialist-current-main-v2` is 30 ahead / 8 behind after PR #269 merged. The new documentation-audit branch `docs/update-267-branch-audit-and-readme-2026-11-22` is the only ahead-only ref because it was created directly from the reviewed main to carry this audit; it is not an implementation branch. Squash-merged branches can remain graph-diverged because their original commits are not ancestors of the squash commit. No non-main ref is identical to the reviewed code main. A diverged branch is not a merge recommendation; graph counts are not quality scores. No mass merge, force-push or branch deletion was performed.

## Canonical dispositions

| Workstream | Current-main evidence | Decision |
|---|---|---|
| Shopify | #242 and #243 merged; #254 merged. #243 exact-head workflows 4/4 pass; #254 workflows 6/6 pass. | Do not merge old Shopify branches or closed PRs #245/#247/#248/#251. Live Shopify/Stripe operations and PostgreSQL restore remain release gates. |
| PNELLY + Wardrobe | #197 and #278 merged; #278 exact-head workflows 6/6 pass. Authenticated wardrobe-aware discovery, three daily-look roles, Complementer advisory, saved outfits and explicit, idempotent Complementer reaction events to TAL exist. | USI profile + current-consent TAL wardrobe like/wear signals and NPL vetoes feed code-level recommendation paths. Complementer reaction events are persisted but are not yet shown to affect ranking. Production Wardrobe PostgreSQL, asset-deletion worker and real-user end-to-end validation remain incomplete. |
| CAL | #196 and #266 merged; #276 adds expired-receipt, offer-mutation race and wrong-subject receipt regression coverage; #276 workflows 6/6 pass. | Code-level display and candidate-bound purchase gates exist. Real staging route-coverage and purchase receipt evidence remain missing. |
| Click It / Look It | #255, #261 and #265 merged; relevant workflows pass. Look It uses request-scoped consent; Click It BFF rejects before multipart parsing. | Click It remains disabled pending detector evaluation, independent attestation, publication/restore/CDN route proof and deletion evidence. |
| Twin / Try-On | #249 and #250 merged; #249 workflows 7/7; #250 workflows 3/3. | SAM 3D Body is research-only and not connected to public Twin/Asset/Registry. BFF reports `try_on_available=false`; FASHN is flat-lay-only pending GPU/visual acceptance. |
| Multi-market | #239/#244 and follow-up commerce changes merged. Versioned FX/tax/fulfilment/payment evidence contracts exist. | No live KYC or fulfilment vendor is connected; Stripe/card only, no completed seller payouts or provider-booked shipments. |
| Retrieval research | #277 merged; exact-head Architecture validation and Twin worker contract workflows 2/2 pass. A hash-locked CPython 3.11 Linux x86_64 CPU environment is available for controlled retrieval research. | CPU lock is not a CUDA/GPU environment, model inference validation or production deployment. |
| Production | `docs/release/release-gates.json`: 23 required gates, 23 blocked, no exact-release-commit evidence. | No production promotion based on CI alone. |

## High-risk divergent families — do not merge wholesale

- PNELLY/Twin: `feat/pnelly-runtime-persistent-twin-tryon` (128 ahead / 167 behind), `integration/current-main-pnelly-cil-gates-2026-11-12-v2` (125 / 60), `feature/outfit-evaluation-publication-guards` (165 / 167), `feature/pnelly-outfit-evaluation-benchmark` (163 / 167).
- CAL/commerce: `feature/end-to-end-cal-purchase-governance` (119 / 180), `feature/cirvanna-feature-spine` (101 / 184), `feature/commerce-multimarket-offers-rebased` (85 / 168), `feat/shopify-inventory-reservation-saga` (63 / 28).
- Privacy/media: `feature/privacy-governance-service` (154 / 167), `reconcile/privacy-publication-gate-hardening-2026-11-08` (172 / 167), `feature/twin-clickit-live-inference` (61 / 181).
- DSI capture/calibration branches remain research candidates until representative consented evaluation and independent calibration evidence exist.

These are graph counts, not quality scores or proof that code is absent from main. Inspect file-level behavior and tests before selectively porting commits.

## Open PRs and branch retention

- #269 is merged; its retained branch is 30 ahead / 8 behind after squash merge. Exact-head CI passed 8/8.
- #267 was closed as a duplicate/superseded base for #269.
- #206 remains an evidence-led DermalSight research roadmap, not production implementation; its branch is 3 ahead / 63 behind and the PR remains open for selective documentation port or closure.
- #67 is an older intelligent-marketplace-filter PR; its branch is 11 ahead / 186 behind and the PR is not mergeable. Current main has the authenticated CAL-governed marketplace path but not every legacy filter in #67. Preserve it as a source candidate; port only compatible server-side filters after contract and CAL review.\n- #279 carries this refreshed documentation audit; its head is based directly on the reviewed main and is the only ahead-only documentation ref in this inventory.
- Keep main, open-PR heads, active dependencies and unique source material. Behind-only branches are archival candidates only after dependency, PR and source-lineage checks.
- No branch was deleted or rewritten.

## Limitations

This is a repository-level graph and implementation review, not a third-party penetration test, live deployment certification, external CDN/cache deletion proof or real GPU quality evaluation.
