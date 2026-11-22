# Independent regression, security and deployment review — 22 November 2026

## Scope and standard

This is an independent cross-workstream review of current-main code contracts, merged PR evidence, CI workflow results, service READMEs, production runbooks and the machine-readable release ledger. It is **not** a third-party penetration test, external privacy assessment, live deployment certification or real-customer acceptance study.

Repository: `cirvannaco-png/Cirvanna-demo`  
Reviewed main: `81580b26034e0cf424172d5b96eead4a1c22f840`

## Regression evidence verified

The following merged PR heads have completed relevant GitHub Actions workflows successfully:

| PR | Area | Exact-head workflow result |
|---|---|---|
| #197 | PNELLY + Wardrobe integration | 7/7 workflows successful |
| #196 | CAL feedback/purchase decision contracts | 6/6 successful |
| #242 | Shopify compensation/refund saga | Merged; follow-up #254 is the current-main regression consolidation |
| #243 | Shopify catalogue sync/inventory reconciliation | 4/4 successful |
| #254 | Shopify/Wardrobe reconciliation | 6/6 successful |
| #266 | Exact candidate/catalog-version/CIL binding | 5/5 successful |
| #255 | Look It request-scoped consent revocation | 5/5 successful |
| #261 | Click It jurisdiction-aware fail-closed policy | All unique workflows successful |
| #265 | Click It consent and image-rights lifecycle | 5/5 successful |
| #253 | Canonical CIL provider consent revocation | 7/7 successful |
| #249 | FASHN flat-lay VTON inference contract | 7/7 successful |
| #250 | Research-only SAM 3D Body worker | 3/3 successful |
| #269 | Appearance specialist/orchestrator candidate | 8/8 successful; review still required |

No unresolved inline review threads were found on the reviewed merged PRs #243, #254, #266, #265, #261, #255 and #253, or current candidate #269. #269 has not been merged. CI success establishes automated contract/build checks only; it does not establish live provider or deployment behavior.

## Findings by product workstream

### 1. PNELLY + Wardrobe

**Implemented on main**
- Authenticated PNELLY conversational discovery uses the wardrobe-aware discovery flow.
- Daily-look endpoint produces three role slots from owner-scoped active wardrobe items and rotation state; it does not fabricate garments to fill missing coverage.
- Complementer is request-scoped and advisory-only; it cannot authorize product display or purchase.
- Saved outfits, piece-level editing, explicit wear events and consent-gated feedback contracts exist.
- BFF resolves the user through Commerce identity rather than trusting a browser-supplied subject.

**Open findings**
- Recommendation Service documents durable profile memory, production gateway hydration, live product retrieval and longitudinal skin-state forecasting as not implemented.
- A durable TAL event is not automatically a changed USI/NPL preference; a reviewed learning consumer and ranking-effect validation remain missing.
- Wardrobe production PostgreSQL and the live asset-deletion worker/retry/DLQ path are not deployed and proven.
- Wardrobe browser entry remains text-only; photo upload/automated visual observation is intentionally disabled pending private asset and consent deployment.
- No production cohort evidence demonstrates that the complete PNELLY → Wardrobe → feedback → learning → next recommendation loop works for real users.

**Disposition:** integration foundation implemented; end-to-end production acceptance remains open.

### 2. CAL display and checkout

**Implemented on main**
- PR #266 binds marketplace candidate display to exact product identity, catalog version, CIL eligibility and policy/arbitration contract versions.
- Non-SHOW candidates must remain undisclosed; Look It returns component descriptions/counts rather than product, merchant, price or image details before CAL SHOW.
- BFF cart/checkout proxy is disabled by default. Protected routes require configured enablement plus live Commerce readiness/capability checks.
- Commerce purchase receipts bind the authenticated subject, action, exact offer snapshot, product/variant/listing/merchant, quantity, price/currency, catalog version, policy version and expiry.
- Checkout and cart mutations are expected to reject stale/changed offers and BLOCK/REVIEW/invalid/expired receipts without creating an order or reservation.

**Open findings**
- The documented staging acceptance sequence has not been evidenced against real staging Commerce + Decision Gateway.
- No proof is recorded that every deployed product/media route, alternate browser surface, cached asset, shared link and checkout path has been independently exercised against the same CAL policy.
- The BFF purchase switch must remain off until real staging evidence and audit persistence are verified.

**Disposition:** strong code-level authorization boundary; complete route-coverage and live checkout acceptance not yet proven.

### 3. Virtual Twin and real Try-On

**Implemented on main**
- Owner-scoped Twin Registry metadata and private asset authorization foundations exist.
- PR #250 adds a gated research-only SAM 3D Body worker with pinned source/model artifact requirements and mesh-only output.
- PR #249 adds a FASHN VTON 1.5 inference path restricted to maskless flat-lay garments.
- Private asset, consent and model-readiness contract tests pass.

**Open findings**
- The SAM 3D worker is not integrated with public Virtual Twin API, Asset Service or Twin Registry; no customer-facing persistent Twin is generated.
- The current BFF capability response explicitly reports `try_on_available=false`. Twin onboarding does not capture the complete full-body reconstruction workflow.
- The worker is research-only; no GPU smoke test, independent mesh/anatomical validation, calibrated measurement study or representative human evaluation is recorded.
- FASHN GPU inference and visual-quality acceptance have not been demonstrated. Model-worn garment mode remains disabled because the segmentation/parser dependency lacks acceptable commercial-use evidence.
- No deployed end-to-end consent/revocation/asset deletion and real-user try-on session has been independently validated.

