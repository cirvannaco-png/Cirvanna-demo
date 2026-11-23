# Cirvanna Commerce Service

**Status: backend implementation candidate; production release still requires environment integration.**

This service implements persistent, authenticated commerce APIs. Canonical product identity belongs to services/catalog-service; merchant offers, prices, variants and inventory belong here.

## Implemented

- JWT authentication with development-only shared-secret HS256 plus production OIDC/JWKS mode validating RS256 signature, issuer, audience, expiry and a configured application-role claim. Production rejects HS256 even when a shared secret exists. A caller cannot choose an arbitrary user ID through the request body or an X-User-ID header.
- Merchant application, admin decision, a required human-verification reference, approval/suspension states, owner-scoped listings and merchant-specific SKUs/variants.
- Inventory adjustment ledger and invariant checks; available stock equals on_hand minus reserved_qty.
- Durable per-user saved products and carts, uniqueness constraints and stock revalidation.
- Idempotent orders via Idempotency-Key, immutable line snapshots, commission basis points, transactional stock reservations and hosted Stripe Checkout.
- Stripe signature verification with 5-minute timestamp tolerance, amount/currency matching, event deduplication and settlement only from verified paid events.
- Reservation expiry route that releases stock only after Stripe confirms session expiry. Ambiguous payment API timeouts keep stock reserved for reconciliation rather than risking oversell.
- Exact-origin CORS allowlist, readiness/capability endpoints and inventory invariant audit.

## Main routes

- GET /marketplace/offers — **internal-only candidate feed**, protected by the dedicated Decision Gateway credential.
- POST /marketplace/compare — **internal-only comparison API**, protected by the same dedicated Decision Gateway credential.
- POST /merchants/applications; GET /merchants/me
- POST /admin/merchants/{merchant_id}/decision
- POST /merchant/listings; POST /merchant/listings/{listing_id}/variants
- POST /merchant/variants/{variant_id}/inventory-adjustments
- PUT/GET/DELETE /saved-products
- GET /cart; POST /cart/items; PATCH/DELETE /cart/items/{variant_id}
- POST /checkout with Idempotency-Key; GET /orders; GET /orders/{id}; GET /merchant/orders
- POST /webhooks/stripe; POST /internal/expire-reservations; GET /admin/inventory/audit

Customer and merchant routes require bearer JWT authentication. Inventory writes are merchant-owner scoped. The approval endpoint requires a verification reference, but this API cannot itself perform business/KYC verification; a human admin and a valid verification procedure remain required.

## Configuration

Set these in a secret manager; never commit real secrets.

- COMMERCE_DATABASE_URL: PostgreSQL for shared/production use. SQLite is local-development only.
- COMMERCE_AUTO_CREATE_SCHEMA: defaults true locally; set false in deployments and apply Alembic migrations.
- COMMERCE_ENVIRONMENT: set to production in deployed environments; production requires OIDC/JWKS.
- SHOPIFY_INVENTORY_RESERVATION_PRODUCTION_ENABLED: defaults false; Shopify-backed checkout is blocked in production (and when the environment is unclassified) until live provider, PostgreSQL restore and compensation/refund acceptance is complete. Keep false in production until those gates are signed off.
- SHOPIFY_COMPENSATION_SCOPE_ENABLED: defaults false; when enabled, Shopify OAuth requests optional `write_orders` permission for irreversible provider-order cancellation. Existing merchants must re-authorize; without the scope, compensation is manual-review only.
- COMMERCE_AUTH_MODE: set to oidc_jwks in production. The hs256 mode is for local development and tests only.
- COMMERCE_JWT_JWKS_URL: trusted HTTPS JWKS endpoint from the chosen identity provider.
- COMMERCE_JWT_ISSUER: exact issuer identifier configured by the identity provider (required for OIDC mode).
- COMMERCE_JWT_AUDIENCE: exact Commerce API audience registered with the identity provider (required for OIDC mode).
- COMMERCE_JWT_ROLE_CLAIM: claim containing customer, merchant, or admin; defaults to role. The identity provider must control this claim and grant merchant/admin roles only to authorized accounts.
- COMMERCE_JWT_SECRET: minimum 32 bytes for local HS256 mode only; it is not a production authentication mechanism.
- CATALOG_API_URL and CATALOG_API_TOKEN: server-side canonical-catalog lookup. In production, CATALOG_API_TOKEN must equal Catalog's CATALOG_READ_TOKEN; never configure Catalog's write token here. Non-local URLs must use HTTPS.
- COMMERCE_CORS_ORIGINS: optional comma-separated exact frontend origins. No wildcard is used.
- STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET: Stripe Checkout and webhook signing secrets; validate with test-mode keys.
- COMMERCE_CHECKOUT_SUCCESS_URL and COMMERCE_CHECKOUT_CANCEL_URL: trusted HTTPS destinations.
- COMMERCE_SHIPPING_COUNTRIES: comma-separated two-letter country codes.
- COMMERCE_CRON_TOKEN: strong secret used by the stock-reservation expiry job.
- COMMERCE_SHOPIFY_SYNC_TOKEN: at least 32 random bytes for Shopify sync, export, reconciliation and compensation workers; schedule `/internal/shopify/process-events`, `/internal/shopify/reconcile` and `/internal/shopify/compensate-paid-orders` separately from provider webhook delivery. Reconciliation returns a store cursor; continue with `after_connection_id` and retry any `failed_connection_ids` by `connection_id`.
- COMMERCE_MARKETPLACE_READ_TOKEN: dedicated 32-byte minimum service credential, shared only with the Decision Gateway and sent as X-Commerce-Marketplace-Read-Token. Do not reuse sync, quote-ingestion, user JWT, or CAL signing secrets.

