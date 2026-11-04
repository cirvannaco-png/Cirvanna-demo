# ADR-0006: PNELLY, DermalSight and distinct visual-discovery services

**Status:** Accepted product boundary; runtime completion remains gated  
**Date:** 4 November 2026  
**Supersedes:** Product naming and assistant presentation in ADR-0005. ADR-0005 remains historical for the Xari decision and technical lineage.

## Context

The canonical conversational assistant is now **PNELLY** (pronounced “Pinelly”). The prior assistant identity Xari is a migration/legacy name, not a second product. DermalSight must be experienced as a capability within PNELLY rather than as a separate assistant or parallel product-facing destination.

PNELLY needs conversational text discovery and conversational visual discovery. Cirvanna also needs a separate real-world visual-shopping service. These use cases share low-level vision and marketplace infrastructure but have different user intent, consent purpose, API contracts and service ownership.

## Decisions

### 1. PNELLY is the product-facing conversational assistant

PNELLY owns the conversational discovery experience, including:
- Describe It: natural-language product/look discovery.
- Look It: visual references supplied inside the PNELLY conversation.
- DermalSight: optional, consent-gated, non-diagnostic skin-analysis capability within PNELLY.
- Optional Complementer invocation for user-requested styling advice.

The internal DermalSight service boundary may remain independently deployed for model isolation, safety and lifecycle management. Its user-facing ownership is PNELLY. DermalSight must not be represented as a diagnosis, clinical forecast or medical compatibility result. No inference is available without a hash-verified model artifact and signed, independently validated model report.

PNELLY credentials prefer `PNELLY_API_TOKEN` and `PNELLY_API_URL`. Xari and Tari environment names may be accepted only as migration aliases. No duplicate Xari/Tari assistant should be deployed.

### 2. Look It belongs inside PNELLY and has its own image-search contract

Look It accepts hand-drawn sketches, saved/downloaded inspiration images and user-provided reference photos. PNELLY interprets the user's conversational intent, searches visually similar Catalog/Commerce candidates and explains uncertainty. It must not identify people or infer sensitive traits.

The implemented route boundary is:
- Marketplace BFF: `POST /api/vision/look-it`.
- PNELLY: `POST /v1/marketplace/search/image`.
- Private Vision Intelligence: `POST /v1/search/image`.

Look It requires server-verified `image_processing` and `look_it` consent scopes. The endpoint is distinct from Click It. Candidate search is not product-display authorization, match probability or fit evidence. NPL, explicit cultural requirements and CAL SHOW remain mandatory before product/offer details are shown.

The present Look It retrieval reuses low-level image embedding, active Commerce offers and Catalog enrichment. It includes an optional outfit-decomposition adapter, but no approved provider is currently provisioned. The adapter returns unavailable unless a trusted provider is configured with an exact model ID, exact full 40-character model revision, and matching validation-report SHA-256. The provider release must also pass source/license review, independent evaluation and operational security review before deployment. The provider response model ID and full revision must exactly match `OUTFIT_DECOMPOSITION_MODEL_ID` and `OUTFIT_DECOMPOSITION_MODEL_REVISION`; the validation-report SHA-256 must match its configured pin.

### 3. Click It remains an independent service and its API contract is preserved

Click It is real-world visual shopping: a user photographs a product in a mall/store or an outfit encountered in the real world. It is independent of PNELLY Look It.

Preserve the current contract:
- BFF `POST /api/vision/click-it`.
- Virtual Twin `POST /click-it`.
- Vision Intelligence `POST /v1/click-it/scan`.

Do not rename Click It, route Look It through its endpoint, reuse its consent purpose, or combine product telemetry. Shared model primitives are allowed only below the separate service/API and governance boundaries.

### 4. Live merchant comparison requires stronger Commerce identity

