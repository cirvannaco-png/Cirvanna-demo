# Shopify connector — Cirvanna Commerce

**Implementation state: feature-branch engineering candidate.** The connector source and migration are implemented, but no Shopify Partner app, store grant, deployed callback, live webhook receipt, or real order export has been verified. Do not label the integration production-ready until exact-head CI and live staging acceptance pass.

## System boundaries

- **Shopify** is the connected merchant's external source for its own product/variant data, shop-base prices, location inventory and fulfilment/financial status for imported orders.
- **Catalog** remains the canonical owner of Cirvanna product and purchasable-variant identity.
- **Commerce** remains the canonical owner of merchant offers, stock reservations, immutable buyer order lines, payments and seller/market eligibility.
- **CAL** remains the final product-display authorization authority. Shopify OAuth, product import, canonical mapping, stock availability and merchant approval do not imply CAL SHOW.
- The connector exposes merchant-only staging records and internal service-job endpoints. It adds no public Shopify product-search or display route.

A Shopify product first lands in private commerce_shopify_product_snapshots and commerce_shopify_variant_snapshots. A merchant must explicitly map it to an existing Catalog product and exact Catalog variant IDs. Commerce verifies those IDs through Catalog's read-only API before creating/updating local listing and variant records. The existing Marketplace → NPL/exclusions → Decision Gateway/CAL SHOW flow remains mandatory for every shopper-facing result. An unmapped, archived, stale, untracked or inventory-incomplete variant must not become a sellable offer.

## OAuth and credentials

Register a Shopify app and configure these URLs exactly:

- OAuth callback: https://<marketplace-bff-public-host>/integrations/shopify/callback
- Webhook receiver: https://<commerce-public-host>/webhooks/shopify

The BFF relays the OAuth callback to Commerce and forwards only the short-lived, HttpOnly state cookie over its private upstream connection. This keeps the OAuth browser cookie on the same public origin as the merchant portal. Set SHOPIFY_APP_BASE_URL to the public Marketplace BFF origin and SHOPIFY_WEBHOOK_BASE_URL to the public Commerce API origin.

The app requests offline access and expiring=1; the implementation stores both access and rotating refresh tokens encrypted with AES-256-GCM. The raw tokens are never returned by an API or written into logs. The encryption key is a separate 32-byte key, base64url-encoded; it is not the Shopify app secret, a JWT secret, a webhook secret, or a CAL signing key.

Required secret-manager settings:

| Setting | Purpose |
|---|---|
| SHOPIFY_API_KEY | Shopify app client ID |
| SHOPIFY_API_SECRET | OAuth and webhook HMAC secret |
| SHOPIFY_APP_BASE_URL | Trusted HTTPS Marketplace BFF origin used to build OAuth callback URLs |
| SHOPIFY_WEBHOOK_BASE_URL | Trusted HTTPS Commerce API origin used to register provider webhooks |
| SHOPIFY_ADMIN_API_VERSION | Must be 2026-10; code intentionally pins this stable version |
| COMMERCE_SHOPIFY_TOKEN_ENCRYPTION_KEY | Base64url-encoded 32-byte AES-GCM key |
| COMMERCE_SHOPIFY_SYNC_TOKEN | At least 32 random bytes for internal sync/export/reconciliation jobs |
| COMMERCE_ENVIRONMENT | Set to production in production so OAuth state cookie is Secure |
| SHOPIFY_INVENTORY_RESERVATION_PRODUCTION_ENABLED | Default false; set true only after live Shopify/Stripe staging acceptance, PostgreSQL restore validation, and operational compensation/refund procedures are signed off. Until then, Shopify-backed checkout is staging-only. |
| SHOPIFY_COMPENSATION_SCOPE_ENABLED | Default false. When true, new/re-authorized OAuth installs request the additional `write_orders` scope needed for order cancellation. Existing merchants must re-authorize. Keep disabled unless the merchant compensation policy and operator process are approved. |

Do not commit secrets or put the encryption key in the app frontend. Rotate the token encryption key only with a planned re-encryption migration; changing it directly makes existing token ciphertext unreadable and requires merchants to re-authorize.