Local run from this directory:

    python -m venv .venv
    . .venv/bin/activate
    pip install -r requirements.txt
    uvicorn app.main:app --host 127.0.0.1 --port 8081

Historical migration ordering: `20261107_0004` introduced the verified-purchase outbox and `20261107_0005` added refund snapshots. The current Commerce schema head is `20261121_0016`; always apply the full Alembic chain with `alembic upgrade head`:

    export COMMERCE_DATABASE_URL='postgresql+psycopg://...'
    export COMMERCE_AUTO_CREATE_SCHEMA=false
    alembic upgrade head

Do not pass a privileged token to a public static frontend. Commerce JWTs must be issued by Cirvanna's trusted identity system; this service is not an identity provider.

## Payment and stock semantics

Checkout commits the order and stock reservations before calling Stripe, so a network call does not hold a database transaction open. Stripe session creation uses a stable idempotency key derived from the persisted order. On a timeout, the service keeps stock reserved and requires a retry/reconciliation using the SAME customer Idempotency-Key. It does not release inventory if the remote outcome is ambiguous.

Only a verified Stripe webhook can mark an order paid. The handler verifies signature, order metadata, Checkout Session ID, total and currency before decrementing stock and consuming reservations. Duplicate event IDs are ignored. The expiry job releases reservations only after Stripe confirms expiration.

A successful paid settlement writes a versioned `commerce.order.paid` record to `commerce_outbox_events` in the same database transaction as payment settlement. The paid Checkout Session's PaymentIntent ID is bound to exactly one Commerce order. A verified Stripe `charge.refunded` event is mapped through that PaymentIntent and checked against the original order amount/currency; only monotonic cumulative refund increases update the payment snapshot and emit `commerce.order.refund.updated`. A Shopify-backed order enters `fulfillment_state=provider_pending` until every provider draft is completed and linked; the paid ownership event remains valid but explicitly carries `fulfillment_ready=false`, and merchant order responses expose the same gate. A terminal Shopify failure enters compensation/manual review and cannot be treated as fulfilment-ready. The durable Shopify compensation case and Stripe refund attempt tables support leased per-seller recovery, asynchronous Shopify cancellation, and one idempotent full refund after every seller is confirmed safe. The Commerce order is marked refunded only after a verified Stripe refund event confirms the succeeded refund and exact amount/currency. Failed, pending, saved, carted and try-on states do not emit ownership events. The outbox exposes authenticated internal lease/claim, acknowledge and retry/dead-letter endpoints for the Sync worker. Delivery is at-least-once; consumers must deduplicate by event ID. The endpoints are not a deployed worker and do not themselves complete purchase-to-Wardrobe sync. A refund is not proof that an item was physically returned or that the buyer no longer possesses it: Wardrobe ownership is not deleted or archived by financial refund status. Physical returns, chargebacks, item-level allocation and seller recovery remain separate workflows.

