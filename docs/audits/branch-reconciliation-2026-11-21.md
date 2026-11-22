> **Superseded on 22 November 2026.** The repository now has 261 refs and all 260 non-main branches have been compared against current main. Use [the 22 November reconciliation](branch-reconciliation-2026-11-22.md) for the current inventory and [the independent regression/security/deployment audit](independent-regression-security-deployment-audit-2026-11-22.md) for current release findings. The historical 21 November counts below are retained for provenance only.

# Branch reconciliation audit — current main, 21 November 2026

## Current snapshot

- Repository: `cirvannaco-png/Cirvanna-demo`
- Current comparison base: `c97e9ff2f8bb5734b37693367672015e6a32af91`
- Current branch inventory: **255 unique refs, including `main`**.
- Inventory method: paginated GitHub branch search across all returned pages.
- No branch was deleted or force-updated during this reconciliation.

**Important accuracy note:** the last complete commit-graph comparison was performed against the earlier `c09ce323c6dc7f5a9e02a9021896ec87bc430440` main snapshot and covered 253 refs. Its graph counts below are historical, not a fresh classification of all 255 current refs. Four subsequently-created work branches were individually compared against the current main before their replacement PRs were merged/closed. A complete 255-ref graph comparison against `c97e9ff` remains outstanding; do not treat the historical graph counts as current.

## Historical graph baseline — 253 refs against `c09ce32`

| Classification | Count | Interpretation |
|---|---:|---|
| Diverged | 179 | Both branch and main contain commits absent from the other. Requires semantic diff and dependency review; never merge wholesale. |
| Behind only | 71 | No unique commits ahead of main. Candidate for archival only after open-PR, dependency, and source-material checks. |
| Ahead only | 2 | Strictly ahead of main with no commits behind at that snapshot. |
| Identical | 1 | The `main` branch compared with itself. |
| **Total** | **253** | Complete for the historical 253-ref snapshot only. |

The historical ahead-only branches were `security/twin-click-it-policy-current-main-2026-11-21` and the historical audit branch. The policy implementation was later merged through PR #261; its original branch is now graph-diverged from the squash merge, which is expected and is not evidence that the code is missing.

## New-branch comparisons against current main

These four later branches were compared individually against current main (`c97e9ff`):

| Branch | Ahead | Behind | Disposition |
|---|---:|---:|---|
| `security/twin-click-it-policy-ci-rerun-2026-11-21` | 9 | 3 | Superseded by merged PR #261 |
| `integration/privacy-rights-ci-rerun-2026-11-21` | 4 | 5 | Superseded by merged PR #265 |
| `integration/privacy-rights-current-main-after-policy-2026-11-21` | 2 | 2 | Merged through PR #265; squash divergence is historical |
| `fix/cal-marketplace-candidate-binding-current-main-v2` | 4 | 1 | Merged through PR #266; squash divergence is historical |

## Canonical workstream dispositions

| Workstream | Current disposition | Reconciliation rule |
|---|---|---|
| Shopify compensation and catalogue sync | PRs #242 and #243 merged; current-main remediation/consolidation PR #254 merged. | Do not merge old stacked branches #245, #247, #248 or #251. Use current main; exact-head commerce, sync, Wardrobe and image-build checks passed for #254. Live development-store operations, Stripe refunds and PostgreSQL restore remain external release gates. |
| Commerce market activation and fulfilment precision | PR #239 and follow-up PR #244 merged. | Provider-evidence checks, market ownership and fulfilment-distance precision are in current main. Real provider coverage and shipment execution remain unverified. |
| PNELLY + Wardrobe | PR #197 merged; exact-head Marketplace, Privacy, Decision Gateway, Appearance, architecture and image-build workflows passed. | Current main contains authenticated wardrobe-aware discovery, bounded conversation context, Complementer advisory, three daily looks/rotation and consent-aware feedback. Do not remerge stale PNELLY branches. Production cohort evaluation and live identity/wardrobe operations remain outstanding. |
| CAL feedback and purchase authorization | PR #196 and checkout/purchase receipt work in #192/#222 are merged; PR #266 adds exact BFF candidate/product-version/CIL/policy-contract validation. | Only CAL SHOW with exact candidate/product/catalog-version binding and eligible CIL state may cross the marketplace display boundary. Checkout still requires fresh subject/action/offer-snapshot-bound purchase receipts and staging verification. |
| Virtual Try-On | PR #249 merged; FASHN VTON 1.5 is restricted to segmentation-free person images and flat-lay garments. | Model-worn garment photos remain rejected because the Human Parser/SegFormer dependency is not commercially cleared. Real GPU/model-weight inference, visual-quality cohort evaluation and deployed consent/asset integration remain unverified. |
| Virtual Twin | PR #250 merged as a research-only SAM 3D Body worker. | The worker is not connected to the public Virtual Twin API, Asset Service or Twin Registry. Persistent generation, calibrated measurements, independent body coverage/scale/privacy validation and customer Try-On remain disabled. |
| Look It privacy | PR #255 merged. | Request-scoped image-processing and Look It consent revocation is in current main. Look It remains distinct from Click It and returns no product/merchant/price/image detail before CAL SHOW. |
| Click It privacy | PR #261 merged the jurisdiction-aware policy gate; PR #265 merged purpose-bound consent, revocation and photographed-person rights intake. | The BFF still rejects Click It before multipart parsing. Do not enable it until pinned detector/runtime, independent masking attestation, full publication/restore/share route coverage, rights quarantine/deletion and independent staging verification pass. |
| CIL provider consent cleanup | PR #253 merged; its exact-head Identity Learning, Intelligence, Decision Gateway, privacy and image-build workflows passed. | Durable provider revocation cleanup, expiry and stale-retry protection are on current main. Live provider deletion acceptance and PostgreSQL restore evidence remain external. |
| Production readiness | PRs #202 and #204 closed as superseded by the current release ledger and updated operational/provider specifications. PR #206 remains an open evidence-led DermalSight roadmap. | The 23 required release gates remain blocked. Code, CI, provider mocks and templates do not prove live identity, managed database restore, payment, provider operations, independent privacy, model quality or rollback/on-call readiness. |

