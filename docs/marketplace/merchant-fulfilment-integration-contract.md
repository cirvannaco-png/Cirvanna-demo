# Merchant and fulfilment integration contract

**Status:** implementation contract; no provider is declared connected or production-ready.  
**Scope:** merchant onboarding, market activation, catalog/offer/inventory, fulfilment quotes and shipment lifecycle.

## Non-negotiable rules

1. A merchant is not active because a row exists. Activation requires human-reviewed legal/KYC evidence, approved categories, supported markets, verified payout capability and an audited decision.
2. A merchant's display name or claimed brand does not establish brand ownership, distributor status or authorization to sell a product.
3. Catalog ownership, merchant listing rights, inventory and market eligibility are separate assertions with separate evidence.
4. No stock, delivery method, price, tax, currency conversion or delivery date may be invented. Missing, stale, conflicting or unsupported evidence produces an unavailable reason.
5. Provider adapters are private server-side services. Credentials come only from the approved secret manager. Never expose provider tokens to browsers.
6. Every provider observation is timestamped, expiry-bound and traceable to a provider reference. Provider health alone is not proof that a quote or shipment operation works.

## Provider-neutral capability model

Each adapter must expose a versioned capability contract with:

- stable provider ID and adapter version;
- legal entity and operating-market scope;
- supported country/region and service-zone identifiers;
- supported currencies and payment/settlement methods where relevant;
- supported fulfilment modes: merchant delivery, courier, collection/pickup, or approved local transport;
- quote requirements, destination precision, package/weight/dimension requirements;
- rate/quote ID, charge basis, amount in minor units, ISO currency, tax treatment and expiry;
- serviceability result and explicit unavailable reason;
- shipment creation reference, label/tracking reference where applicable;
- lifecycle events with provider event ID, event time, received time and idempotency key;
- cancellation, failed delivery, return, refund and dispute capabilities;
- provider terms, retention, data region and subprocessor review status.

The adapter must reject unknown currencies, negative amounts, unsupported country/mode combinations, missing provider references, expired quotes and non-monotonic or duplicate lifecycle transitions.

## Merchant onboarding lifecycle

`draft → submitted → review → approved → active`  
Alternative terminal/restricted states: `rejected`, `suspended`, `revoked`.

Required evidence before activation:

- verified legal entity and beneficial ownership where required by jurisdiction;
- verified contact and operating address;
- tax/business registration evidence appropriate to the market;
- KYC/AML decision by an authorized reviewer where applicable;
- payout account ownership and supported currency;
- product/category and brand/distributor authorization;
- returns, warranty, consumer support and fulfilment policies;
- market-specific tax and regulatory capability;
- signed terms and a recorded reviewer, timestamp and evidence references.

Suspension or revocation must immediately prevent new display and purchase eligibility after cache invalidation. Existing orders follow the approved exception/refund process.

## Offer, stock and quote semantics

An offer is eligible only if the listing, merchant, product rights, variant, inventory, market, price and fulfilment evidence are simultaneously valid. Each component must be evaluated at display time and revalidated at checkout.

Use the existing canonical Commerce records and migrations as the source of truth. Do not create a parallel merchant or fulfilment database. The existing quote records for FX, tax and fulfilment must be populated only by verified adapters and must retain provider references, observation times and expiries.

A quote must distinguish:

- item price and source currency;
- customer payable currency;
- FX provider, rate, spread/rounding rule, observation time and expiry;
- tax amount, jurisdiction, tax basis and tax-provider reference;
- fulfilment mode, destination, amount, currency, charge basis, provider quote ID and expiry;
- any separately disclosed fees and total payable.

At checkout, if any quote is expired, market eligibility changes, inventory changes, or amount/currency differs, stop and require a fresh quote/confirmation. Never silently substitute a more expensive method.

## Shipment and exception lifecycle

Minimum normalized events:

`accepted → packed → handed_over → in_transit → out_for_delivery → delivered`

Exception states include `cancelled`, `delivery_failed`, `returned_to_sender`, `lost`, `damaged`, and `disputed`. Provider-specific states must map losslessly to a normalized state while retaining the original provider event.

All webhook/event handling must verify authenticity, enforce idempotency, tolerate out-of-order delivery, persist the raw provider event only under approved retention, and maintain an append-only transition/audit record. A duplicate event must not create a second shipment, charge, refund or inventory movement.

## Required adapter tests

- supported and unsupported market/mode combinations;
- merchant pending, rejected, suspended and revoked;
- expired, malformed, stale and conflicting FX/tax/fulfilment quotes;
- destination mismatch and unsupported postal/zone;
- stock race and concurrent checkout oversell;
- provider timeout, rate limit, 5xx, malformed payload and credential rotation;
- duplicate, replayed, invalid-signature and out-of-order shipment events;
- cancellation, partial fulfilment, failed delivery, return and refund;
- quote change between cart and checkout;
- tenant isolation and unauthorized merchant access.

## Provider onboarding checklist

For each selected provider, record and review before integration:

- [ ] provider legal name, official API docs and contract;
- [ ] countries, service zones, supported currencies and fulfilment modes;
- [ ] sandbox and production account owners;
- [ ] data-processing terms, region, subprocessors and retention;
- [ ] authentication, webhook signature and rotation procedure;
- [ ] rate limits, SLA, retry/backoff and idempotency guarantees;
- [ ] quote expiry and pricing/tax responsibility;
- [ ] cancellation, returns, claims and support escalation;
- [ ] real sandbox transaction and production-readiness test evidence;
- [ ] independent approval by marketplace operations and security/privacy.

## Acceptance and release gate mapping

- REL-06: approved merchants, rights, inventory and tenant governance.
- REL-10 / REL-16: support, fulfilment operations, monitoring, recovery and incident procedure.
- REL-13: market-specific merchant capability, FX/tax/fulfilment evidence, quote freshness and checkout totals.
- REL-19: separate brand/distributor tenant roles and evidence-backed dashboards.

No provider is considered integrated until a real authenticated staging transaction and its exception paths pass. The presence of database models or adapter interfaces is foundation work only.