Requested scopes:

- read_products
- read_inventory
- read_locations
- read_orders
- read_draft_orders
- write_draft_orders

Optional compensation scope (requested only when `SHOPIFY_COMPENSATION_SCOPE_ENABLED=true`):

- write_orders

The connector no longer uses orderCreate; draftOrderCreate/draftOrderComplete/draftOrderDelete require draft-order permissions. The optional `write_orders` permission is used only for the irreversible `orderCancel` compensation path. The Shopify staff account/app installation must also be authorized to cancel orders (`cancel_orders` staff permission) for Shopify's structured `OrderCancelJobResult` to be readable. This is a Shopify Admin user permission, not an OAuth API scope that Cirvanna can grant. If either authorization is missing, the case is blocked for operator review; the connector does not silently widen permissions or attempt cancellation. The read scope is used only to reconcile the deterministic draft reservation by ID/tag; the connector does not request or persist draft customer, address, or contact fields.

No customer profile scope is requested. The order/draft-order read scopes can expose customer-associated fields, but connector GraphQL projections deliberately exclude customer, email, phone, billing and shipping fields; none of those values are synchronized or persisted. Shopify order creation deliberately excludes buyer PII.

## Implemented API surface

### Merchant-authenticated

| Method and path | Purpose |
|---|---|
| GET /integrations/shopify/install?shop=<store>.myshopify.com | Start OAuth; requires a signed merchant identity and approved Commerce merchant |
| GET /integrations/shopify/callback | Validate Shopify HMAC, one-use state and browser state cookie; exchange code for expiring offline tokens |
| GET /integrations/shopify/connection | Read connection, granted scopes, webhook and sync status; never returns tokens |
| POST /integrations/shopify/disconnect | Revoke local token material |
| POST /integrations/shopify/sync/products | Manually reconcile product, variant, shop-currency and inventory snapshots |
| GET /integrations/shopify/staged-products | Inspect merchant-private staging products and mappings |
| POST /integrations/shopify/products/{snapshot_id}/map | Map selected variants to verified Catalog product/variant IDs |
| POST /integrations/shopify/markets/{country_code}/sync-pricing | Read Shopify Markets contextual item prices for a declared operating market |
| GET /integrations/shopify/readiness | Report connection, scope, webhook and sync readiness |

### Shopify/platform and internal jobs

| Method and path | Authentication | Purpose |
|---|---|---|
| POST /webhooks/shopify | Shopify Base64 HMAC-SHA256 | Verify and durably queue allowlisted delivery metadata; duplicate delivery IDs are idempotent |
| POST /internal/shopify/process-events | X-Commerce-Shopify-Sync-Token | Process product, inventory, order-status and compliance events |
| POST /internal/shopify/export-paid-orders | X-Commerce-Shopify-Sync-Token | Create external Shopify order records only for already-paid Cirvanna orders |
| POST /internal/shopify/reconcile | X-Commerce-Shopify-Sync-Token | Re-read Shopify product/inventory and linked order status to recover missed/out-of-order webhooks |
| POST /internal/shopify/compensate-paid-orders | X-Commerce-Shopify-Sync-Token | Reconcile failed paid-order completions, cancel/restock only when safe, and request a Stripe refund only after every seller is compensated |

Configure an external scheduler to call the three internal jobs on a controlled cadence. Keep the sync token server-side; never route these endpoints through a public browser session.

## Product and inventory semantics

Product sync pages Shopify's top-level productVariants connection with a persisted cursor, so stores larger than one worker batch continue across repeated sync/reconciliation runs. Each complete product page and its continuation cursor are committed together under a durable per-store lease; concurrent webhook/reconciliation workers cannot sync the same store simultaneously, and a provider failure on a later page resumes from the last durable cursor rather than replaying the entire catalogue. A crashed lease expires after 120 minutes and is then reclaimable. The lease exceeds the bounded worst-case nested inventory-page budget (20 variants × 20 extra location pages × 12 seconds per provider request). It snapshots title, handle, vendor, product type, Shopify status, remote update time, variant identifiers/options/SKUs, shop-base unit price and inventory item/location quantities. It is not a Catalog create operation. A merchant must select an existing Catalog product and the exact canonical Catalog variant ID for every variant they intend to offer.