## Identity provider setup

This repository does not issue login sessions or manage the user lifecycle. Connect the actual Cirvanna identity provider before staging rollout. Configure the provider's JWKS URL, exact issuer and Commerce audience in the secret manager, map its trusted application-role claim, and test key rotation, expiry, unknown keys, issuer/audience mismatch and disabled-user/session revocation. Signature verification here does not replace the provider's sign-in, consent, account recovery or lifecycle controls.

## Production gates still open

- Run migration on PostgreSQL and test backup/restore plus concurrent last-unit checkout contention. SQLite tests do not prove production locking semantics.
- Integrate the actual Cirvanna identity issuer and validate JWT claims, role administration and secret handling.
- Configure a non-production catalog and verify real TLS, credentials and CORS from the intended origin.
- Configure Stripe test mode and exercise real test payment, expiry, retry, webhook replay and reconciliation. Stripe/card is the only implemented payment rail; PayPal and bank rails are not integrated. Market-aware checkout can calculate totals only from fresh, validated FX/fulfilment/tax/payment capability records; live third-party quote-provider operations and market settlements still require staging evidence.
- Seller payouts/Connect onboarding, physical returns, chargebacks, item-level refund allocation, carrier booking/tracking, fraud/rate limits, reconciliation dashboards, retention/deletion and a staffed operational alerting/incident workflow are not implemented. The new compensation worker and manual-review outbox events are code paths, not a deployed scheduler or staffed operations process.
- Full production enablement still requires the signed CAL purchase-authorisation path, BFF integration, live staging browse → cart → checkout → Stripe webhook reconciliation, and independent privacy evidence. Click It reconstruction, Virtual Twin mesh reconstruction and licensed try-on rendering remain unavailable until real adapters/models are integrated and independently validated.


## Canonical variants and offer freshness

Commerce retains its merchant-local `variant_id` and `sku` as source identifiers. It may additionally store `canonical_variant_id`, but only after validating the ID with Catalog's read-scoped `GET /variants/{variant_id}` endpoint and confirming that the returned canonical `product_id` matches the listing's Catalog product. Merchants cannot self-assert a canonical identity.

Production always rejects new variants without a Catalog-verified canonical variant ID; the `COMMERCE_REQUIRE_CANONICAL_VARIANT_ID=true` setting can enforce the same gate in staging. Existing legacy rows remain nullable and are not comparison-eligible.

Each offer has a server-generated `observed_at` timestamp. It is refreshed when the offer is created and when stock changes through merchant inventory updates, checkout reservations, payment settlement, or reservation release. `GET /marketplace/offers` returns `observed_at`, `is_fresh`, `canonical_variant_id`, and `comparison_eligible`. Freshness is controlled by `COMMERCE_OFFER_MAX_AGE_SECONDS` (default 3600 seconds, clamped to 60 seconds–7 days). A missing canonical identity or stale observation makes the individual offer ineligible for comparison. This is only a per-offer precondition: a comparison must verify the same canonical Catalog product and exact canonical variant ID, current availability, exact destination zone, compatible tax evidence and payment capability. Different merchant transaction currencies are comparable only when fresh provider FX converts each item, fulfilment and tax amount to one requested display currency. This timestamp is Commerce's server observation time; it is not proof of a third-party feed timestamp. Shipping/tax and FX remain excluded unless separately sourced.


## Multi-market offers and checkout (mainline migrations 20261109_0007–0008)

The merged 20261109_0007 migration establishes merchant brand-home/legal-country separation, source price/currency provenance, explicit operating-market records, and provider-evidence tables for FX, fulfilment, tax and payment capabilities. This is a schema foundation only: no market is enabled by adding a row or by the presence of quote tables, and no live provider is configured by the migration.

The old PR #102 migration files must not be applied unchanged. The current mainline already uses its historical 0004/0005 identifiers for verified-purchase outbox and refund snapshot work. Port the remaining multi-market APIs and offer-comparison/checkout flow using a new migration chained after 20261109_0007. Until real provider-sourced quotes and capability evidence are configured and verified, localized totals and comparisons must remain unavailable rather than estimated or fabricated. See [the system readiness register](../../docs/architecture/system-readiness-and-quality-2026-11-09.md).


