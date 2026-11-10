# Cirvanna Complementer — Personal Aesthetic Intelligence

**Status:** expanded deterministic advisory composer and feedback-event contract implemented in code. Durable profile memory, production gateway hydration, live product retrieval, and skin-state forecasting are not implemented by this service.

Complementer coordinates a complete look without treating the user's existing identity as something to replace. The API is an internal advisory boundary; it does not authorize catalogue display or purchase.

## Capability domains

- **Fragrance direction:** perfume families, scent profiles, occasion, desired longevity, intensity, and a currency-scoped budget. Longevity is a preference target, not a guarantee about actual wear time. Fragrance-free and user-declared sensitivity settings suppress scent suggestions.
- **Colour intelligence:** coordinates clothing, makeup, jewellery and accessory colours. Explicit favourites and exclusions take precedence over curated palette pairings. It does not infer skin tone or undertone from images.
- **Jewellery and accessories:** earrings, necklaces, glasses, metals and user-selected accessory categories. A self-reported face shape is optional; the service does not infer face geometry from images.
- **Aesthetic direction:** minimalist, elegant, classic, romantic, bold, streetwear, editorial, natural and bohemian directions. A cultural direction requires a user-selected cultural context; appearance, name and location are never used to infer culture.
- **Look completion:** proposes at most two optional finishing changes and explicitly preserves the chosen silhouette, identity and existing statement pieces.
- **Explainability:** each domain returns the preference or current-look context that explains why a suggestion was made.

## Checkout preference learning contract

The checkout-learning module defines a versioned TAL handoff for explicit checkout choices. It can represent selected offers, selected fulfilment, selected payment-method family, explicit item removal/replacement reasons, and a verified paid-order event.

- Checkout remains user-directed. Cirvanna never chooses or changes the merchant, variant, quantity, fulfilment, payment method, or final confirmation on the user's behalf.
- The event builder requires an already verified, subject-bound personalization consent receipt. A client boolean alone is not sufficient evidence; the future gateway integration must verify the receipt with the canonical Identity Learning/consent owner.
- Events carry only allowlisted identifiers, ISO currency and integer minor-unit price/total values, selected fulfilment mode, payment-method family, and explicitly supplied removal reasons. They exclude email, address, payment credentials/tokens, bank-account details, free-form notes and raw cart snapshots.
- Every observation is weak evidence. A paid order is a verified transaction, not proof of enduring aesthetic preference. A removed item is not a dislike unless the user explicitly supplies a reason; abandonment, cancellation and payment failure are deliberately not accepted as negative preference signals.
- Events cannot create NPL hard vetoes or silently mutate explicit USI preferences. TAL persistence, idempotent delivery, correction, revocation, export and deletion remain integration requirements; this module is a contract, not proof of durable learning.

## API

### `POST /v1/complementer/recommend`

Requires internal bearer authentication using `COMPLEMENTER_SERVICE_TOKEN` (at least 32 UTF-8 bytes). The request includes an opaque user identifier, declared preferences, and current-look context. It returns style directions only; it does not invent product names, SKUs, prices, stock or purchase links.

### `POST /v1/complementer/feedback`

Accepts an approval/rejection observation only when `consent_to_personalization=true`. A user may explicitly ask to save the observed value as a preference. Rejections are represented as **soft preference observations**; they do not create NPL hard vetoes or permanent exclusions.

The endpoint currently returns a versioned event for handoff to the canonical CaTaCaCi/TAL owner. It does **not** persist that event or provide durable cross-session memory. The response reports `durable_persistence=not_configured`; do not present this handoff as completed preference learning.

### Operations

- `GET /health`: liveness only.
- `GET /ready`: checks the internal service token; it does not claim profile, catalogue or memory readiness.
- `GET /capabilities`: reports implemented and unavailable capabilities.

## Ownership and integration boundaries

- **Complementer:** composes advisory look suggestions from trusted, explicit profile and current-look data.
- **USI:** interprets positive style preferences. Complementer must not create a second user-style profile.
- **NPL:** owns hard negative preferences. Complementer cannot weaken or bypass an active exclusion.
- **CaTaCaCi/CAL:** sole final authority for displaying catalogue candidates. Retrieval and Complementer ranking are not display authorization.
- **TAL:** owns consented, versioned preference-learning events. This service emits a handoff contract; durable storage and profile hydration remain integration work.
- **Catalog:** canonical product identity, metadata and version history. Product details, current price and availability must be retrieved from Catalog/Commerce rather than generated by Complementer.
- **DermalSight:** owns non-diagnostic cosmetic skin-attribute inference. Longitudinal skin-state forecasts are not generated by this service.

Do not expose the request's `user_id` as a public trust boundary. The gateway must bind the subject to a verified authenticated principal and hydrate preferences server-side. No face image or video is accepted here.

## Privacy and user control

- Use only user-entered or explicitly selected context.
- Do not infer gender, ethnicity, religion, culture, modesty, skin tone, undertone or face shape from a face, name or location.
- Avoid storing raw face media or sensitive context in this service.
- Feedback is not accepted for learning without explicit consent.
- A rejection is reversible and non-binding; an explicit user hard exclusion remains owned by NPL.
- Users must be able to inspect, correct and delete durable preferences through the canonical identity/profile owner before this is exposed as a persistent-memory feature.

## Validation

From this directory:

```bash
python -m pip install -r requirements.txt
python -m pip check
python -m compileall -q app tests
python -m pytest -q
```

Catalog validation is tested separately from `services/catalog-service`. Passing isolated service tests does not prove gateway hydration, persistent memory, end-to-end CAL gating, production deployment or marketplace correctness.

## Not yet implemented

- User-facing preference editor and UI integration.
- Trusted gateway binding and profile/USI/NPL/cultural-declaration hydration.
- Durable TAL persistence, event replay, user correction/export/deletion lifecycle and cross-session memory.
- Live Catalog/Commerce retrieval, ranking against evidence-backed product intelligence, and exact candidate-bound CAL display authorization.
- Validated longitudinal skin-response model, representative data, calibration, and opt-in scenario forecasting.
- Production deployment, observability, rate limits, threat review and end-to-end staging validation.
