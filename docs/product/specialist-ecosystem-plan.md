# Cirvanna Specialist Ecosystem — Architecture and Delivery Plan

- Status: Implementation candidate on this branch; CI has not produced a successful execution; no production/storefront certification implied
- Date: 2026-10-24
- Target: `cirvannaco-png/Cirvanna-demo`
- Branch: `feature/specialist-ecosystem-foundation`

## 1. Product direction

Evolve Cirvanna toward a coordinated personal-appearance intelligence platform. The specialist ecosystem has seven distinct domains (implementation state is recorded in specialist-capability-audit.md):

1. Hair
2. Face and facial styling
3. Skin analysis
4. Complete look / personal styling
5. Footwear
6. Makeup
7. Skincare (ingredient/routine/product compatibility, distinct from skin analysis)

These are domain capabilities under one product experience, not seven independent recommendation engines. The user should be able to request a complete look while retaining control over identity, preferences, budget, occasion, consent, and hard exclusions.

## 1A. Current implementation boundary

The candidate branch now contains executable Python library code for the seven-domain registry, catalog-backed candidate evaluation, an authenticated NPL preference adapter, the internal catalog/NPL orchestrator, CAL arbitration, and deterministic Look + Makeup composition. The Catalog Service and NPL Service remain the respective sources of truth through read-only adapters. This is not yet a complete storefront integration: no public orchestrator route, authenticated HTTP identity binding, durable decision-audit receipts, checkout revalidation, production safety/legal/fit evidence providers, or validated image/model providers are enabled. The latest GitHub Actions runs terminated before job steps started (no runner was assigned), so this branch has no confirmed green CI result yet. See specialist-capability-audit.md for the exact capability inventory and limits.

## 2. Non-negotiable architecture rules

- **CaTaCaCi / CAL remains the sole final display-arbitration authority.** A specialist may provide evidence or a candidate; it cannot independently authorize display, checkout, or override a CAL BLOCK or REVIEW result.
- **NPL hard negatives are global constraints.** A rejected item or declared dislike must not re-enter through another specialist or the complete-look composer. An absent/unavailable preference snapshot is UNKNOWN, not an empty preference set, and cannot authorize display.
- **No duplicate product source of truth.** Specialists consume the canonical catalog/product contracts; do not create specialist-owned product tables or competing catalog identifiers.
- **Evidence before claims.** A module is not called live until its provider, model/assets (if any), permissions, quality evaluation, latency, failure behavior, and integration tests are demonstrated.
- **No sensitive inference from images.** Do not infer race, ethnicity, religion, health diagnoses, or other sensitive identity attributes. Cultural requirements must be user-declared or otherwise explicitly consented and governed.
- **Consent and data minimization.** Store only data needed for a stated feature; document retention/deletion, purpose, and access boundaries. Face/skin imagery and derived measurements require explicit purpose and careful access control.
- **Graceful partial results.** If one specialist is unavailable, report the missing domain and return only a clearly labelled partial result if CAL's policy permits. Never fabricate a successful analysis.
- **No forced purchase.** Recommendations remain optional; product ranking must not override user constraints or disguise sponsored placement.

## 3. Shared specialist contract

Every specialist should implement a versioned interface with the following conceptual input:

- `request_id`, `user/profile reference`, and `consent scope`
- `domain` and `contract_version`
- user-declared preferences, hard exclusions, budget, occasion, and context
- candidate catalog IDs and evidence references, where applicable
- data/model/policy versions and request deadline

Every specialist response should include:

- `status`: `OK`, `INSUFFICIENT_EVIDENCE`, `UNAVAILABLE`, or `ERROR`
- structured candidate/evidence references (not an untraceable prose-only verdict)
- confidence/calibration metadata only when supported by evaluation
- known incompatibilities and missing evidence
- provenance, timestamps, and contract/model version
- explicit statement that the result is **not** final display or purchase authorization

