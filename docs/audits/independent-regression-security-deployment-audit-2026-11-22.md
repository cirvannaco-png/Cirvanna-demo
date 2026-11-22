# Independent regression, security and deployment review — 22 November 2026

Reviewed repository: `cirvannaco-png/Cirvanna-demo`  
Reviewed code main before this documentation PR: `81df302848468f1e744252e435cbbd75d579b7f3`. The reviewed code now includes six mainline commits since `eca1a7349daef730a9e1ac43c72fec91712cb8b8`, including appearance orchestration, private benchmark artifact hardening, CAL checkout regression coverage, the hash-locked CPU research environment and PNELLY/Wardrobe Complementer feedback integration.

The companion branch inventory now records 268 refs including main (267 non-main), with the four post-audit implementation/research branches compared directly to the reviewed code main and this documentation branch identified separately.\n\nThis is a cross-workstream review of code contracts, merged PRs, CI evidence, service READMEs, runbooks and release-gate state. It is not a third-party penetration test, external privacy assessment, live deployment certification or real-customer acceptance study.

## Regression evidence

| PR | Scope | Recorded exact-head CI |
|---|---|---:|
| #197 | PNELLY + Wardrobe | 7/7 successful |
| #196 | CAL feedback/purchase contracts | 6/6 successful |
| #243 | Shopify catalogue sync | 4/4 successful |
| #254 | Shopify/Wardrobe reconciliation | 6/6 successful |
| #266 | CAL candidate/catalog-version/CIL binding | 5/5 successful |
| #255 | Look It consent revocation | 5/5 successful |
| #261 | Click It jurisdiction-aware fail-closed policy | All unique workflows successful |
| #265 | Click It consent and image-rights lifecycle | 5/5 successful |
| #253 | CIL provider-consent revocation | 7/7 successful |
| #249 | FASHN flat-lay VTON contract | 7/7 successful |
| #250 | Research-only SAM 3D Body worker | 3/3 successful |
| #269 | Appearance specialist/orchestrator orchestration | 8/8 successful; merged |
| #275 | Private benchmark artifact-write hardening | 3/3 successful runs |
| #276 | CAL display/checkout regression matrix | 6/6 successful |
| #277 | Hash-locked CPU fashion-retrieval research environment | 2/2 successful |
| #278 | Wardrobe Complementer feedback-to-TAL UI integration | 6/6 successful |

No unresolved inline review threads were found on #243, #254, #266, #265, #261, #255, #253, #269, #275, #276, #277 or #278. PR #278 was merged after its six exact-head workflows passed. CI validates automated contracts/builds, not live provider or deployment behavior.

## Findings

### PNELLY + Wardrobe
Authenticated wardrobe-aware discovery, three daily-look roles, Complementer advisory, saved outfits, editing and consent-gated feedback contracts exist. The API Gateway reads the verified user's USI style profile, applies NPL hard vetoes to wardrobe items, and loads current-consent, unexpired TAL wardrobe like/wear events as bounded positive ranking signals. Wardrobe feedback is durably recorded through the Wardrobe → Identity Learning/TAL and NPL integration with idempotency and retry state. Complementer itself remains advisory-only. PR #278 adds user-visible Helpful/Not for me controls that require active style-learning consent and persist only a minimal idempotent reaction event to TAL; it does not store the raw look text. The current ranking consumer specifically reads wardrobe like/wear events and USI profile preferences, so no evidence shows Complementer reaction events independently changing future ranking. The Recommendation Service's own README correctly limits its responsibility: it is not the durable profile owner.

Wardrobe production PostgreSQL, live asset-deletion worker/retry/DLQ and deployed identity/consent acceptance remain unverified. Browser photo entry remains text-only. No staging evidence or cohort study demonstrates the complete loop for real users or quantifies the effect of each feedback source.

**Decision:** the core USI/TAL/NPL-to-wardrobe recommendation loop is implemented at code/contract level; production deployment and real-user end-to-end validation remain incomplete.

### CAL display and checkout
PR #266 binds displayed candidates to exact product/catalog version, CIL eligibility and policy/arbitration versions. PR #276 adds regression tests for expired CAL purchase receipts, offer mutation during the CAL round-trip, wrong-subject signed receipts and BLOCK/REVIEW decisions. Non-SHOW results are intended to be withheld. BFF cart/checkout proxy is default-off and requires live Commerce readiness/capability checks plus candidate-bound purchase receipts.

Staging acceptance against real Commerce + Decision Gateway has not been evidenced. Every deployed product/media route, alternate surface, cached asset, shared link and checkout path has not been independently exercised against the same CAL policy.