## Superseded PR handling

- Merged: #185, #186, #192, #196, #197, #219, #222, #228, #235, #239, #242, #243, #244, #249, #250, #253, #254, #255, #261, #265 and #266.
- Closed as superseded/redundant: #84, #107, #111, #174, #182, #202, #204, #245, #247, #248, #251, #256, #257, #258, #259, #260, #262 and #264.
- #263 is the earlier audit PR and should be replaced by this refreshed report after review. PR #206 remains open for DSI research; other active work must be checked against the current open-PR list.
- A squash-merged branch can still compare as diverged because its original commits are not ancestors of the squash commit. Treat that as historical graph divergence, not evidence that its implementation is missing.

## High-risk semantic branch review

The following branches were inspected and should not be merged wholesale:

1. `feat/pnelly-runtime-persistent-twin-tryon`: 128 commits ahead and 164 behind current main; 36 changed files. Its history spans obsolete service ownership and stale BFF/Twin/consent contracts. Current PNELLY, Wardrobe, Twin Registry, Asset Service and VTON paths are newer and separately owned.
2. `feat/pnelly-runtime-twin-vton-integration`: 8 ahead, 161 behind; its old Xari/PNELLY identity and BFF changes are superseded by canonical PNELLY routes and PR #197.
3. `feature/twin-clickit-live-inference`: 61 ahead, 178 behind. Its Virtual Twin Click It route predates the current jurisdiction-aware policy gate and must not bypass the BFF's pre-read disabled boundary.
4. `feat/virtual-twin-registry-current-main`: 8 ahead, 143 behind. It places registry code under the old Virtual Twin service boundary; current main assigns persistent metadata to the separate `services/twin-registry` service.
5. `fix/vton-worker-real-readiness-current-main`: 9 ahead, 131 behind. It proposes re-enabling model-worn garment mode through a boolean parser-license environment flag. That is weaker than a digest-bound, independently evidenced commercial license approval; current main's maskless flat-lay-only mode is safer. Do not port the boolean gate or model-worn path.
6. CAL/multi-market feature branches such as `feature/end-to-end-cal-purchase-governance`, `feature/cal-bound-cart-checkout-authorization-2026-11-10`, `feature/commerce-multimarket-offers-rebased` and `feat/multi-market-commerce-current-main` must be compared semantically against merged #184, #192, #196, #222, #239, #244, #254 and #266 before any further port.
7. DSI branches remain research candidates; do not treat capture or color-calibration branches as validated skin/fit providers without a consented, representative human-reviewed evaluation and independent calibration evidence.

## Retention and deletion policy

- Keep `main`, every open-PR head, active dependency branches and branches with unique unreviewed source material.
- Forward-port useful diverged commits selectively. Do not merge old branch histories wholesale.
- Mark behind-only branches as archive candidates only after checking all open PRs, dependent branches and source-lineage references.
- Close duplicate PRs only after the replacement is merged and the replacement diff is verified.
- Do not delete branches as part of this audit. No branch was deleted or force-updated.

## Remaining limitation

The current inventory is 255 refs, but the complete graph comparison is still the historical 253-ref snapshot against `c09ce32`. Four new work branches were individually compared against `c97e9ff`; a full current-main comparison of all 255 refs and semantic review of all remaining divergent histories are not complete. The next work is feature-family review and safe archival, not mass merge or mass deletion.
