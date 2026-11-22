# Independent regression, security and deployment review — 22 November 2026

Reviewed repository: `cirvannaco-png/Cirvanna-demo`  
Reviewed main: `81580b26034e0cf424172d5b96eead4a1c22f840`.

This is a cross-workstream review of code contracts, merged PRs, CI evidence, service READMEs, runbooks and release-gate state. It is not a third-party penetration test, external privacy assessment, live deployment certification or real-customer acceptance study.

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
| #269 | Appearance specialist/orchestrator candidate | 8/8 successful; review pending |

No unresolved inline review threads were found on #243, #254, #266, #265, #261, #255, #253 or #269. CI validates automated contracts/builds, not live provider or deployment behavior.

## Findings

### PNELLY + Wardrobe
Authenticated wardrobe-aware discovery, three daily-look roles, Complementer advisory, saved outfits, editing and consent-gated feedback contracts exist. However, Recommendation Service documents durable profile memory, production gateway hydration, live product retrieval and skin-state forecasting as not implemented. TAL events do not automatically change USI/NPL or ranking; a reviewed learning consumer and measured feedback loop are missing. Wardrobe production PostgreSQL, live asset-deletion worker/retry/DLQ and deployed identity/consent acceptance remain unverified. Browser photo entry remains text-only.

**Decision:** integration foundation present; end-to-end production acceptance incomplete.

### CAL display and checkout
PR #266 binds displayed candidates to exact product/catalog version, CIL eligibility and policy/arbitration versions. Non-SHOW results are intended to be withheld. BFF cart/checkout proxy is default-off and requires live Commerce readiness/capability checks plus candidate-bound purchase receipts.

Staging acceptance against real Commerce + Decision Gateway has not been evidenced. Every deployed product/media route, alternate surface, cached asset, shared link and checkout path has not been independently exercised against the same CAL policy.

**Decision:** code-level authorization boundary present; complete route coverage and live checkout acceptance unproven. Keep the purchase switch off until staging evidence passes.

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
2. Complete #269 review; merge only if review is clean and exact-head CI remains green.
3. Deploy real identity, managed PostgreSQL, Wardrobe deletion worker and Asset Service in staging; run migration and restore drills.
4. Exercise PNELLY discovery → three looks → edits/wear/dislike → revocation/deletion → next recommendation; prove durable learning and ranking behavior.
5. Test every display/media/cart/checkout route with SHOW/BLOCK/REVIEW, absent/expired/revoked receipts, stale catalog version, changed offers, CIL denial and gateway failure.
6. Complete GPU VTON smoke/visual evaluation and independent Twin geometry/measurement validation before user-facing integration.
7. Complete Click It detector benchmark, independent attestation and full publication/deletion route audit.
8. Execute real provider sandbox operations for KYC, FX/tax, fulfilment, Shopify order/refund and Stripe reconciliation.
9. Obtain assessor-independent penetration, privacy, deployment, restore and rollback reviews; bind evidence to the exact release SHA and obtain owner approval before changing gate status.

**Overall decision: NOT PRODUCTION READY.**