## Multi-market offers and checkout (mainline migrations 20261109_0007–0008)

- Brand home/origin country and legal entity country are independent fields. The existing merchant country_code is preserved as a legacy legal-country alias. Existing merchants are backfilled to legal_country_code only; brand_home_country_code remains unknown until declared.
- Operating markets are explicit and begin in pending state. Merchants can inspect their own declarations at `GET /merchants/me/markets`; administrators can inspect the full provider-evidence record at `GET /admin/merchants/{merchant_id}/markets` and activate/disable a market through the admin-only state endpoint. In staging/production, activation re-verifies the merchant's complete current operating-market set against fresh KYB evidence (so a market added after initial approval cannot inherit old scope), verifies active payment capability, and independently attests exact merchant/market tax and fulfilment capability with matching provider references and expiry. Expired or mismatched evidence fails closed. Fulfilment distances must be exactly representable at the persisted 0.01 km precision; values such as 30.004 km are rejected rather than rounded into a 30.00 km radius result.
- Variant price_minor/currency remains the payable offer amount and transaction currency. source_price_minor/source_currency are optional product/source provenance and never overwrite the offer price.
- FX, fulfilment, tax and market payment capabilities are versioned provider records with provider IDs, provenance, observation time and expiry. Tax quotes are additionally bound to the exact destination_key/fulfilment zone; country-only legacy tax quotes remain ineligible for comparison and checkout. Only the secret-protected internal market-context API can write these records. Sellers cannot self-assert exchange rates, authoritative tax, or payment readiness.
- Currency minor-unit precision is sourced from Babel/CLDR. A display price is derived separately from the immutable source offer amount. FX rate is the provider's executable rate (including any spread); spread_bps is retained for audit and is not applied twice.
- Fulfilment quotes explicitly declare `per_unit` or `per_quote` charging. Checkout multiplies per-unit charges by quantity and applies a shared provider quote only once; inconsistent repeated quote totals across cart lines are rejected.
- GET /marketplace/offers accepts market_country_code and display_currency. When destination_key and fulfillment_mode are supplied, it also applies a 30 km default radius (user-adjustable from 1–500 km), excludes offers without a current confirmed quote within the radius, and returns transport amount, currency, distance and FX provenance. POST /marketplace/compare enforces the same selected radius, so an offer outside the user-selected service area cannot enter a comparison.
- POST /marketplace/compare returns comparable only for the same canonical Catalog product and exact canonical variant, fresh in-stock offers, approved merchants active in the destination market, exact destination zone and fulfilment mode, confirmed destination-bound fulfilment quotes, fresh authoritative tax for that exact zone with matching jurisdiction/category/basis, and current payment capability for the selected order/display currency. Offers may originate in different transaction currencies; each item, fulfilment and tax amount must have a current provider FX quote into the requested display currency before the landed totals are compared. Source amount/currency and each FX quote remain visible in the comparison provenance. No direct raw-currency comparison is permitted.
- Inclusive tax is already in the item price and is not added a second time. Missing/stale/incomparable facts return a stable unavailable reason; an incomplete amount is never labelled a landed price.
- Market-aware checkout requires destination country/key, selected fulfilment mode and display currency. The destination_key is a provider-issued delivery-zone key, not a free-form street address. At payment-session creation Commerce revalidates the active market, Stripe card payment capability, current confirmed fulfilment quote and exact destination-zone authoritative tax quote, plus the required FX quotes. It calculates item, fulfilment, tax and total in one order currency, stores original source prices and quote provenance, charges fulfilment/exclusive tax as separate Stripe line items, and verifies the webhook amount against total_minor. Inclusive tax is not double-counted. Stripe does not collect a second address for market-aware orders; the fulfilment provider_quote_id resolves the quoted destination. The idempotency key is bound to the checkout context; a changed destination or currency conflicts.
- Legacy checkout remains available only for merchants without active operating markets. Once a merchant's market is active, omitting market checkout context is rejected. Reservations are capped by the earliest relevant provider quote expiry.

