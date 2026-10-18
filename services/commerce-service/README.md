# Cirvanna Commerce Service

**Status: backend implementation candidate; production release still requires environment integration.**

This service implements persistent, authenticated commerce APIs. Canonical product identity belongs to services/catalog-service; merchant offers, prices, variants and inventory belong here.

## Implemented

- HMAC-SHA256 JWT verification requiring exp, iss, aud, sub, and role claims. A caller cannot choose an arbitrary user ID through the request body or an X-User-ID header.
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
- COMMERCE_JWT_SECRET: minimum 32 bytes, shared only with the trusted identity issuer.
- COMMERCE_JWT_ISSUER: defaults to cirvanna-auth.
- COMMERCE_JWT_AUDIENCE: defaults to cirvanna-commerce.
- CATALOG_API_URL and CATALOG_API_TOKEN: server-side canonical-catalog lookup. Non-local URLs must use HTTPS.
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

## Production gates still open

- Run migration on PostgreSQL and test backup/restore plus concurrent last-unit checkout contention. SQLite tests do not prove production locking semantics.
- Integrate the actual Cirvanna identity issuer and validate JWT claims, role administration and secret handling.
- Configure a non-production catalog and verify real TLS, credentials and CORS from the intended origin.
- Configure Stripe test mode and exercise real test payment, expiry, retry, webhook replay and reconciliation. This service currently charges item subtotal only; shipping/tax computation is not implemented.
- Seller payouts/Connect onboarding, refunds/returns, fulfillment, fraud/rate limits, reconciliation dashboards, retention/deletion and alerting are not implemented.
- CaTaCaCi eligibility, Click It reconstruction, Virtual Twin and try-on remain explicitly unavailable until real adapters/models are integrated and independently validated.