Do not treat confidence as policy approval. Missing, stale, unsigned, or contradictory evidence must lead to review or rejection according to the canonical CAL contract.

## 4. Responsibilities by specialist

### Hair
- User-selected texture, style, length, color, maintenance, and budget preferences.
- Hairstyle discovery and preview only where an evaluated visual provider exists.
- Haircare product information with ingredient/sensitivity evidence where available.
- Do not claim precise hair-texture classification or realistic virtual results without validation.

### Face and facial styling
- Face-aware styling for hairstyles, eyewear, facial hair, and accessories where the user opts in.
- Use only measurements necessary for the selected task; explain uncertainty.
- Do not rank facial features against a universal beauty standard or infer sensitive identity.

### Skin
- Extend the existing DermalSight/Xari direction only after auditing canonical ownership and actual provider availability.
- Separate cosmetic appearance observations from medical diagnosis.
- Include image-quality checks, uncertainty, consent, and safe escalation for concerning symptoms.
- Product compatibility requires ingredients and user-declared sensitivities; image analysis alone cannot establish safety.

### Skincare
- Keep skincare product discovery separate from image-based cosmetic skin analysis.
- Match routines/products only against verified catalog fields and explicit user declarations (for example, declared skin type, ingredients to avoid, budget, and routine step).
- Do not infer allergies or ingredient compatibility from an image, and do not guarantee safety without authoritative ingredient evidence and a reviewed compatibility policy.
- Do not diagnose conditions or prescribe treatment; missing ingredient data or uncertain compatibility must remain unresolved rather than being presented as safe.

### Look / complete-look composer
- Orchestrates hair, makeup, clothing, footwear, and accessories for an occasion and budget.
- Applies cross-category color/style compatibility as explainable evidence, not as a substitute for user preference.
- Checks budget totals, availability timestamps, duplicate items, and missing category coverage.
- Returns a complete look only after each candidate has passed canonical constraints and CAL arbitration.

### Footwear
- Matches footwear to outfit, occasion, declared comfort/fit needs, price, and availability.
- Distinguishes catalog size/fit evidence from inferred fit; do not guarantee comfort or sizing without evidence.
- Respect excluded shoe types, materials, brands, and price limits across all composer flows.

### Makeup
- Supports user-directed looks and product discovery, including shade matching only when suitable product shade data and evaluated image conditions exist.
- Account for lighting, camera, undertone uncertainty, and catalog shade quality.
- Ingredient/sensitivity matching uses authoritative product data and user declarations; do not promise that a product cannot cause a reaction.

## 5. Shared decision flow

1. Obtain user intent, preferences, budget, context, and required consent.
2. Retrieve candidates from the canonical catalog and relevant profile/wardrobe services.
3. Load the authenticated user's canonical NPL state; missing or cross-user state fails closed. Apply eligibility, consent, declared cultural constraints, and NPL hard negatives.
4. Request evidence from only the specialists required by the task.
5. Validate contract versions, provenance, freshness, and evidence completeness.
6. Compose candidates and cross-category compatibility evidence.
7. Send each proposed display candidate through the canonical CaTaCaCi/CAL pipeline.
8. Display only `SHOW`; suppress `BLOCK`; hold `REVIEW` or insufficient/stale evidence. Never bypass this result at checkout.
9. Revalidate catalog availability, price, constraints, and CAL decision at checkout; record an auditable decision receipt.
10. Collect feedback only with the appropriate consent; update preference state through the existing governed learning path, never by silently weakening hard negatives.

## 6. User experience

Provide one entry point such as **Build my look**, with optional specialist controls:

- Hair
- Face
- Skin analysis
- Skincare
- Outfit / Look
- Shoes
- Makeup

Users can ask for one domain or a coordinated result. Explain why candidates were suggested, identify missing evidence, show price and availability freshness, and let users change or remove any component. Do not require users to upload face or skin images when declared preferences and catalog data are sufficient.

## 7. Delivery sequence