Configure COMMERCE_MARKET_CONTEXT_TOKEN (at least 32 bytes) only for trusted quote-provider ingress. Never expose it to the merchant browser.

The #181/#102 integration provides provider-neutral quote and capability ingestion contracts, not live FX, tax, courier, KYC or payment-provider onboarding adapters. Schema and internal ingestion endpoints do not themselves prove that an external provider is configured, authenticated or operational. Provider references and timestamps must be independently verified before admin activation. No production secrets or live provider integrations are configured by this change.


## Candidate-bound CAL authorization for cart and checkout

Commerce does not treat a successful marketplace display decision as permission to mutate a cart or create a payable order. Each user-controlled cart read, add, quantity update and checkout asks the Decision Gateway for a fresh action-specific authorization. Removing a cart line remains available without a product authorization so a buyer can always remove an item.

The request contains the authenticated buyer identity and an offer snapshot hash covering the canonical Catalog product, variant, listing, merchant, variant version/state, SKU/options, source and authorized unit price/currency, quantity, available stock and, for market-aware checkout, the destination-zone hash, fulfilment mode, display currency and provider quote/FX/tax/payment evidence. No raw street address is sent to the Decision Gateway. Gateway independently resolves the end-user bearer through Commerce identity and returns a per-offer HMAC-SHA256 signed receipt bound to subject, candidate/variant, product, listing, merchant, action, offer hash, market, quantity, price, Catalog version, policy version, verdict and short expiry.

Commerce verifies the receipt signature, authenticated subject, exact request binding, Catalog version presence, policy metadata, and issue/expiry window. Only SHOW with may_display=true is accepted. Missing configuration, timeouts, malformed receipts, signature failures, mismatched offers, stale receipts and BLOCK/REVIEW decisions fail closed. A batch is split so no Decision Gateway evaluation contains more than 25 unique Catalog products.

Migration 20261110_0010_cal_purchase_authorizations.py creates the commerce_cal_purchase_audits table. Migration 20261112_0011_cal_purchase_audit_immutability.py installs database triggers that reject UPDATE and DELETE on both PostgreSQL and SQLite, and TRUNCATE on PostgreSQL. Successful cart-action receipts and denied decisions are recorded against the buyer and cart version. Checkout receipts are bound to the exact line snapshots and inserted in the same transaction as the order, stock reservations and immutable order lines. An idempotent payment-session retry is permitted only when every existing order line has its corresponding successful checkout authorization audit. Existing legacy orders without those audits cannot be reopened for payment. The Commerce CI migration job inserts a fixture row and verifies that the database itself rejects UPDATE/DELETE. In staging/production, apply migrations with a separate schema-owner credential and run Commerce using a non-owner runtime role without audit-table UPDATE/DELETE/TRUNCATE or trigger-administration privileges.

Configure DECISION_GATEWAY_URL, DECISION_GATEWAY_TOKEN and CAL_PURCHASE_RECEIPT_HMAC_SECRET in the secret manager. The URL must use HTTPS outside local development, the service token and HMAC key must each be at least 32 bytes, and the HMAC key must be the same dedicated secret in Commerce and the Decision Gateway. Never expose either value to a browser or merchant. /ready now requires a reachable, ready Decision Gateway and the current 20261112_0011 schema before reporting Commerce ready.

The BFF and buyer-facing Cart/Checkout routes must remain disabled until this service-level authorization is deployed and its exact-head CI and non-production browse → cart → checkout → payment/webhook path have passed. Enabling a frontend button is not evidence that CAL is enforced.


## Optional checkout preference learning

A checkout may include a personalization consent bundle ID and optional consent version. Commerce verifies that bundle with the canonical Identity Learning service against the authenticated buyer and the active, non-resource-bound personalization scope. The resolved receipt ID is snapshotted on the order. Commerce writes a consented checkout.started selection event in the same transaction that creates the pending order and immutable line snapshots; after payment, it writes the verified commerce.order.paid event. Checkout remains available without opting into personalization; no receipt means no checkout learning.

Set IDENTITY_SERVICE_URL and IDENTITY_SERVICE_TOKEN together to enable this optional consent verification. The token must be at least 32 bytes. The service URL must use HTTPS outside local development. If a user supplies a consent bundle and verification is unavailable, invalid, expired or revoked, Commerce fails closed for that consented request rather than accepting an unverified learning signal.