Shopify inventory is location-scoped. Inventory-level locations are independently cursor-paginated (first 50, then bounded 100-row pages); every location and quantity must be complete and active. The bounded location-page limit is fail-closed: if Shopify reports more pages than Cirvanna can safely read, the aggregate remains inventory-incomplete and cannot be reserved or sold. Missing IDs, unknown location activity, duplicate inventory-level or location IDs, repeated cursors, malformed page envelopes, duplicate/missing quantity names, boolean/malformed quantities and partial pages are not treated as zero stock; they are unavailable evidence and are withheld. The sync aggregates available and on_hand only across active locations. Cirvanna sets its local on_hand to Shopify's aggregated available quantity plus Cirvanna's currently reserved quantity. This preserves available_stock = on_hand - reserved_qty while preventing stock already committed in Shopify from being oversold through Cirvanna. Inventory movements are recorded for reconciliation.

If tracking is disabled, locations are missing/inactive, inventory pagination is incomplete, stock is malformed, or Shopify's available quantity cannot safely accommodate Cirvanna reservations, the local variant observation is made stale and held out of the fresh-offer path. Do not replace this with an assumption of unlimited availability. A full, cursor-complete catalogue cycle is required before the connector retires variant snapshots that disappeared from Shopify; those local variants are deactivated and excluded from future mapping. Partial sync batches never infer deletion. An archived/deleted Shopify product disables its mapped Commerce listing/variant; a later reactivation requires a deliberate merchant action.

Product and inventory webhooks are coalesced per Shopify store within each claimed worker batch: a store receives one full catalogue sync even if many product/inventory notifications arrive together. If that sync fails, every event for that store remains retryable without repeating the same expensive provider call in that batch. Large stores continue through the persisted product cursor on subsequent reconciliations. Reconciliation also verifies/repairs each store's webhook subscriptions before syncing products and order status. The authenticated reconciliation endpoint is paginated across stores with `connection_limit` and `after_connection_id`; it returns `next_after_connection_id`, `webhooks_verified` and explicit `failed_connection_ids`, which can be retried individually using `connection_id`. Readiness exposes `products_sync_complete`, `products_sync_has_more` and `products_sync_in_progress` separately from connection/webhook readiness.

## Currency and regional pricing

Shop-base prices are normalized into integer minor units using Babel/CLDR currency precision, retaining the exact ISO currency code. The connector never converts money using a guessed exchange rate.

Shopify Markets contextualPricing is stored as a separate, country-keyed merchant item-price observation. It is not written into Variant.price_minor, OfferFXQuote, tax, fulfilment or payment-capability records. A Shopify contextual price alone is not an FX settlement quote or a landed consumer price. Marketplace comparison and localized checkout continue to require the current Commerce provider evidence for FX, destination-zone fulfilment, authoritative tax and payment capability.

## Order creation and status

Only a Commerce order already in paid state can be exported. The worker creates one Shopify sub-order per connected merchant, uses the exact mapped Shopify variant IDs, includes the immutable seller source price in shop currency and the immutable buyer-presentment amount/currency where available, and marks the Shopify order paid as an external import (sourceName=Cirvanna, a deterministic link tag, and an explicit note). It does not charge a buyer in Shopify. No customer identity, email, phone or shipping address is sent.

The connector refuses export if merchant source currency does not equal the connected shop currency, if any line lacks a mapped Shopify variant, or if fulfilment/tax/other non-item charges have not been allocated to the merchant sub-order. This avoids creating a Shopify record whose money silently disagrees with the immutable Cirvanna order. Multi-merchant orders generate separate seller-side Shopify order records. A durable link row is written before the remote create; if the API times out, the worker searches for the stable link tag before retrying to avoid duplicate orders.

