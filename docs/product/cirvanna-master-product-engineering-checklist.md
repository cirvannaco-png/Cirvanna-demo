# Cirvanna master product and engineering checklist

**Baseline:** `main` at `5604cf57cd7f0805e28b5af33e7011d7da596d06` (7 November 2026)  
**Status:** Active; the product requirements are captured below. This is not a production-readiness declaration.

## Operating rules

- Track the whole product, not isolated demos. A task is complete only when its acceptance criteria pass at the correct level (unit, contract, integration, deployed or physical-device).
- Keep the two-step product plan: **Step 1 — foundation and ownership**; **Step 2 — intelligence and connected experience**. Workstreams may progress simultaneously when contracts and dependencies permit.
- Do not make the personal wardrobe the universal source of truth. A new user with an empty wardrobe still receives useful, non-fabricated recommendations from their declared identity/style profile and context. Once the user adds items, the wardrobe is authoritative for what they own and wear.
- Preserve domain ownership: Identity/USI owns declared style profile; Wardrobe owns user-owned item records and wear history; Catalog owns canonical product identity and product facts; Commerce owns merchant offers, prices, stock, orders and payment state; NPL owns hard exclusions; USI/TAL owns positive preference/learning observations; the canonical decision/CAL layer owns final product display authorization; Virtual Twin owns the user's authorized Twin record/assets; DermalSight owns non-diagnostic cosmetic skin signals.
- A product being browsed, saved, shortlisted, placed in a cart, recommended or tried on is **not** wardrobe ownership. A confirmed purchase may be synchronized to the wardrobe only through a verified Commerce event and an idempotent ownership handoff; cancellations/refunds must reconcile the wardrobe state.
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
- [ ] Expand and validate an extensible category taxonomy for clothing, shoes/footwear, bags, jewellery, ties, glasses/frames, watches, accessories, makeup and other user-owned beauty products.
- [ ] Support user-added items with explicit provenance, optional photos, metadata correction and appropriate consent; do not silently turn image guesses into facts.
- [ ] Support safe archive, restore and deletion; ensure image/asset deletion is actually completed by the storage worker, not merely queued.
- [ ] Add import/bulk-add, duplicate detection and item merge/correction without silently merging distinct variants.

### 1.3 Wardrobe sync, purchase ownership and source-of-truth rules
- [ ] Define near-real-time sync for user-added/edited items and authorized brand/catalog changes, with explicit source, version, last-synced time and conflict handling.
- [ ] Sync a marketplace item into the personal wardrobe only after verified purchase/ownership confirmation; browsing, saved, cart, unpurchased or try-on products must never appear as owned.
- [ ] Reconcile purchase sync on payment confirmation, partial/full cancellation, refund, return and chargeback; preserve a truthful ownership/purchase state.
- [ ] Keep Catalog product facts canonical; Wardrobe stores canonical product/variant references plus user-specific notes and preferences, not a competing copy of merchant facts.
- [ ] Add replayable webhook/event tests for duplicate, delayed, out-of-order and failed sync events.
- [ ] Provide optional marketplace notifications for unowned products that complement an outfit; label them as suggestions/available-to-buy, never wardrobe items.

### 1.4 Commerce and marketplace transaction integrity
- [~] Commerce documents immutable checkout line snapshots, idempotent orders, inventory reservation and verified settlement; full customer cancellation/refund/return behaviour and deployed reconciliation still require verification.
- [ ] Enforce price integrity: merchant changes to a listing affect future offers only; checkout must bind an explicit quoted offer/version/expiry and revalidate before payment; once an order is accepted/paid, merchant edits must not rewrite the order's agreed line price or terms.
- [ ] Implement customer cancellation windows and state transitions, including partial cancellation where supported, stock release, payment void/refund, audit trail and clear merchant/customer permissions.
- [ ] Implement refunds, returns, disputes and webhook reconciliation without treating a browser redirect as proof of payment.
- [ ] Apply market, currency, tax, shipping/delivery fee, stock, seller eligibility, size/variant availability and fulfilment constraints to recommendations and checkout.
- [ ] Support the configured local discovery radius (30 km initial radius, user-expandable) without implying delivery availability; show delivery/transport fees and estimated availability where verified.
- [ ] Add offer freshness, price-history/provenance and stale-quote tests; preserve canonical product and cross-merchant variant identity.
- [ ] Keep product display gated by the canonical CAL decision; no search, sponsored, try-on or recommendation path may bypass BLOCK/REVIEW or missing evidence.