Migration 20261110_0009 adds the nullable tal_consent_receipt_id column to commerce_orders. Apply it after 20261109_0008 before enabling the new code in a shared environment. The Sync worker sends minimized per-line weak checkout-selection observations to durable TAL at checkout start and a separate verified-transaction observation after payment settlement; TAL rechecks that the receipt remains active for each write. Purchase history is not a declared preference and cannot create a hard NPL veto.


## Merchant verification and fulfilment provider boundary

Merchant applications, admin decisions and owner-scoped listings are implemented, but Commerce does not independently perform legal-entity/business verification or beneficial-owner checks. A verification reference on an admin decision is not a live KYC result. The normalized FX/tax/fulfilment quote records and quote-ingestion APIs are contracts, not a carrier integration: live serviceability, shipment booking, labels/handoff, tracking webhooks, cancellations, exceptions and provider reconciliation remain unimplemented. Seller payouts/Connect onboarding are also not implemented. See [the merchant and fulfilment integration contract](../../docs/commerce/merchant-and-fulfilment-provider-integration.md). Do not activate a merchant market or publish a landed-cost promise until the selected provider's operation-level staging evidence passes REL-22 and REL-13.

## Shopify merchant-provider connector

The optional Shopify adapter is documented in [the Shopify Commerce connector contract](../../docs/commerce/shopify-commerce-connector.md). It uses expiring offline tokens encrypted at rest, stages provider products privately, requires explicit Catalog product/variant mapping, and reconciles complete location-scoped stock under a durable per-store sync lease. The staged-products, map, and reactivate routes require an authenticated approved merchant and resolve the Shopify connection from that merchant's owner identity; staged product snapshots are not a shopper-facing Catalog or Marketplace API. Regression tests prove anonymous/customer access is rejected and another merchant cannot enumerate the owner's staged records. Readiness distinguishes connected/webhook-ready from catalogue-ready and exposes interrupted sync recovery rather than reporting stale catalogue data as complete. For Shopify-backed checkout it requests a provider-native inventory hold through the Admin GraphQL `DraftOrderInput.reserveInventoryUntil` field before Stripe session creation. Because Shopify draft orders do not reserve inventory by default, Commerce reads back and verifies the exact future expiry, `OPEN` state and `ready=true` before treating a provider draft as reserved; missing or mismatched evidence fails closed and enters compensation. The local deadline is aligned to the provider's whole-second expiry, and the hold is revalidated immediately before draft completion after payment. After verified payment, Commerce completes those exact drafts; post-payment failures enter the seller-compensation/Stripe-refund saga and fulfilment stays blocked until every seller is reconciled. The API contract is pinned to Shopify Admin GraphQL `2026-10`; see [draftOrderCreate](https://shopify.dev/docs/api/admin-graphql/2026-10/mutations/draftOrderCreate) and [inventory management app states](https://shopify.dev/docs/apps/build/inventory-management-apps). Shopify product import does not grant shopper display access: all Marketplace product display continues through the Decision Gateway/CAL SHOW path, and all cart/checkout actions retain the separate candidate-bound purchase authorization. Set the Shopify secrets in the secret manager only; live Shopify credentials, store grants, webhook delivery, inventory reconciliation, payment/compensation lifecycle and production readiness remain unverified until staging acceptance passes.


## Yoti age evidence for cart and checkout

The BFF Commerce proxy forwards the three `X-Cirvanna-Age-*` headers only on cart/checkout purchase paths. Commerce validates that the signed attestation subject equals the authenticated buyer and that its request ID matches the companion header, then forwards it to the internal Decision Gateway as part of the candidate-bound CAL purchase authorization. The Gateway verifies the active EEPL policy and consumes the one-time attestation JTI before it can authorize an age-restricted candidate. A single attestation can cover at most 25 unique Catalog products in one purchase-authorization request; larger carts fail closed with `AGE_EVIDENCE_SINGLE_REQUEST_LIMIT_EXCEEDED` rather than reusing a one-time attestation across batches. Without verified evidence, age-restricted candidates remain REVIEW and cannot be added or checked out.
