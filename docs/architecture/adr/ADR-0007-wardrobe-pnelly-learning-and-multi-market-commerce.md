# ADR-0007: Wardrobe intelligence, EEPL context and multi-market commerce

**Status:** Proposed — requirements captured for implementation review; no production behaviour is enabled by this ADR alone.
**Date:** 4 November 2026
**Related:** #82, #85, #89, #93, #94

## Context

Cirvanna has a Wardrobe domain and authenticated Wardrobe API, but its current responsibility is limited to user-owned item records and lifecycle management. It does not yet provide a PNELLY companion surface, recommendation feedback loop or a verified Wardrobe-to-assistant integration.

The repository also contains a deterministic EEPL policy kernel and a separate USI/TAL persistence service. Their presence does not establish a live PNELLY integration. EEPL currently returns PASS, BLOCK or REVIEW; it is not a relevance-ranking model.

Commerce currently models a merchant's country, one price currency per variant and offer observation time. It does not yet represent a merchant's distinct brand home country and legal country, operating markets, localized prices, sourced FX quotes, fulfilment quotes, market-specific taxes or payment-provider capability. The current Brand Partner Portal exposes only a single merchant country field and a single variant price/currency input.

The recently merged Catalog/Commerce canonical-variant and observation-time foundation is necessary but insufficient for reliable cross-market total-cost comparisons.

## Decision

### 1. PNELLY belongs inside Wardrobe as a persistent companion

- Wardrobe will expose PNELLY as a first-class, contextual assistant surface in the user's closet, as well as from the Marketplace and other supported surfaces. This is one assistant capability, not a second independent assistant service.
- PNELLY reads only the authenticated user's active, authorized wardrobe records through the Wardrobe service. Trusted ingress binds the verified identity to the subject; arbitrary client-supplied owner IDs are never trusted.
- Recommendations use the user's existing items to compose outfits, identify wardrobe gaps, avoid redundant purchases and explain which owned items support each suggestion.
- Inputs may include user-declared item attributes, explicit saved outfits, supported purchase history and purpose-scoped user-approved images. This is not permission for background camera observation or silent image processing.
- User interactions are distinct evidence types: approve, reject, modify, save outfit, explicitly record wear and correct an earlier observation. Recommendation exposure alone is not proof of preference.
- Persisted learning is user-scoped, consented, versioned, idempotent, correctable, revocable, exportable and deletable. Positive preference evidence flows to USI/TAL; explicit hard exclusions remain owned by NPL. An inferred signal must not silently become an explicit user preference.
- PNELLY may suggest both combinations from owned clothing and additional products to complete a wardrobe. Product identity, merchant, offer price, currency, stock and availability must come from Catalog/Commerce—not generated assistant text.
- Marketplace recommendations retain the configured local-discovery behaviour: start within a 30 km radius, allow a user-selected wider radius, and surface any applicable transport/delivery charge before describing an option as lower-cost.

### 2. EEPL supplies context and eligibility to PNELLY; it does not rank

- PNELLY consumes a structured EEPL envelope containing the policy verdict, reason codes and the minimum relevant context needed for the current recommendation (for example, declared occasion and sufficiently fresh, consented location/climate context).
- Changing context carries source/provenance, observation time and freshness. Missing or stale required inputs remain unknown; a failed upstream context provider must not be replaced by guessed weather or location.
- EEPL BLOCK is a hard veto. EEPL REVIEW is an abstention state and cannot be presented as approval. EEPL PASS only satisfies the configured EEPL policy.
- PNELLY may rank only after EEPL passes, and all later controls remain mandatory: NPL hard exclusions, explicit cultural requirements, applicable CAL SHOW, current Catalog/Commerce offer validity and separate FCI evidence where fit claims are made.
- Do not infer age, cultural identity or other sensitive attributes from images, appearance, names or location. Use only the minimum declared or verified context required by a versioned policy.

### 3. Brand identity and market coverage are separate facts

The merchant onboarding contract will distinguish:
- brand home/origin country;
- legal entity registration country;
- one or more operating/selling markets, each with its own activation/review status.

The existing merchant country field is legacy data until a reviewed migration establishes its meaning. It must not silently be reinterpreted as both brand origin and legal country.

Market activation requires the relevant merchant verification, fulfilment, tax and payment capabilities to be available for that market. An operating-market declaration alone does not prove regulatory, tax or payment readiness.

### 4. Product, offer and display currencies remain distinct

