# Cirvanna master product and engineering checklist

**Code baseline audited:** `main` at `6428b41d8334b7579e2b9620bd4a12d523bcfa1b` (8 November 2026; includes consent #158, refund reconciliation #159, VTON/Click It containment #161/#162, CRFP scope correction #164, double-review evaluator #165 and canonical PNELLY identity #166)  
**Status:** Active; the product requirements are captured below. This is not a production-readiness declaration.

## Operating rules

- Track the whole product, not isolated demos. A task is complete only when its acceptance criteria pass at the correct level (unit, contract, integration, deployed or physical-device).
- Keep the two-step product plan: **Step 1 — foundation and ownership**; **Step 2 — intelligence and connected experience**. Workstreams may progress simultaneously when contracts and dependencies permit.
- Do not make the personal wardrobe the universal source of truth. A new user with an empty wardrobe still receives useful, non-fabricated recommendations from their declared identity/style profile and context. Once the user adds items, the wardrobe is authoritative for what they own and wear.
- Preserve domain ownership: Identity/USI owns declared style profile; Wardrobe owns user-owned item records and wear history; Catalog owns canonical product identity and product facts; Commerce owns merchant offers, prices, stock, orders and payment state; NPL owns hard exclusions; USI/TAL owns positive preference/learning observations; the canonical decision/CAL layer owns final product display authorization; Virtual Twin owns the user's authorized Twin record/assets; DermalSight owns non-diagnostic cosmetic skin signals.
- A product being browsed, saved, shortlisted, placed in a cart, recommended or tried on is **not** wardrobe ownership. A confirmed purchase may be synchronized to the wardrobe only through a verified Commerce event and an idempotent ownership handoff. A payment refund updates financial state only; it does not prove a physical return or automatically remove the garment from Wardrobe. Any ownership reversal requires a separate verified return/possession workflow.
- Never infer sensitive identity, culture, skin tone, body shape, health status or preferences from a name, location or face when the relevant data must instead be user-declared or evidence-validated.
- Fail closed when consent, ownership, model provenance, product evidence, fit evidence or display authorization is missing. Return explicit UNKNOWN / REVIEW / unavailable states instead of fabricated confidence.
- AI suggestions are advisory. Users can accept, reject, modify, undo and correct learned information. Hard exclusions remain distinct from soft rejection observations.

## Status vocabulary

- [ ] Not started / not verified.
- [~] Partially implemented or code exists but one or more product, evidence, integration or deployment gates remain open.
- [x] Verified at the stated level only. The evidence and exact scope must be recorded.
- [!] Blocked by an external dependency, missing dataset/model/provider, account access or physical-device test.

## Step 1 — Foundation, data ownership and integrity

### 1.1 Identity, profile and empty-wardrobe onboarding
- [ ] Define a versioned identity/style profile that works when the wardrobe is empty, partial or fully populated.
- [ ] Separate declared preferences, measured/analysed signals, model estimates, context and learned observations; retain provenance, confidence semantics, timestamps and correction history.
- [ ] Define user control for profile creation, edits, export, deletion, consent, retention and reset.
- [ ] Make identity/profile the recommendation bootstrap for an empty wardrobe; make Wardrobe authoritative only for owned items and the user's own wear/combination history.
- [ ] Define conflict resolution and event ordering for profile updates, wardrobe updates, purchases, cancellations, user corrections and offline sync.
- [ ] Add cross-domain schemas, API contract tests, idempotency keys, optimistic concurrency and owner/tenant isolation tests.

### 1.2 Wardrobe domain and item lifecycle
- [x] Merge the versioned, owner-scoped single-item edit API (PR #128); its Wardrobe persistence and architecture checks passed.
- [x] Connect single-item editing to the authenticated BFF and Wardrobe UI; edit one selected garment/accessory without changing other items, with stale-version conflict handling and reload. User-facing undo remains open.
- [x] Saved-outfit piece editing implemented in PR #135: create/list saved looks from owned items; add, replace or remove one piece with optimistic versioning and command replay protection; the UI preserves unaffected pieces. Deployment migration and device QA remain release gates.
- [x] Implement the versioned shared Wardrobe taxonomy for clothing, footwear, accessories and beauty items; expose it through the authenticated Wardrobe API/BFF, normalize legacy aliases, preserve valid custom keys, reject malformed keys, and populate the UI from the canonical list. Merged current-main implementation and cross-service CI are verified (PR #153); deployment and physical-device evidence remain separate release gates.
- [ ] Support user-added items with explicit provenance, optional photos, metadata correction and appropriate consent; do not silently turn image guesses into facts.
- [ ] Support safe archive, restore and deletion; ensure image/asset deletion is actually completed by the storage worker, not merely queued.
- [ ] Add import/bulk-add, duplicate detection and item merge/correction without silently merging distinct variants.

### 1.3 Wardrobe sync, purchase ownership and source-of-truth rules
- [ ] Define near-real-time sync for user-added/edited items and authorized brand/catalog changes, with explicit source, version, last-synced time and conflict handling.
- [~] Verified purchase-to-Wardrobe ownership source is implemented: Commerce emits a paid-order outbox event and the authenticated worker materializes owner-scoped purchase provenance idempotently (PR #151 / #145). Production webhook delivery, live event replay and operational monitoring remain unverified; browsing, saved, cart, unpurchased or try-on products must never appear as owned.
- [~] Commerce now processes signed Stripe `charge.refunded` events, maps them to a paid order through its PaymentIntent, validates cumulative amount/currency and emits an idempotent `commerce.order.refund.updated` outbox event (PR #159). Wardrobe stores an owner/order-scoped financial snapshot and deliberately leaves item ownership unchanged. Physical return, restocking, cancellation reversal, disputes/chargebacks and item-level refund allocation remain open.
- [ ] Keep Catalog product facts canonical; Wardrobe stores canonical product/variant references plus user-specific notes and preferences, not a competing copy of merchant facts.
- [~] Paid and refund event source paths have duplicate/replay, monotonic cumulative refund, retry, owner isolation and PostgreSQL restore CI coverage (PR #145/#151/#159). Live Stripe webhook delivery, worker deployment/monitoring, provider replay and physical-return event handling still require staging/production evidence.
- [ ] Provide optional marketplace notifications for unowned products that complement an outfit; label them as suggestions/available-to-buy, never wardrobe items.

### 1.4 Commerce and marketplace transaction integrity
- [~] Commerce implements immutable checkout line snapshots, idempotent orders, inventory reservation, signed Stripe paid-event verification, transactional paid-order outbox and cumulative charge-refund snapshot/outbox (PR #159). Physical returns, chargebacks/disputes, partial cancellations, live Stripe test-mode reconciliation, landed-cost completeness and deployed operational controls remain open.
- [ ] Enforce price integrity: merchant changes to a listing affect future offers only; checkout must bind an explicit quoted offer/version/expiry and revalidate before payment; once an order is accepted/paid, merchant edits must not rewrite the order's agreed line price or terms.
- [ ] Implement customer cancellation windows and state transitions, including partial cancellation where supported, stock release, payment void/refund, audit trail and clear merchant/customer permissions.
- [~] Signed Stripe charge-refund webhook reconciliation and downstream financial snapshot delivery are implemented in source/CI (PR #159); no browser redirect is trusted. Physical returns, disputes/chargebacks, item-level allocation and inventory restocking remain unimplemented.
- [ ] Apply market, currency, tax, shipping/delivery fee, stock, seller eligibility, size/variant availability and fulfilment constraints to recommendations and checkout.
- [ ] Support the configured local discovery radius (30 km initial radius, user-expandable) without implying delivery availability; show delivery/transport fees and estimated availability where verified.
- [ ] Add offer freshness, price-history/provenance and stale-quote tests; preserve canonical product and cross-merchant variant identity.
- [ ] Keep product display gated by the canonical CAL decision; no search, sponsored, try-on or recommendation path may bypass BLOCK/REVIEW or missing evidence.

### 1.5 Consent, privacy and learning data rights
- [~] Profile-learning consent, resource-bound media/Twin consent bundles and the owner-scoped Twin registry are in main. PR #158 added subject + bundle + consent-version + optional resource verification, exact Twin-ID binding, scope-completeness checks, resource-specific revocation and PostgreSQL 17 migration/backfill/dump-restore CI. The production identity/consent provider and managed database are not provisioned; real bucket policy, revocation/deletion worker and deployed evidence remain release gates.
- [~] Click It is deliberately unavailable and fails closed: Marketplace BFF now closes the uploaded file without reading or forwarding bytes (PR #162), and Vision Intelligence rejects the internal scan before decode, quality scoring, embedding or retrieval. Public marketplace/gateway/vision serializers withhold unverified image URLs. This is containment, not a released masking feature or global publication certification.
- [~] Draft PRs #107/#111 contain the privacy-governance and pinned BlazeFace masking candidate, but remain open and unmerged; current main intentionally blocks Click It ingress (#162). The model pin/build smoke test is not independent recall validation and does not release Click It.
- [ ] Build the trusted face-masking stage and independent asset-bound privacy attestation; mask all detected faces, fail closed on uncertain/missing detection, prohibit facial recognition/identity search/age estimation, use transient processing and bind receipts to exact source/output asset hashes and model revisions.
- [!] Binary media storage/delivery remains a separate open security gap tracked by issue #121: recursive API URL redaction does not prove private object ACLs, origin isolation, CDN invalidation or revocable binary delivery. No claim that every unmasked image is contained is permitted.
- [ ] Inventory and wire every public media mutation path—profile/community feeds, marketplace, merchant surfaces, shared links, restore, syndication, cache/CDN and derivatives—to the central pre-publication gate. Verify that no unmasked original or derivative can escape on missing, stale, mismatched or unsafe attestation.
- [ ] Provision jurisdiction policy resolver, signed counsel-approved policy bundles, guardian-authority verification, rights-requester verification and Content Lifecycle quarantine/unpublish/delete/CDN purge; staff a human review/removal operation. PRs #107/#111 remain open candidates and are not live providers or platform-wide evidence.
- [x] User-facing export, NPL correction/retraction and deletion across USI/TAL, NPL and Wardrobe are implemented and CI-verified in merged PR #139. Production migration, retry/failure-injection and deployed deletion evidence remain release gates.
- [ ] Ensure consent is checked server-side on every relevant read/write/processing path; a UI checkbox alone is not authorization.
- [ ] Ensure no raw face/body photos, tokens, secrets or unnecessary sensitive information are written to logs/analytics.
- [ ] Test subject isolation, resource substitution, expired/revoked consent, replay, deletion retries and asset purge at API and storage boundaries.
- [x] Stale PR #130 privacy/learning-data requirements were reconciled into merged PR #139 on the current main base; no stale branch was force-merged.

## Step 2 — Intelligence, connected experience and measurable quality

### 2.1 Personal colour profile (independent Style Desk product)
- [x] User-owned, editable Style Desk colour profile merged in PR #137, separate from catalogue colour metadata; it uses versioned USI/TAL storage and existing profile-storage consent.
- [x] The profile captures user-declared liked, disliked and “brings out my best version” colours with optimistic versioning and export/deletion support. Objective analysis is explicitly marked unavailable; no skin-tone inference is fabricated.
- [ ] Store colour observations separately from user preference: undertone/contrast/palette hypotheses must be evidence-labelled, confidence-aware and correctable.
- [ ] Define a controlled capture protocol (neutral lighting guidance, exposure/white-balance checks, camera/device metadata, reference calibration where appropriate) and detect unsuitable lighting before analysis.
- [ ] Evaluate colour analysis across skin tones, devices, lighting conditions and regions. Report subgroup performance and uncertainty; do not collapse preference into an objective “best colour”.
- [ ] Use the profile for clothing, makeup, accessories, hair colour and complete-look coordination, with an explanation of whether each result comes from user preference or measured/curated colour harmony.
- [ ] Connect the profile to Wardrobe, PNELLY, Complementer, Marketplace, Virtual Twin and Virtual Try-On through versioned, consented profile signals.

### 2.2 Cosmetic skin analysis (DermalSight)
- [~] A runnable API, hash-verified ONNX adapter and signed validation-report gate exist. The repository states that no approved trained model artifact, representative evaluation dataset, calibrated performance report or production inference setup is currently supplied.
- [ ] Approve a licensed model artifact, preprocessing contract and attribute taxonomy for visible cosmetic characteristics such as dark spots, blemishes, freckles and texture variation; keep outputs non-diagnostic.
- [ ] Validate image quality and lighting (illumination, colour cast, blur, glare, occlusion, exposure and camera differences) and request recapture or return UNKNOWN when quality is insufficient.
- [ ] Validate repeatability and accuracy by skin-tone subgroup, lighting, device, age range where legally/ethically appropriate, and capture condition; publish error bars and failure cases.
- [ ] Distinguish visible observations from inferred explanations; never claim that one photo diagnoses a condition or identifies its cause.
- [ ] Validate skin-attribute calibration and any score semantics before exposing a score; do not present raw model outputs as probabilities.
- [ ] Complete model licensing, data rights, privacy, security and intended-claims review; verify actual inference on the deployed runtime, not only fake-session unit tests.

### 2.3 FCI, body measurements and fit
- [~] FCI contracts and architecture tests exist, but an independently validated, calibrated fit-evidence provider and representative garment/body dataset are still release gates. The Virtual Twin API currently does not claim calibrated body measurements.
- [ ] Define the exact FCI claims, units, confidence semantics and abstention behaviour; unknown evidence must remain UNKNOWN.
- [ ] Define body-measurement capture protocol (camera placement, distance, pose, garment state, scale reference, lighting, image-quality checks and retries).
- [ ] Treat the requested 4% measurement error as a target requiring independent evidence. Specify the metric (per-measurement absolute percentage error, median/p95 and subgroup error), ground truth protocol and confidence interval before claiming pass.
- [ ] Validate measurement error per body region, pose, device, height/body-size range and relevant user cohorts; publish failures and unsupported conditions.
- [ ] Distinguish geometric measurement error from garment fit confidence; do not market them as the same metric.
- [ ] Calibrate fit evidence against real garment sizing/construction/brand size charts and observed outcomes, with no recommendation if evidence is inadequate.

### 2.4 Wardrobe intelligence, PNELLY, NPL, CRFP and learning
- [~] PNELLY daily-look composition is implemented and CI-verified in merged PR #139 from authenticated Wardrobe snapshots through Decision Gateway to Complementer, with a Wardrobe UI. Marketplace, persistent Twin and multi-product try-on context handoff remain open.
- [~] Merged PR #139 records explicit worn/not-my-style feedback only with active style-learning consent; modify/save/search/purchase/return event coverage and durable outfit-graph attribution remain open.
- [~] Merged PR #139 keeps PNELLY soft feedback separate from NPL hard exclusions and adds user retraction; full end-to-end tests across every recommendation surface remain open.
- [ ] Connect wardrobe feedback to NPL and the canonical recommendation pipeline. Keep FCI fit-confidence ownership and the two CRFP scopes (marketplace/system-wide) distinct; do not promote CRFP runtime behavior before its authoritative specifications are recovered.
- [ ] Use explicit profile and wardrobe evidence to personalise recommendations; explain the reason, source and uncertainty.
- [~] Wardrobe now stores owner-scoped saved outfit snapshots and explicit wear events with item snapshots, outfit version and consent provenance (PR #151); rotation-cycle state and revival logic are persistent (PR #149). A complete cross-surface outfit graph, user-rating/context coverage and production learning telemetry remain open.
- [~] Persistent wardrobe rotation prioritizes unseen eligible items, resets immediately after a completed cycle and uses recent wear as a ranking signal rather than a permanent exclusion (PR #146/#149). Cross-surface outfit-level evaluation and real-user utilisation outcomes remain unmeasured.
- [ ] Add deterministic anti-repeat tests (same outfit, near-duplicate combination, cooldown, wardrobe changes, seasonal/context changes) plus a human-reviewed relevance/diversity baseline.
- [~] PNELLY evaluation now has a strict case schema, exactly two independent blinded reviews per candidate, disagreement adjudication, consent/pseudonym/privacy-checked trace preparation, a transparent baseline, reviewer agreement/kappa, participant-cluster bootstrap intervals and Everyday/Elevated/Explore reporting (PR #117 foundation; double-review/statistical hardening merged in #165). CI uses synthetic fixtures only. The HMAC-pseudonymized opt-in Gateway trace exists, but the dataset remains empty; no approved reviewer UI/study collector, randomized baseline arm, look-level exposures/edits/rejections or empirical algorithm-vs-baseline result exists. Reviewer identity and independence still require coordinator verification. Do not claim recommendation quality or causal uplift.
- [ ] Measure whether recommendations improve user satisfaction and wardrobe utilisation; do not equate clicks or exposure with preference.

### 2.5 Complementer: suggestions and “Upgrade my look”
- [ ] Make Complementer optional and available from PNELLY, Virtual Twin, Virtual Try-On and relevant recommendation surfaces.
- [ ] Provide two explicit modes: **Suggestion mode** for small, reversible refinements and **Upgrade my look** for a deliberate, user-requested transformation.
- [ ] Explain proposed changes using the user's colour profile, declared preferences, proportions/fit evidence where validated, wardrobe, context and available products.
- [ ] Preserve identity, signature pieces, explicit exclusions and the user's chosen silhouette unless the user requests a change.
- [ ] Let users compare before/after, accept, reject, modify and undo each individual piece independently.
- [ ] Recommend actual marketplace products only from canonical Catalog/Commerce data and only after CAL authorization; never fabricate brand, SKU, price, inventory or delivery.

### 2.6 Connected Virtual Twin and multi-product try-on
- [~] Owner-scoped persistent Twin registry and provider-neutral private asset service are merged (PR #152/#124), with authorization, integrity, parent-scoped deletion and lifecycle contracts. Resource-bound consent verification is now in main (PR #158). Actual production private S3/PostgreSQL providers, validated full-body mesh generation, live renderer and end-to-end deletion confirmation are not provisioned.
- [~] The API and registry distinguish ephemeral pose-skeleton inference from a validated full-body mesh registration; a pose skeleton is not a persistent Twin. Real full-body generation/validation and persisted visual preview remain unavailable.
- [ ] Connect Wardrobe, PNELLY and Marketplace bidirectionally to the same Twin and try-on session without duplicate stores or user identity paths.
- [ ] Permit product selection from Marketplace and wardrobe selection from the personal closet; support searching for an exact product or a canonical purchasable variant in the Marketplace.
- [ ] Support multi-item try-on from either source (e.g. top + trousers + shoes + accessories) with slot validation, product/variant provenance and independent removal/replacement.
- [ ] Preserve the exact product's colour, pattern, design, cut, material appearance and variant through visualization; disclose unsupported rendering changes.
- [ ] Support complete user-created outfit combinations in the Twin/try-on, save them to the wardrobe/outfit graph and send consented feedback to identity/decision learning.
- [ ] Allow users to modify one selected piece in a saved look without regenerating or silently changing the rest.
- [ ] Integrate optional Complementer suggestions and Upgrade my look mode into Twin/try-on with per-item acceptance and comparison.
- [ ] Reduce latency through measured budgets, caching keyed by safe/versioned assets, progressive rendering and bounded worker queues; never serve one user's private render to another.
- [~] The private VTON worker now enforces source/artifact provenance, model-file integrity, real GPU readiness and a commercial-license gate (PR #127/#161). Model weights are not provisioned, the inherited human-parser license blocks commercial use absent written permission or a cleared replacement, and no real GPU inference is verified.
- [!] Physical Android QA remains blocked. Browser/fake-camera CI is not device evidence; the Android 10 TECNO KB8 and low-/mid-/high-range device matrix still require hands-on runs with camera, lifecycle, FPS, memory, thermal and network measurements (issue #70).

### 2.7 Marketplace recommendations and product discovery
- [ ] Give each product a concise, evidence-backed assessment of fit with the user's declared style profile, colour preferences, wardrobe, context and constraints.
- [ ] Consider region/location, market eligibility, in-stock status, size/variant, budget/price currency, delivery coverage/time/cost, fulfilment and explicit exclusions before ranking.
- [ ] Let users search the Marketplace from a wardrobe item for the exact product or a verified canonical variant/near substitute.
- [ ] Let users try a product before purchase from the Marketplace; do not make a wishlist/cart entry a wardrobe-owned item.
- [ ] Recommend real products to complete or improve a look from PNELLY, Complementer, Twin, try-on and marketplace recommendations, all through the same product authorization gate.
- [ ] Support merchant product/offer sync and user wardrobe sync as distinct event streams with freshness, source and conflict visibility.
- [ ] Keep product notifications separate from the owned wardrobe; make promotional placement transparent and subject to the same exclusion/display rules.
- [ ] Measure recommendation relevance, item availability, actual conversion, cancellation, return and dissatisfaction; use controlled experiments and avoid unsupported promises.

### 2.8 Quality, performance, security and release
- [ ] Add contract, unit, integration, security, privacy, regression and end-to-end tests for all user flows and ownership boundaries.
- [ ] Add latency SLOs for Twin and multi-product try-on; measure p50/p95/p99 on defined device/network cohorts.
- [ ] Run dependency, source/artifact license, secret and supply-chain scans; verify CSP, HTTPS, CORS, object-storage access and API auth.
- [~] PostgreSQL 17 migration application and custom dump/restore CI cover Wardrobe rotation, wear history, purchase provenance and refund snapshots (PR #159), plus Identity consent bundles (PR #158). These are isolated CI databases, not production backup/restore drills. Production migrations, live webhook replay, queue/DLQ operations and provider-backed deletion completion remain unverified.
- [ ] Run actual Android-device acceptance tests in addition to browser automation.
- [ ] Add observability with privacy-minimized event IDs, reason codes and model/runtime provenance; never log raw image payloads or credentials.
- [~] The machine-readable release-gate registry and repository evidence instructions exist; this checklist update records the current source/CI state. A complete release evidence pack with deployed environment, production restore drill, live payment, provider/model manifests, operational ownership and rollback evidence is still outstanding.
- [ ] Do not declare Cirvanna production-ready until the critical provider, dataset, model, privacy, payment, migration, storage and device gates pass.

## Current verified baseline and immediate work

- [x] Repository inspected on 8 November 2026 at main commit `6428b41d8334b7579e2b9620bd4a12d523bcfa1b`; active monorepo and service boundaries identified.
- [x] Versioned single-item Wardrobe edit API and authenticated UI controls merged in PR #128; its Wardrobe persistence and architecture checks passed.
- [~] DermalSight has a fail-closed ONNX adapter and signed release-evidence gate, but the trained/validated model and dataset are absent.
- [~] Commerce implements immutable line snapshots, transactional stock reservation, verified Stripe settlement and cumulative signed charge-refund reconciliation (PR #159). Refund snapshots flow through Sync to Wardrobe's separate financial ledger without changing garment ownership. Physical returns/chargebacks, landed-cost checkout, complete price-integrity verification and live production reconciliation remain open.
- [~] Wardrobe has authenticated persistence, persistent rotation, explicit wear-history and verified-purchase ownership contracts; the production database/restore, production event delivery, physical UI QA and real object-store deletion path remain gated.
- [~] FCI contract exists; no independently validated calibrated provider or proven 4% measurement accuracy.
- [~] Virtual Twin registry and private asset-service source are merged; a real mesh generator/validator, live consent verifier, private object-store configuration and persistent render provider are not operational. The API correctly reports pose-skeleton inference separately from a persistent user Twin.
- [x] Saved-outfit piece editing is implemented in merged PR #135; the user-declared colour preference profile is implemented in merged PR #137. PNELLY wardrobe companion, complete personal outfit graph, actual human-reviewed dataset and study operations, multi-product try-on, and end-to-end marketplace-to-wardrobe/Twin flows remain to be integrated and verified.
- [x] Merged PR #139 ports the PNELLY daily-look Decision Gateway route and consent/NPL checks onto current main; Decision Gateway tests passed.
- [x] Privacy/learning-data controls from stale PR #130 are integrated through PR #139. Confirm deployed migrations, deletion retry behaviour and production evidence before release.
- [~] PR/branch reconciliation was documented in #157, but its inventory is stale. The 8 November 2026 open-PR query returned **11 pre-existing open PRs** (excluding this checklist refresh, #167):
  - #102 multi-market Commerce: 85 commits ahead / 42 behind main; 7 historical workflow groups passed on its head. Rebase and re-audit the offer/FX/tax/fulfilment providers before considering integration.
  - #84 PNELLY Look It: 63 ahead / 46 behind; 11 historical workflow groups passed. Keep separate from Click It; provider/model and current privacy/consent integration remain blockers.
  - #77 merchant/founder portals: 6 ahead / 48 behind; 4 historical workflow groups passed. Rebase and verify identity role issuance, migration and same-origin deployment.
  - #69 AM/PM skincare routines: 19 ahead / 52 behind; 2 historical workflow groups passed. UI, authenticated subject binding and live recommendation provider remain absent.
  - #68 Living Filters: 96 ahead / 52 behind; 3 historical workflow groups passed. Physical Android QA, performance and runtime/device acceptance remain open.
  - #67 intelligent marketplace filters: 11 ahead / 52 behind; 8 historical workflow groups failed before runner steps were recorded. Rebase before diagnosing or trusting prior results.
  - #66 appearance specialist registry: 51 ahead / 52 behind; 4 historical workflow groups failed before runner steps. Keep internal until identity, provider and current-main integration gates pass.
  - #64 PAMASMMA/brand-auth foundations: 42 ahead / 480 behind; its workflow failed before runner steps. Treat as highly stale; do not merge without a fresh source/value audit.
  - #62 candidate-bound CAL purchase governance: 119 ahead / 54 behind; 10 historical workflow groups failed. Independent safety/FCI providers and staging checkout evidence are still absent.
  - #107 Privacy Governance: 154 ahead / 41 behind; no workflow runs are reported for its current head. Keep draft; provider, policy-signing, rights and publication integration gates remain.
  - #111 outfit-evaluation/publication safeguards: 165 ahead / 41 behind, stacked on #107; no workflow runs are reported for its current head. Rebase/retarget only after #107 is reconciled; the human-labelled dataset is empty.
  - All 11 feature branches diverge from current main. The ahead/behind figures are commit topology, not evidence of unique useful work. Do not merge or delete branches based on counts alone; compare file-level changes, preserve valuable commits, and close/supersede stale work only after a reviewed migration.

- [x] CRFP naming and scope corrected in merged PR #164: CRFP is canonical, with distinct marketplace and system-wide scopes; no unvalidated runtime behavior is implied.
- [x] PNELLY evaluation hardening merged in PR #165; its two-review protocol, adjudication and cluster-aware reporting are CI-verified, but the human-labelled dataset remains empty.
- [x] PNELLY canonical identity migration merged in PR #166; legacy Xari API/import compatibility remains intentionally in place pending a separate path migration.

## Required evidence for every completed checklist item

For each item marked [x], record: implementation commit/PR; affected contract/API/UI; unit and contract tests; integration or deployed evidence where required; model/dataset/version and license where relevant; performance cohort and metric where relevant; privacy/consent scope; unresolved limitations. Physical-device, deployed, empirical accuracy or production-readiness claims must not be inferred from repository code or unit tests alone.