### 1.5 Consent, privacy and learning data rights
- [ ] Complete one coherent consent lifecycle for profile learning, wardrobe photos, skin analysis, body measurement, Twin storage, try-on rendering and image publication, with scope/purpose/resource binding.
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

### 2.4 Wardrobe intelligence, PNELLY, NPL, CFRP/CRFP and learning
- [~] PNELLY daily-look composition is implemented and CI-verified in merged PR #139 from authenticated Wardrobe snapshots through Decision Gateway to Complementer, with a Wardrobe UI. Marketplace, persistent Twin and multi-product try-on context handoff remain open.
- [~] Merged PR #139 records explicit worn/not-my-style feedback only with active style-learning consent; modify/save/search/purchase/return event coverage and durable outfit-graph attribution remain open.
- [~] Merged PR #139 keeps PNELLY soft feedback separate from NPL hard exclusions and adds user retraction; full end-to-end tests across every recommendation surface remain open.
- [ ] Connect wardrobe feedback to NPL and the repository's canonical fit/recommendation pipeline (CFRP/CRFP naming must follow the approved repository contract, not create a second system).
- [ ] Use explicit profile and wardrobe evidence to personalise recommendations; explain the reason, source and uncertainty.
- [ ] Implement a personal outfit graph: items, outfit combinations, times worn, last worn, frequency, user ratings and context, with privacy/consent controls.
- [ ] Use that graph to reduce repeated outfits and repeated combinations, improve wardrobe utilisation and rotate items fairly; never force an unsuitable outfit just to maximize usage.
- [ ] Add deterministic anti-repeat tests (same outfit, near-duplicate combination, cooldown, wardrobe changes, seasonal/context changes) plus a human-reviewed relevance/diversity baseline.
- [ ] Establish the human-reviewed outfit evaluation dataset; compare against a transparent baseline and measure relevance, diversity, exclusion violations, user edits, rejection and repeated-rejection rates.
- [ ] Measure whether recommendations improve user satisfaction and wardrobe utilisation; do not equate clicks or exposure with preference.

### 2.5 Complementer: suggestions and “Upgrade my look”
- [ ] Make Complementer optional and available from PNELLY, Virtual Twin, Virtual Try-On and relevant recommendation surfaces.
- [ ] Provide two explicit modes: **Suggestion mode** for small, reversible refinements and **Upgrade my look** for a deliberate, user-requested transformation.
- [ ] Explain proposed changes using the user's colour profile, declared preferences, proportions/fit evidence where validated, wardrobe, context and available products.
- [ ] Preserve identity, signature pieces, explicit exclusions and the user's chosen silhouette unless the user requests a change.
- [ ] Let users compare before/after, accept, reject, modify and undo each individual piece independently.
- [ ] Recommend actual marketplace products only from canonical Catalog/Commerce data and only after CAL authorization; never fabricate brand, SKU, price, inventory or delivery.