Before Stripe Checkout Session creation, Commerce creates one Shopify draft order per connected seller sub-order with a deterministic Cirvanna reservation tag and reserveInventoryUntil equal to the Commerce checkout expiry. Each draft uses the immutable seller source price snapshot as a Shopify priceOverride in the shop currency, so a merchant price edit between catalog sync and checkout cannot silently change the seller-side order value. Shopify's draft-order reservation is the provider-side stock hold; local Commerce reservations alone never count as proof. Ambiguous create outcomes are reconciled by the stable tag and remain fail-closed if they cannot be resolved. If any seller reservation fails, known remote drafts are deleted, local reservations are released and no Stripe session is created. For any checkout containing a Shopify-backed seller, Stripe Checkout is restricted to card payments; delayed-settlement methods are disabled because the provider inventory hold expires with the checkout and must not lapse before payment confirmation. Non-Shopify checkouts retain the existing Stripe payment-method configuration.

After a verified Stripe payment, the paid-order worker completes the reserved Shopify draft. Draft completion commits the held Shopify inventory exactly once; the connector no longer uses orderCreate with DECREMENT_OBEYING_POLICY, avoiding a second decrement. On confirmed Stripe expiry or asynchronous payment failure, draft reservations are deleted idempotently; Shopify's reserveInventoryUntil remains the expiry safety net if the release call cannot be confirmed.

A paid order with Shopify reservations enters `provider_pending`; the paid ownership event remains valid for Wardrobe but explicitly carries `fulfillment_ready=false`. Merchant order responses also expose `fulfillment_ready=false`. Commerce changes this to `ready` only after every Shopify reservation is completed and every provider order link is synchronized. If a terminal completion failure occurs, the order enters `compensation_pending` and cannot be exported or fulfilled through the Shopify order worker.

The internal `/internal/shopify/compensate-paid-orders` worker first reconciles each exact draft tag/GID. Drafts without a created order are deleted and confirmed released. If Shopify already created an order, the worker checks fulfillment state and—only when the optional `write_orders` scope is granted—calls `orderCancel` with `restock=true` and Shopify-side refund disabled. The structured `OrderCancelJobResult` is polled until `done=true`; the result must report `status=SUCCEEDED`, no errors and an affected order with `cancelledAt`. Before cancellation, Cirvanna records fresh `available` quantities for every mapped inventory item and requires every returned location to be active. After the job succeeds, it re-reads all inventory-level pages and requires the available quantity for each inventory item to increase by at least the ordered quantity. A missing/inactive location, incomplete inventory mapping, pagination gap, or insufficient restock delta goes to `manual_review`; this deliberately prefers a blocked refund over silently losing seller stock. `orderCancel` is irreversible. Shopify can reject cancellation for pending payment authorizations, active returns, outstanding fulfillments that cannot be cancelled, or restocking to a deactivated location. Active/fulfilled work, any provider cancellation error, missing app/staff permission, ambiguous mutation outcomes, and non-Shopify sellers in a multi-seller order go to `manual_review`; no buyer refund is issued automatically in those cases.

Only after every seller in the Commerce order has a confirmed compensated Shopify case does Commerce create one durable full Stripe refund attempt. It uses a stable idempotency key and refund metadata; ambiguous requests are reconciled against Stripe's refund list and are never retried beyond the safe 20-hour idempotency window without operator review. The order is not marked refunded until a verified `refund.created`/`refund.updated` event confirms a succeeded refund with the exact amount/currency. The `charge.refunded` cumulative snapshot remains monotonic. A confirmed refund changes financial/fulfilment state only; it does not imply a physical return or delete Wardrobe ownership.

This is a distributed saga, not a cross-provider atomic transaction. Provider timeouts, webhook ordering, draft expiry and partial multi-seller reservation failures still require live Shopify/Stripe staging tests, PostgreSQL restore evidence and an operational compensation/refund procedure before production. The connector must remain staging-only until those tests pass.

Shopify order webhook/reconciliation status updates only the Shopify link's financial and fulfilment status. It cannot mark a Cirvanna order paid, refund it, release its inventory, or alter the buyer's order state. Only Cirvanna's verified Stripe payment/refund webhooks and the authenticated compensation worker may change the corresponding Commerce financial/fulfilment state.