### Phase 0 — Repository and ownership audit
- Map existing code and contracts for Xari, DermalSight, Virtual Twin, wardrobe, catalog, NPL, USI, EEPL, fit evidence, and CAL.
- Resolve canonical names and duplicate adapters before extending them.
- Record which providers and models are executable versus scaffold/documentation only.
- Baseline current CI and preserve all unrelated work.

### Phase 1 — Contracts and deterministic orchestration
- Define shared request/response schemas and stable reason codes.
- Implement a specialist registry with fail-closed behavior for missing handlers.
- Add a deterministic complete-look composer that consumes catalog fixtures and declared preferences only.
- Enforce NPL exclusions and CAL decisions at the final output boundary.
- No fabricated visual inference, product availability, fit, or skin analysis.

### Phase 2 — First useful vertical slice
- Start with Look + Makeup using verified catalog metadata and explicit user preferences.
- Demonstrate request → catalog candidates → constraints → specialist evidence → CAL verdict → auditable response.
- Keep unavailable providers explicitly unavailable; allow a clearly labelled non-image workflow.

### Phase 3 — Hair and footwear
- Add contract-compatible providers and evaluation sets.
- Test category coverage, hard-negative propagation, price/availability changes, and partial provider failure.

### Phase 4 — Face and skin
- Enable image-dependent capabilities only after consent UX, secure image handling, quality/rejection evaluation, privacy review, and accuracy limits are documented and tested.

### Phase 5 — Visual try-on and personalization
- Integrate Virtual Twin / try-on only after asset provenance, model availability, visual quality, latency, and failure behavior are verified.
- Validate performance across diverse skin tones, hair types, lighting, devices, and regional product catalogs.

## 8. Required test gates

### Contract and unit tests
- Each domain returns valid, versioned responses and stable reason codes.
- Missing handlers, malformed responses, stale evidence, and timeouts fail closed.
- NPL hard negatives cannot be reintroduced by any specialist or composer.
- CAL `BLOCK` and `REVIEW` results are never shown as approved recommendations.
- Budget totals and per-item constraints are correct; unknown prices are never represented as confirmed totals.
- Partial results clearly identify unavailable domains.

### Integration and security tests
- Canonical catalog identifiers only; no shadow product database.
- User/tenant isolation for profiles, images, wardrobe, preferences, and audit records.
- Consent revocation prevents further use of affected data.
- Checkout revalidates price, availability, hard constraints, and CAL decision.
- No secret values, image payloads, or sensitive attributes in ordinary logs.
- Provider errors cannot trigger fallback to an unvalidated or permissive decision path.

### Quality and release evidence
- Publish per-domain dataset provenance, sample sizes, acceptance thresholds, rejection rates, latency/resource measurements, and uncertainty.
- Test representative and difficult inputs (blur, darkness, occlusion, irrelevant images) for image-dependent providers.
- Use held-out evaluation data; do not tune and report on the same set.
- Record commit SHA, commands, CI run URL, test counts, and actual pass/fail output.
- Do not label the platform production-ready from unit tests alone.

## 9. Initial acceptance criteria

The first milestone is complete only when:

- The canonical architecture and ownership map is approved.
- Shared specialist contracts and deterministic registry have executable tests.
- A fixture-backed Look + Makeup vertical slice returns explainable candidates.
- NPL exclusions and CAL decisions are demonstrably enforced.
- Missing/failed specialists produce honest partial/unavailable results.
- CI executes the new tests on the intended pull-request branches and records actual results.
- No new product database, unverified model claim, production endpoint, or checkout bypass is introduced.

## 10. Explicit non-goals for the first milestone

- Building six separate AI models from scratch.
- Claiming clinical skin diagnosis or guaranteed product suitability.
- Shipping realistic try-on before model/assets and quality have been validated.
- Migrating or exposing brand authentication routes as part of this feature.
- Merging directly into `main` or promoting a scaffold to production without review and CI evidence.