### 2.6 Connected Virtual Twin and multi-product try-on
- [ ] Establish one persistent, owner-scoped Virtual Twin registry, media-asset lifecycle, exact resource-bound consent and user deletion path.
- [ ] Distinguish pose-skeleton inference, body reconstruction, persistent Twin generation and preview as separate capabilities; report only what is actually available.
- [ ] Connect Wardrobe, PNELLY and Marketplace bidirectionally to the same Twin and try-on session without duplicate stores or user identity paths.
- [ ] Permit product selection from Marketplace and wardrobe selection from the personal closet; support searching for an exact product or a canonical purchasable variant in the Marketplace.
- [ ] Support multi-item try-on from either source (e.g. top + trousers + shoes + accessories) with slot validation, product/variant provenance and independent removal/replacement.
- [ ] Preserve the exact product's colour, pattern, design, cut, material appearance and variant through visualization; disclose unsupported rendering changes.
- [ ] Support complete user-created outfit combinations in the Twin/try-on, save them to the wardrobe/outfit graph and send consented feedback to identity/decision learning.
- [ ] Allow users to modify one selected piece in a saved look without regenerating or silently changing the rest.
- [ ] Integrate optional Complementer suggestions and Upgrade my look mode into Twin/try-on with per-item acceptance and comparison.
- [ ] Reduce latency through measured budgets, caching keyed by safe/versioned assets, progressive rendering and bounded worker queues; never serve one user's private render to another.
- [ ] Verify pinned model/source revisions, full weight manifests and SHA-256, licenses, runtime/provider availability, GPU/CPU behaviour, offline dependencies and image-size limits.
- [ ] Complete physical Android QA for camera permission, lifecycle/backgrounding, tracking stability, thermal/load behaviour, memory, low-end devices and network loss.

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
- [ ] Validate migrations, backup/restore, idempotent event replay, queue retry/DLQ and deletion completion in a non-production environment.
- [ ] Run actual Android-device acceptance tests in addition to browser automation.
- [ ] Add observability with privacy-minimized event IDs, reason codes and model/runtime provenance; never log raw image payloads or credentials.
- [ ] Produce a release evidence pack listing exact commit, tests, workflow run results, deployed environment, model versions, known limitations and rollback path.
- [ ] Do not declare Cirvanna production-ready until the critical provider, dataset, model, privacy, payment, migration, storage and device gates pass.

## Current verified baseline and immediate work

- [x] Repository inspected on 7 November 2026; active monorepo and service boundaries identified.
- [x] Versioned single-item Wardrobe edit API and authenticated UI controls merged in PR #128; its Wardrobe persistence and architecture checks passed.
- [~] DermalSight has a fail-closed ONNX adapter and signed release-evidence gate, but the trained/validated model and dataset are absent.
- [~] Commerce documents immutable checkout line snapshots and transactional payment/stock controls; cancellation/refund and deployment-level price-integrity verification remain open.
- [~] Wardrobe has authenticated persistence and feedback contracts; durable production DB, storage deletion worker and end-to-end integrations remain gated.
- [~] FCI contract exists; no independently validated calibrated provider or proven 4% measurement accuracy.
- [~] Virtual Twin exposes truthful capability boundaries; its persistent registry/asset/consent work is in open PRs and not yet a production capability.
- [x] Saved-outfit piece editing is implemented in merged PR #135; the user-declared colour preference profile is implemented in merged PR #137. PNELLY wardrobe companion, complete personal outfit graph, human-reviewed dataset, multi-product try-on, and end-to-end marketplace-to-wardrobe/Twin flows remain to be integrated and verified.
- [x] Merged PR #139 ports the PNELLY daily-look Decision Gateway route and consent/NPL checks onto current main; Decision Gateway tests passed.
- [x] Privacy/learning-data controls from stale PR #130 are integrated through PR #139. Confirm deployed migrations, deletion retry behaviour and production evidence before release.
- [ ] Reconcile existing open PRs and branches before creating parallel implementations. Preserve reviewable feature branches and never bypass CI or domain ownership.

## Required evidence for every completed checklist item

For each item marked [x], record: implementation commit/PR; affected contract/API/UI; unit and contract tests; integration or deployed evidence where required; model/dataset/version and license where relevant; performance cohort and metric where relevant; privacy/consent scope; unresolved limitations. Physical-device, deployed, empirical accuracy or production-readiness claims must not be inferred from repository code or unit tests alone.
