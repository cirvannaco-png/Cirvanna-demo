# ADR-0005: Xari-assisted discovery, Complementer collaboration and marketplace Try-On

**Status:** Accepted — product and service ownership decision. Runtime completion remains gated.
**Date:** 4 November 2026

## Context

Cirvanna has separate foundations for conversational discovery (`services/xari`), Complementer advisory styling, marketplace browsing, Virtual Twin and Virtual Try-On. The canonical product name is **Xari**. Tari is a legacy name in the preserved source lineage and must not become a second assistant or take over the product-facing identity. Marketplace search currently returns candidate matches pending CAL; it is not yet a complete price-comparison journey. Product-card Try-On is present but disabled because the renderer and secure adapters are not configured.

Public-name reconnaissance on 4 November 2026 found existing uses of both Xari and Tari. Xari is used by an AI marketing/SEO product and appears in an existing cosmetics/perfumery trademark record; Tari is used by an African business-software and fintech brand and appears in other trademark records. This is not legal trademark clearance. Cirvanna retains Xari as the product decision, subject to a jurisdiction- and category-specific trademark review before commercial launch.

Adding duplicate assistant services or allowing the assistant to own product, price or fit truth would increase coupling and weaken the existing domain boundaries.

## Decision

### 1. Xari is the single canonical assistant

Xari is the canonical product-facing assistant and orchestration identity. The existing `services/xari` path and `XARI_API_TOKEN` / `XARI_API_URL` configuration remain canonical. `TARI_API_TOKEN` / `TARI_API_URL` are compatibility fallbacks only; the capability response names Xari as canonical and Tari/Xyra as legacy names. Do not create or deploy a second Tari assistant.

Xari is optional and user-invoked. It is available as a discovery/help entry point in Marketplace and may be offered from the Experience, Virtual Twin and Virtual Try-On surfaces. A user can browse, use Twin and use Try-On without invoking Xari.

### 2. Complementer is an optional advisory collaborator

Complementer is available to Xari as an optional styling capability. Xari may call it when the user asks for look coordination or enables styling help; it is not a mandatory step for search, product display or Try-On. The same advisory capability may be surfaced as an optional action within Twin or Try-On.

Complementer owns styling advice only. It does not own the user's canonical style profile, hard exclusions, products, variants, offers, prices, inventory, fit evidence or product-display decisions. It must not invent SKUs, merchant names, stock, prices, purchase links or claims of fit. USI owns positive preferences, NPL owns hard exclusions, TAL owns consented learning events, Catalog owns product identity and metadata, Commerce owns offers and transactions, FCI owns calibrated fit evidence, and CAL remains the only product-display authority.

Complementer must not be required for baseline Xari search or marketplace browsing. Its output is explainable and reversible; a rejected suggestion is a soft observation, not an automatic NPL veto.

### 3. Marketplace discovery and price comparison

The marketplace must expose an Xari natural-language search entry point. Users may describe the product or look they want in their own words and optionally supply explicit constraints such as category, currency-scoped budget, colour, climate, occasion, size or exclusions. Xari may clarify only when required; it must not infer sensitive cultural or identity attributes from appearance, name or location.

The complete discovery flow is:

1. Xari interprets the user's description and explicit constraints.
2. Retrieval searches canonical active Catalog products and current, purchasable Commerce offers. Semantic/vision retrieval can rank candidates but cannot replace canonical product/offer records.
3. Offers are joined to products by exact canonical product and variant identifiers. Orphan, inactive, out-of-stock or unapproved merchant offers are excluded.
4. Where multiple merchants offer the same product/variant, the marketplace compares live offer prices within the same currency and shows the merchant, currency, stock/availability and offer observation time.
5. Different currencies are not compared without a separately sourced, timestamped exchange-rate service. Merchant price is not described as total checkout cost unless shipping and tax are included.
6. Every candidate passes NPL and explicit cultural requirements and then CAL. Only a CAL `SHOW` result may expose product and offer details. `BLOCK`, `REVIEW`, missing evidence and pending decisions remain hidden.

Similarity and preference-ranking scores are not probabilities, fit-confidence estimates, or display authorization. Product facts, merchant details, currency, price and stock are retrieved from Catalog/Commerce; Xari and Complementer must never generate them.

### 4. Virtual Try-On is a marketplace product action

Marketplace product cards are the first-class entry point for trying a selected catalog product before purchase. The Try-On action should be visible on eligible product cards and enabled only when the user is authenticated, a user-owned Twin and trusted person/product assets can be resolved, active server-side consent is verified, and the Virtual Try-On service confirms a validated renderer is ready.

The browser must call the same-origin Marketplace BFF. The BFF derives the subject from a verified Commerce identity and keeps service credentials server-side. The renderer accepts trusted opaque asset references; it must not accept arbitrary caller URLs or cross-tenant asset identifiers. Client checkboxes and client-supplied user IDs are not proof of consent or identity.

Xari may optionally guide the Try-On journey. Complementer may optionally suggest styling or pairings. Both are outside the rendering, consent and asset-authorization trust boundary. Neither may bypass policy or turn a visual preview into a fit guarantee. FCI remains the separate owner of calibrated fit confidence; CAL governs product display.

Until renderer, consent verifier, asset authorizer, user-owned Twin and BFF integration are verified, the product-card action must remain visibly unavailable/disabled. Do not render synthetic try-on images, fake a successful result, or imply that the current pose-skeleton output is a persistent complete Twin.

### 5. Virtual Twin remains independently usable

Xari is an optional conversational guide inside the Twin experience. Complementer is optional styling help. Neither is required to create, view or manage a Twin. Twin owns its user-scoped representation, consent and asset authorization; the current pose-skeleton response must not be marketed as a persistent avatar or calibrated measurement model.

## Required acceptance criteria before claiming full integration

- [x] Xari is the canonical name in the assistant capability contract.
- [x] XARI environment names are preferred while Tari remains a compatibility fallback only.
- [x] Marketplace discovery UI presents Xari as the natural-language assistant entry point.
- [x] Complementer is defined as optional styling advice, not product or price authority.
- [x] Marketplace Try-On remains visible but disabled while secure rendering prerequisites are absent.
- [ ] Xari search calls the canonical Catalog/Commerce discovery path and returns current offer data only after CAL `SHOW`.
- [ ] Multi-merchant offer comparison groups exact product/variant matches and compares only like currencies with timestamped source data.
- [ ] Complementer has an authenticated, optional handoff from Xari and optional Twin/Try-On UI entry points; no duplicate profile or product store is introduced.
- [ ] Marketplace BFF exposes a user-authenticated Try-On capability/request contract backed by verified identity, server-side consent, Twin ownership and asset authorization.
- [ ] A pinned and licensed renderer is deployed and independently evaluated across supported garment categories, body representations, devices and lighting.
- [ ] Browser E2E, service contract, privacy, security, model-quality, latency/cost and production smoke tests pass before enabling Try-On.

## Implementation status and release truth

This change establishes the canonical naming contract, compatibility path, marketplace Xari entry point, service ownership documentation and regression tests. It does not claim to complete live price comparison, Complementer runtime orchestration, persistent Twin storage or Try-On rendering. Those remain explicit follow-up implementation and release gates. Production readiness must not be inferred from this ADR or from passing unit tests.