**Disposition:** not complete. Do not advertise persistent Twin generation, calibrated measurements or production Try-On.

### 4. Click It and Look It privacy

**Implemented on main**
- Look It and Click It are separate routes with different product semantics and consent handling.
- Look It uses short-lived request/resource-bound `image_processing` + `look_it` consent; PNELLY rechecks consent; BFF revokes the request bundle and suppresses results if cleanup fails.
- Click It has jurisdiction-aware policy and photographed-person rights lifecycle contracts.
- Click It BFF closes/rejects uploads before multipart parsing and returns a private no-store 503 while the masking release is blocked.
- Public serializers withhold unverified image URLs and product details.

**Open findings**
- No independent detector false-negative/recall evaluation is recorded for the exact pinned runtime and release build.
- The production masking/attestation pipeline and private storage provider are not proven deployed.
- Jurisdiction, guardian verification, requester-authority and content-lifecycle providers remain unconfigured/unverified in the privacy verification plan.
- Full ingress → processing → object store → restore → publication → CDN/cache → shared-link → deletion route coverage has not passed an independent end-to-end inspection.
- Rights quarantine and deletion propagation are not proven across external storage, replicas, CDN caches and backups.

**Disposition:** Look It's guarded flow is implemented; Click It remains disabled. Do not enable it.

### 5. Multi-market commerce and Shopify

**Implemented on main**
- Market/merchant eligibility, versioned FX/tax/fulfilment/payment evidence contracts and quote freshness validation exist.
- Market activation requires current merchant verification evidence and tax capability evidence; fulfilment distance must be exactly representable at 0.01 km.
- Shopify compensation, catalogue synchronization leases, inventory reconciliation and Wardrobe refund identity/landed-total fixes are merged.
- #243 and #254 exact-head CI passed.

**Open findings**
- The provider integration specification explicitly says no merchant KYC or fulfilment vendor is selected/connected.
- Quote records and admin/provider references are not proof of carrier-generated quotes or real serviceability.
- Checkout is Stripe/card only; seller payouts/Connect onboarding, provider-booked shipments, tracking, cancellation, delivery confirmation, claims and physical returns are not completed provider operations.
- No live merchant verification, tax provider, FX source, carrier booking or cross-market order has been reconciled against a provider source of truth.
- PostgreSQL backup/restore and scheduled monitored worker operation still need real environment evidence.

**Disposition:** schema and adapter contracts are present; multi-market production operations remain blocked.

## Security and deployment review

### Positive controls observed
- Private BFF/service credentials are not intended for browser exposure.
- Service-to-service URLs reject insecure/credential-bearing configurations.
- Upload paths are bounded, consent-scoped and private/no-store; Look It suppresses results if revocation/cleanup fails.
- Click It fails closed before reading user-uploaded bytes.
- Candidate display and checkout are separated from retrieval/ranking.
- Rollback procedures keep checkout and public media paths disabled until database/payment/privacy reconciliation is complete.

### Release blockers confirmed
- `docs/release/release-gates.json` contains **23 required gates; all 23 are blocked** and there are no exact-release-commit evidence references.
- Real OIDC identity provider/session lifecycle, managed PostgreSQL migration/backup/restore, Stripe staging checkout/webhook/refund/reconciliation, merchant verification, tax/fulfilment providers, production object storage, on-call/alerts and rollback drills remain unverified.
- No third-party penetration test, independent Click It masking assessment, external privacy review or production deployment certification was found in the repository evidence reviewed.

## Required next acceptance sequence

1. Keep the Commerce CAL purchase proxy and Click It disabled outside controlled staging.
2. Finish PR #269 review; merge only if review remains clean and exact-head CI is still green.
3. Deploy real identity, managed PostgreSQL, Wardrobe deletion worker, Asset Service and provider secrets in staging; execute migration and restore drills.
4. Run a signed-in PNELLY/Wardrobe user journey from discovery through three looks, edit/wear/dislike feedback, revocation, deletion and subsequent recommendation; prove which feedback reaches durable USI/TAL/NPL and how ranking changes.
5. Exercise every product display, image/media, cart and checkout route with SHOW/BLOCK/REVIEW, missing/expired/revoked receipt, stale catalog version, changed offer, CIL denial and gateway timeout.
6. Complete GPU VTON smoke/visual-quality evaluation and independently validate Twin geometry/measurements before connecting the research worker to any user-facing Twin path.
7. Complete Click It detector benchmark, independent masking attestation and full publication/deletion route audit before considering enablement.
8. Execute real provider sandbox operations for merchant verification, FX/tax, fulfilment booking/tracking, Shopify order/refund and Stripe reconciliation.
9. Have an assessor independent of implementation execute penetration, privacy, deployment, restore and rollback reviews. Attach evidence to the exact release SHA and update gates only after owner approval.

**Overall decision: NOT PRODUCTION READY.** Automated regression coverage is materially stronger, but the requested end-to-end and independent operational acceptance has not yet been achieved.
