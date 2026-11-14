# Merchant verification and fulfilment provider integration

**Status: contracts and internal commerce workflows exist; live merchant-verification and fulfilment providers are not connected.** This document defines the implementation boundary and acceptance evidence. It does not claim a provider has been selected, authenticated, or tested.

## 1. What exists today

Commerce owns merchant applications, owner-scoped listings, merchant-specific SKUs and variants, stock adjustments, admin approval/suspension, order records and market declarations. An admin decision requires a verification reference, but Commerce does not independently establish a business's legal identity, beneficial ownership, sanctions status, bank-account ownership or payout eligibility. Approval is therefore a human decision supported by a reference, not an automated KYC integration.

The multi-market schema stores versioned FX, tax, fulfilment and payment capability/quote records. The internal fulfilment-quote ingestion route validates timestamps, currency, destination, mode, quote amount and charging basis. Marketplace comparison requires fresh destination-zone evidence. These records are storage and validation contracts; a seller or operator writing a quote into Commerce is not proof that a carrier or logistics provider generated it.

The existing checkout path is Stripe/card only. The code now verifies provider capability evidence but does not yet implement seller payouts/Connect onboarding, provider-booked shipments, tracking, cancellation, delivery confirmation, carrier claims or physical returns as completed provider operations.

## 2. Merchant verification integration

A production merchant must not become active because a form was submitted or a browser supplied a verification reference.

Required state machine:

`application_received → verification_pending → verified | rejected | review_required → approved → market_active`

Suspension, expiry, revocation and re-verification must be explicit transitions. A provider outage or unknown response leaves the merchant in `verification_pending` or `review_required`; it must never grant market eligibility.

The selected provider adapter must support, at minimum:

- business registration/legal-name and registered-address verification for the declared operating country;
- beneficial-owner/controller checks where legally required;
- authorized representative verification and proof of authority;
- sanctions/restricted-party checks when applicable to the market and risk policy;
- verification status, reason codes, reference, provider version, observed time and expiry;
- signed webhooks or authenticated result retrieval, idempotency, replay protection and re-verification after material changes;
- proportionate data minimization, retention, deletion and evidence-access controls.

Commerce should persist opaque provider references, status, timestamps, verification version and an integrity digest—not raw identity documents or unnecessary personal data. Identity documents, if the chosen provider requires them, belong in that provider's approved secure collection flow. Do not put sensitive KYC payloads in application logs, analytics or the Commerce database.

The admin approval action must require a current, subject- and merchant-bound provider result. Human review may add a separate control but may not override a provider's hard rejection or a required legal prohibition without a documented, authorized appeal path.

## 3. Fulfilment integration

A complete fulfilment adapter is more than a quote API. It must support an operation lifecycle:

1. **Serviceability and quote:** resolve the exact origin, destination/service zone, parcel characteristics, quantity, chosen mode and merchant/warehouse. Return a provider quote ID, amount/currency, charge basis, tax treatment where relevant, service class, estimated delivery window, expiry and terms.
2. **Checkout binding:** bind the exact quote and offer snapshot to the cart/order version. Revalidate quote freshness, merchant eligibility, stock, destination, currency and CAL purchase receipt before payment.
3. **Booking:** create a shipment/collection booking with an idempotency key after the correct order/payment state transition. Store the provider booking reference and accepted service terms against the order.
4. **Label or handoff:** retrieve a label or handoff instruction through a private service path. Do not expose carrier credentials or private object URLs to the browser.
5. **Tracking and events:** verify webhook signatures, provider account, event ID, shipment reference, event ordering and replay. Store a normalized status and immutable provider-event digest.
6. **Cancellation and exceptions:** define cancel cut-offs, failed pickup, failed delivery, lost/damaged parcel, address correction, return-to-sender and refund/compensation behavior. Never mark an order delivered from a browser redirect or unverified callback.
7. **Reconciliation:** compare booked, picked-up, in-transit, delivered, cancelled and charged shipments with the provider's settlement/invoice records. Surface unmatched events to an operator queue.

The existing `FulfillmentQuoteIn` record remains the normalized quote contract. A quote is eligible only when provider identity is approved, the provider result is authenticated, its destination key exactly matches, it is current, its amount/currency/charge basis are valid, and its quote has not been consumed or invalidated. A seller cannot self-assert authoritative delivery cost or serviceability.

## 4. Provider-neutral adapter contract

Keep external vendor semantics behind an adapter with stable Cirvanna operations:

| Domain | Required operations | Minimum durable evidence |
|---|---|---|
| Merchant verification | create/check verification, verify webhook, revoke/recheck | provider reference, merchant, status, reason, observed/expiry, event digest |
| Inventory feed (where applicable) | ingest snapshot/event, reconcile quantity | merchant/listing/variant, source sequence, observed time, source digest |
| Fulfilment | serviceability, quote, book, cancel, track, reconcile | provider quote/booking/event IDs, destination, mode, amount, status, time, idempotency key |

Adapters must use trusted HTTPS, server-held secrets, narrow scopes, explicit connect/read timeouts, no redirects, response-size limits, schema validation and sanitized errors. Webhooks require signature verification, timestamp tolerance, deduplication and replay tests. Provider operations must be idempotent; retries must not create duplicate merchant verifications, shipments, labels, charges or cancellations.

A provider's `/health` or `/ready` result is not evidence of a completed operation. Staging must exercise an actual sandbox verification and shipment booking. Before production, run a controlled live transaction and reconcile it with the provider's source-of-truth record.

## 5. Provider selection is a required decision

No merchant KYC or fulfilment vendor is selected by the current repository. Do not write fictitious provider names, keys or coverage claims into configuration.

Before adapter implementation is treated as complete, the product/commercial owner must approve a provider per target operating market using a recorded decision covering:

- legal entity and contractual data-processing terms;
- country, currency, language and service-zone coverage;
- supported merchant types, verification checks and escalation process;
- quote, booking, cancel, tracking, returns and claims APIs;
- webhook authentication, rate limits, idempotency and sandbox availability;
- pricing, surcharges, taxes, settlement and reconciliation export;
- SLA, incident process, data location, retention and deletion;
- fallback behavior and manual operations when the provider is unavailable.

Do not select a carrier solely because it exposes a quote endpoint. The provider must cover the intended fulfilment promise, not just price estimation.

## 6. Acceptance and release evidence

The integration is not accepted until all of these pass against the exact release commit:

- merchant application → provider verification → human decision → operating-market activation; prove rejected, expired, mismatched-subject and provider-timeout cases remain inactive;
- provider webhook signature, replay, duplicate, out-of-order, retry and revocation tests;
- merchant ownership and tenant-isolation tests for every listing, stock, order and verification operation;
- serviceability and quote tests for each supported market, mode and zone, including expired, unavailable, negative, malformed, duplicated and wrong-currency quotes;
- quote-bound checkout with stock contention, quote expiry between cart and checkout, provider timeout, booking idempotency and compensation;
- shipment booking, tracking webhook, cancellation, failed delivery and provider reconciliation against sandbox records;
- operator procedures for exceptions, provider outage, manual hold, escalation and audit export;
- live staging credentials, provider account IDs, API versions, webhook signing keys and actual operation evidence stored in the approved secret manager/evidence registry.

**Release gates:** REL-06 (real merchant, catalog and inventory operations), REL-13 (multi-market landed-cost and checkout evidence), and REL-22 (merchant verification and fulfilment execution). All remain blocked until evidence is independently reviewed. No market is enabled by adding a database row or mock quote.