Visual/text similarity may identify candidates, but exact price comparison requires the same canonical product and canonical variant across merchants. Commerce must return a stable cross-merchant canonical variant identifier, current purchasable offer, merchant, currency, stock and an explicit observation timestamp.

The current Commerce offer response exposes merchant-local `variant_id` values and does not expose a trustworthy offer-observation timestamp. Therefore cross-merchant same-variant comparison remains unavailable. Do not infer equivalence from matching names, option strings, SKUs or embedding similarity. Do not compare unlike currencies without a separately sourced, timestamped FX rate, and do not claim landed price when shipping/tax are absent.

Even after those fields exist, NPL and explicit cultural requirements must be evaluated before CAL, and only CAL SHOW may reveal product and offer details. REVIEW, BLOCK or missing evidence stays hidden.

### 5. Complementer remains optional and advisory-only

PNELLY may invoke Complementer only when the user asks for styling assistance or explicitly enables it. Complementer cannot own Catalog product identity, Commerce offers/prices/stock, USI profile truth, NPL exclusions, FCI evidence or CAL display authority.

The existing API Gateway integration is a server-to-server advisory adapter. The current request model's `user_id` is not sufficient identity proof by itself. User-facing invocation remains disabled until the Gateway resolves the subject from the signed end-user authorization and checks it against the request. Rejected suggestions are not automatic NPL vetoes or durable memory.

### 6. Twin, Try-On, consent, assets and FCI remain fail-closed

Marketplace → Twin → Try-On is enabled only when all of the following are proven:
- Authenticated user identity and a persistent Twin owned by that user.
- Server-side active consent for the exact purpose, subject, resource and processing operation, with revocation checked at request time.
- Private assets resolved by opaque identifiers and authorized against subject, Twin and product, with tenant isolation.
- A real renderer with pinned source/model assets and independently validated output artifacts.
- Calibrated FCI estimate with evidence coverage, signed candidate-bound evidence, a distinct validation attestation and uncertainty/abstention behavior.
- CAL receives the trusted fit evidence and independently governs product display.

The current Virtual Twin produces pose-skeleton inference, not a persistent full avatar mesh. The consent verifier and Twin registry are external contracts and are not implemented/deployed in this repository. Virtual Try-On intentionally has no registered renderer, consent verifier or asset authorizer. The FCI gateway remains UNKNOWN when no validated provider is configured. Keep the Try-On action disabled until every gate is met. A visual preview is never a fit guarantee.

### 7. Image processing and privacy

Look It and Click It must retain distinct consent purposes and telemetry. Image processing is ephemeral by default. Validate actual file format, byte size, decoded dimensions and pixel count; decode to pixel data and strip metadata before inference; close uploads; do not persist source images or expose arbitrary remote URL fetching. Enforce short-lived private storage and deletion if later workflows require intermediate assets. Never perform person identification or sensitive-trait inference.

## Current implementation status

- PNELLY identity and PNELLY-preferred credential aliases: implementation in progress.
- Separate Look It BFF, PNELLY and Vision Intelligence endpoints: added on the feature branch; CI verification pending.
- Click It BFF endpoint, Virtual Twin path, Vision path and existing UI panel: retained as separate contracts.
- DermalSight: represented as a PNELLY sub-capability; real model readiness remains independently gated.
- Outfit decomposition: blocked pending validated model/provider.
- Same-variant live merchant comparison: blocked pending canonical cross-merchant variant identity and offer timestamp in Commerce.
- Complementer: advisory endpoint exists; verified end-user identity binding remains required before user-facing invocation.
- Persistent Twin, deployed consent verifier/Twin registry, real Try-On renderer, asset authorizer and calibrated FCI provider: not complete; keep disabled.

## Consequences

The experience can provide a separate PNELLY Look It candidate-search foundation without corrupting Click It's established contract. It cannot claim complete outfit decomposition, trustworthy cross-merchant price ranking, fit prediction or production-ready Try-On until the missing provider and data contracts are delivered and independently tested.