- A merchant may declare a product/source currency and independently select the currency in which an offer is actually transacted.
- The charged offer amount/currency is the source commercial fact for that offer revision. Preserve it with its source and revision.
- Consumer display currency and locale are separate presentation choices, normally based on the user's selected market/preferences. Localized formatting must use the currency's actual minor-unit exponent; do not assume all currencies use two decimal places.
- FX conversion is a derived, time-bounded quote. It records the currency pair, rate, provider/source, quote identifier, observation time, expiry, rounding rule and any spread/fee. It never overwrites the merchant's source price.
- When FX is missing, stale, invalid or for the wrong pair, show the original amount and currency or state that conversion is unavailable. Do not invent a rate or imply that a displayed estimate is the payable checkout amount.

### 5. Fulfilment, transport, tax and payment are first-class offer context

- Support distinct fulfilment modes: shipping, courier delivery, merchant delivery, collection/pickup and local transport.
- Each applicable charge is destination/service-area bound and carries amount, currency, provider/source, estimate-versus-confirmed status, observation time and expiry. Alternative fulfilment modes are alternatives; they are not summed together.
- Distance-based transport quotes disclose distance, coverage and price. Expanding the user's local search radius must not hide the incremental transport/delivery charge.
- Tax is market/jurisdiction-specific and must retain tax category, inclusive/exclusive basis, amount/currency, calculation provider or approved rule version, timestamp and authoritative-versus-estimate status. Unknown tax remains unknown; no generic rate is guessed.
- Market-specific payment capability records identify supported markets, transaction currencies, payment methods, settlement currencies, merchant onboarding/readiness requirements and provider provenance. Checkout is blocked when the chosen provider cannot support the selected market and currency.

### 6. Comparison is a like-for-like landed-cost calculation

A comparison record must preserve canonical Catalog product and variant identity, merchant-local source identifiers, merchant and brand provenance, destination market, offer currency, localized/converted display price and FX provenance, stock and observation time, selected fulfilment mode and charge quote, tax basis/state, payment capability and source timestamps.

Two offers may be compared only when:
1. they share the exact canonical variant ID;
2. they target the same destination market and fulfilment destination;
3. their stock/availability and source observations are current;
4. the selected fulfilment basis is compatible;
5. source currencies match, or each offer has a valid, fresh FX quote to the same display currency.

A total-cost comparison additionally requires equivalent item-price, selected fulfilment-charge and tax treatment. If those inputs are incomplete or incomparable, the system must return comparison unavailable or explicitly label an item-price-only comparison. It must never label a partial amount the cheapest total or a landed price.

## Ownership boundaries

| Concern | Owner |
|---|---|
| User wardrobe records and item lifecycle | Wardrobe service |
| Assistant orchestration and conversational experience | Existing assistant runtime; proposed PNELLY brand remains subject to #81 |
| Explicit positive style preferences | USI |
| Consented temporal interaction/learning events | TAL |
| Explicit hard exclusions | NPL |
| Eligibility and environmental policy verdict | EEPL |
| Canonical product/variant identity and product metadata | Catalog |
| Merchant, offers, transactional currency, stock, fulfilment, tax/payment capability and orders | Commerce |
| Final product display authorization | CaTaCaCi/CAL |

No duplicate wardrobe, profile, product, offer, currency or policy source of truth is introduced.

## Release gates and sequencing

1. Resolve the data contracts and implementation boundaries through #93 and #94.
2. Complete #85's pairwise offer comparison gate, extending it with FX, market, fulfilment and tax equivalence.
3. Implement the Wardrobe/assistant and EEPL context contracts with consent, subject-binding and regression tests.
4. Extend merchant onboarding, Commerce storage, pricing/FX/fulfilment/tax/payment capability and comparison contracts with versioned migrations and backward-compatible legacy states.
5. Complete #89's production consent, private storage, tenant isolation, backup/restore and live integration/security gates before enabling any user-facing production capability.

This ADR does not authorize a database plan, paid infrastructure purchase, production migration, deployment, market activation or feature-flag enablement. Existing infrastructure provisioning remains on hold until schema ownership, provider requirements, budget and release evidence are reviewed.

## Verification requirements

- Wardrobe access tests prove strict subject isolation.
- Learning tests cover consent, event idempotency, correction, revocation, export and deletion.
- EEPL integration tests cover BLOCK, REVIEW, PASS and stale/missing context without fallback guessing.
- Currency tests cover zero-, two- and three-decimal exponent currencies; FX tests cover missing, stale, wrong-pair and provider failure.
- Fulfilment tests prove that alternative modes are not double-counted and quotes are destination-bound.
- Tax/payment tests prove unknown tax is not fabricated and unsupported market/currency combinations cannot check out.
- Comparison tests prove canonical-variant, market, destination, stock, currency/FX, fulfilment and tax compatibility.
- Checkout revalidates payable amount, currency, fulfilment and taxes against the authoritative quote before creating a payment session.
- CI and contract tests do not substitute for deployed-provider, backup/restore, privacy or independent security verification.