## Webhook and privacy handling

Webhook HMAC is checked against the raw request bytes before parsing. The queue stores the shop domain, delivery/event IDs, topic, remote resource ID and payload digest—not the raw body—so customer or address fields are not accidentally persisted. Event processing is idempotent; retries use bounded attempts and dead-letter after repeated failures. Stale processing jobs are reclaimable after worker interruption. A merchant disconnect or app/uninstalled event immediately clears encrypted token material and quarantines all Shopify-backed listings/variants from shopper availability; a later reconnection requires a complete inventory sync and explicit merchant reactivation. shop/redact deletes the connection's linked product/order data. Customer data request/redact deliveries are acknowledged without lookup because customer data is not requested or stored.

Manual-review outbox events are not leased to the Wardrobe Sync worker. They remain in the durable Commerce operations inbox at `GET /admin/operations/alerts` for authenticated administrators; `POST /admin/operations/alerts/{event_id}/acknowledge` records that an operator has seen the alert but does not resolve the underlying case. The Marketplace BFF exposes these admin-only routes. Shopify compensation and Stripe refund manual-review alerts therefore cannot be retried into the Sync worker's unsupported-event dead-letter path.

Webhook delivery order is not guaranteed, and delivery itself is not a complete synchronization mechanism. Keep scheduled reconciliation enabled and monitor pending/dead-letter counts.

## Required staging acceptance before production

1. Run alembic upgrade head against an isolated PostgreSQL database and prove a backup restore. Confirm alembic_version=20261121_0014 and that all nine Shopify/compensation tables exist.
2. Register the Shopify app scopes, callback and webhook URLs. Install against a development store and verify state mismatch/replay, HMAC mismatch, wrong shop domain, OAuth exchange failure, missing scopes, token refresh/rotation and expiry recovery.
3. Confirm both access and refresh token ciphertext are encrypted at rest and absent from logs, HTTP responses, error bodies and frontend assets. Verify uninstall removes token material.
4. Sync a product with multiple variants and multiple inventory locations. Test duplicate/empty SKUs, inactive locations, untracked inventory, incomplete pagination, zero stock, stock decrement/increment, and Cirvanna reservations concurrent with Shopify stock changes.
5. Map a product to an existing Catalog identity. Test wrong product/variant mapping, cross-merchant snapshot access, duplicate canonical variants, unapproved merchant, archived/deleted product and partial mapping. Prove no unmapped Shopify product can reach a shopper.
6. Verify regional contextual price observations preserve currency and are never treated as landed prices without fresh FX, tax, fulfilment and payment evidence.
7. Verify checkout creates a Shopify draft-order reservation for every connected seller before Stripe session creation. Test stale stock, final-unit contention, multi-seller partial failure, duplicate retry, ambiguous draft-create timeout and release on Stripe expiry/payment failure. Prove no Stripe session is created unless all required Shopify reservations are confirmed.
8. Use a real Stripe test-paid Cirvanna order to verify each reserved draft is completed exactly once and the Shopify inventory decrement is not repeated. Test completion timeout/reconciliation, expired holds, currency mismatch, unallocated shipping/tax and unmapped variants. Confirm no duplicate remote order and no second buyer charge.
9. Replay, duplicate and reorder webhook deliveries; test worker restart, dead-letter, uninstall, shop redact and scheduled full reconciliation.
10. Verify every shopping surface still requires fresh Decision Gateway/CAL SHOW and every cart/checkout action still requires its own candidate-bound purchase authorization. Do not enable a public Shopify browse endpoint.
11. Attach exact-commit CI, database migration/restore, provider sandbox and end-to-end evidence to the release record. Live deployment, Shopify Partner configuration, real store authorization, real webhook delivery, actual inventory reconciliation and order export remain unproven until these checks are performed.

The connector is not production-ready merely because its routes or migration exist. Provider credentials, app distribution policy, operational scheduler, live environment, monitoring, rollback and independently reviewed release evidence remain deployment gates.