**Decision:** code-level authorization boundary and expanded regression matrix present; complete deployed route coverage and live checkout acceptance remain unproven. Keep the purchase switch off until staging evidence passes.

### Virtual Twin and Try-On
PR #250 adds a gated research-only SAM 3D Body worker; it is not integrated with public Twin API, Asset Service or Twin Registry. The BFF capability contract reports `try_on_available=false`; persistent customer reconstruction is not available. PR #249 enables FASHN only for maskless flat-lay garments. GPU smoke tests, visual-quality evaluation, independent mesh/anatomical validation, calibrated measurements and representative human evaluation are absent.

**Decision:** not complete. Do not advertise persistent Twin generation, calibrated measurements or production Try-On.

### Click It and Look It
Look It is a separate, short-lived request/resource-bound consent flow; PNELLY rechecks consent and BFF revokes the bundle, suppressing results if cleanup fails. Click It has jurisdiction and photographed-person rights contracts, but the BFF returns private no-store 503 before multipart parsing while masking is unreleased.

No independent detector false-negative evaluation, deployed masking attestation, verified jurisdiction/guardian/requester/content-lifecycle providers, full publication/restore/CDN/shared-link route inspection or external deletion propagation evidence is recorded.

**Decision:** Look It guarded flow implemented; Click It remains disabled.

### Multi-market commerce and Shopify
Versioned FX/tax/fulfilment/payment evidence, market activation validation and quote freshness contracts exist. Shopify compensation, catalogue sync, inventory reconciliation and Wardrobe refund identity/landed-total fixes are merged and CI-green. But the provider integration specification states no merchant KYC or fulfilment vendor is selected/connected. Checkout is Stripe/card only; seller payouts, provider-booked shipments, tracking, delivery/cancellation/returns and live provider reconciliation are not completed operations.

**Decision:** schema and adapter contracts present; multi-market production operations blocked.

### Fashion retrieval research environment
PR #277 adds a hash-locked CPython 3.11/Linux x86_64 CPU-only dependency environment and a CI install/import consistency check. This supports reproducible CPU research setup only. It does not run model weights, retrieval inference, GPU kernels, CUDA compatibility or performance acceptance. A separate pinned CUDA environment and approved GPU validation are still required before GPU benchmarking.

## Security and deployment

Positive controls observed:
- Service credentials stay server-side; private routes use authenticated service boundaries.
- Look It uses bounded, request-scoped consent and private/no-store responses.
- Click It rejects before reading user-uploaded bytes.
- Product retrieval is distinct from CAL display authorization.
- Checkout is fail-closed by default and depends on live readiness and signed purchase receipts.
- Rollback guidance keeps checkout/public media disabled until database, payment and privacy reconciliation completes.

Outstanding release blockers:
- The release registry contains **23 required gates; all 23 are blocked**, with no exact-release-commit evidence references.
- Real OIDC identity/session lifecycle, managed PostgreSQL migration/backup/restore, Stripe staging checkout/webhook/refund/reconciliation, merchant verification, tax/fulfilment providers, production object storage, on-call/alerts and rollback drills remain unverified.
- No external penetration test, independent Click It masking assessment, external privacy review or production deployment certification was found in the reviewed repository evidence.

## Required acceptance sequence

1. Keep CAL purchase proxy and Click It disabled outside controlled staging.
2. #269 is merged with 8/8 exact-head workflows successful; retain the appearance-orchestration acceptance and integration gates below.
3. Deploy real identity, managed PostgreSQL, Wardrobe deletion worker and Asset Service in staging; run migration and restore drills.
4. Exercise PNELLY discovery → three looks → edits/wear/dislike → revocation/deletion → next recommendation; prove durable learning and ranking behavior.
5. Test every display/media/cart/checkout route with SHOW/BLOCK/REVIEW, absent/expired/revoked receipts, stale catalog version, changed offers, CIL denial and gateway failure.
6. Complete GPU VTON smoke/visual evaluation and independent Twin geometry/measurement validation before user-facing integration.
7. Complete Click It detector benchmark, independent attestation and full publication/deletion route audit.
8. Execute real provider sandbox operations for KYC, FX/tax, fulfilment, Shopify order/refund and Stripe reconciliation.
9. Obtain assessor-independent penetration, privacy, deployment, restore and rollback reviews; bind evidence to the exact release SHA and obtain owner approval before changing gate status.

**Overall decision: NOT PRODUCTION READY.** The release ledger remains 23/23 blocked; the latest merged CI does not change any production gate without independently verifiable, exact-release-commit evidence.
