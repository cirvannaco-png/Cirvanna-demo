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

- GET /marketplace/offers
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

Local run from this directory:

    python -m venv .venv
    . .venv/bin/activate
    pip install -r requirements.txt
    uvicorn app.main:app --host 127.0.0.1 --port 8081

Production-like migration:

    export COMMERCE_DATABASE_URL='postgresql+psycopg://...'
    export COMMERCE_AUTO_CREATE_SCHEMA=false
    alembic upgrade head

Do not pass a privileged token to a public static frontend. Commerce JWTs must be issued by Cirvanna's trusted identity system; this service is not an identity provider.

## Payment and stock semantics

Checkout commits the order and stock reservations before calling Stripe, so a network call does not hold a database transaction open. Stripe session creation uses a stable idempotency key derived from the persisted order. On a timeout, the service keeps stock reserved and requires a retry/reconciliation using the SAME customer Idempotency-Key. It does not release inventory if the remote outcome is ambiguous.

Only a verified Stripe webhook can mark an order paid. The handler verifies signature, order metadata, Checkout Session ID, total and currency before decrementing stock and consuming reservations. Duplicate event IDs are ignored. The expiry job releases reservations only after Stripe confirms expiration.

## Identity provider setup

This repository does not issue login sessions or manage the user lifecycle. Connect the actual Cirvanna identity provider before staging rollout. Configure the provider's JWKS URL, exact issuer and Commerce audience in the secret manager, map its trusted application-role claim, and test key rotation, expiry, unknown keys, issuer/audience mismatch and disabled-user/session revocation. Signature verification here does not replace the provider's sign-in, consent, account recovery or lifecycle controls.

## Production gates still open

- Run migration on PostgreSQL and test backup/restore plus concurrent last-unit checkout contention. SQLite tests do not prove production locking semantics.
- Integrate the actual Cirvanna identity issuer and validate JWT claims, role administration and secret handling.
- Configure a non-production catalog and verify real TLS, credentials and CORS from the intended origin.
- Configure Stripe test mode and exercise real test payment, expiry, retry, webhook replay and reconciliation. This service currently charges item subtotal only; shipping/tax computation is not implemented.
- Seller payouts/Connect onboarding, refunds/returns, fulfillment, fraud/rate limits, reconciliation dashboards, retention/deletion and alerting are not implemented.
- CaTaCaCi eligibility, Click It reconstruction, Virtual Twin and try-on remain explicitly unavailable until real adapters/models are integrated and independently validated.


## Canonical variants and offer freshness

Commerce retains its merchant-local `variant_id` and `sku` as source identifiers. It may additionally store `canonical_variant_id`, but only after validating the ID with Catalog's read-scoped `GET /variants/{variant_id}` endpoint and confirming that the returned canonical `product_id` matches the listing's Catalog product. Merchants cannot self-assert a canonical identity.

Production always rejects new variants without a Catalog-verified canonical variant ID; the `COMMERCE_REQUIRE_CANONICAL_VARIANT_ID=true` setting can enforce the same gate in staging. Existing legacy rows remain nullable and are not comparison-eligible.

Each offer has a server-generated `observed_at` timestamp. It is refreshed when the offer is created and when stock changes through merchant inventory updates, checkout reservations, payment settlement, or reservation release. `GET /marketplace/offers` returns `observed_at`, `is_fresh`, `canonical_variant_id`, and `comparison_eligible`. Freshness is controlled by `COMMERCE_OFFER_MAX_AGE_SECONDS` (default 3600 seconds, clamped to 60 seconds–7 days). A missing canonical identity or stale observation makes the individual offer ineligible for comparison. This is only a per-offer precondition: a comparison must still verify that both offers share the exact same canonical variant ID and currency and both have current availability. This timestamp is Commerce's server observation time; it is not proof of a third-party feed timestamp. Shipping/tax and FX remain excluded unless separately sourced.


## Multi-market offers and checkout (migrations 20261105_0004–0005)

- Brand home/origin country and legal entity country are independent fields. The existing merchant country_code is preserved as a legacy legal-country alias. Existing merchants are backfilled to legal_country_code only; brand_home_country_code remains unknown until declared.
- Operating markets are explicit and begin in pending state. Activation requires an approved merchant, a current active payment capability, and fresh administrator-verified tax and fulfilment provider evidence with references and expiry. Expired capability evidence makes the market unavailable until refreshed.
- Variant price_minor/currency remains the payable offer amount and transaction currency. source_price_minor/source_currency are optional product/source provenance and never overwrite the offer price.
- FX, fulfilment, tax and market payment capabilities are versioned provider records with provider IDs, provenance, observation time and expiry. Only the secret-protected internal market-context API can write these records. Sellers cannot self-assert exchange rates, authoritative tax, or payment readiness.
- Currency minor-unit precision is sourced from Babel/CLDR. A display price is derived separately from the immutable source offer amount. FX rate is the provider's executable rate (including any spread); spread_bps is retained for audit and is not applied twice.
- Fulfilment quotes explicitly declare `per_unit` or `per_quote` charging. Checkout multiplies per-unit charges by quantity and applies a shared provider quote only once; inconsistent repeated quote totals across cart lines are rejected.
- GET /marketplace/offers accepts market_country_code and display_currency. When destination_key and fulfillment_mode are supplied, it also applies a 30 km default radius (user-adjustable from 1–500 km), excludes offers without a current confirmed quote within the radius, and returns transport amount, currency, distance and FX provenance.
- POST /marketplace/compare returns comparable only for exact matching canonical variant IDs, fresh in-stock offers, approved merchants active in the destination market, exact destination and fulfilment mode, confirmed destination-bound fulfilment quotes, fresh authoritative tax with matching jurisdiction/category/basis, valid FX for every currency conversion, and current payment capability for each transaction currency.
- Inclusive tax is already in the item price and is not added a second time. Missing/stale/incomparable facts return a stable unavailable reason; an incomplete amount is never labelled a landed price.
- Market-aware checkout requires destination country/key, selected fulfilment mode and display currency. The destination_key is a provider-issued delivery-zone key, not a free-form street address. At payment-session creation Commerce revalidates the active market, Stripe payment capability, current confirmed fulfilment quote, authoritative tax quote and required FX quotes. It calculates item, fulfilment, tax and total in one order currency, stores original source prices and quote provenance, charges fulfilment/exclusive tax as separate Stripe line items, and verifies the webhook amount against total_minor. Inclusive tax is not double-counted. Stripe does not collect a second address for market-aware orders; the fulfilment provider_quote_id resolves the quoted destination. The idempotency key is bound to the checkout context; a changed destination or currency conflicts.
- Legacy checkout remains available only for merchants without active operating markets. Once a merchant's market is active, omitting market checkout context is rejected. Reservations are capped by the earliest relevant provider quote expiry.

Configure COMMERCE_MARKET_CONTEXT_TOKEN (at least 32 bytes) only for trusted quote-provider ingress. Never expose it to the merchant browser.

This PR provides provider-neutral quote and capability ingestion contracts, not live FX, tax, courier, KYC or payment-provider onboarding adapters. Provider references and timestamps must be independently verified before admin activation. No production secrets or live provider integrations are configured by this change.
