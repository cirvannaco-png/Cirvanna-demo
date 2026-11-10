# Sync service

**Owner:** Commerce outbox delivery, Wardrobe purchase ownership handoff, retries and replay. **Status:** worker implementation and mocked contract tests added; deployment and live integration remain open.

## Commerce-to-Wardrobe ownership flow

1. Commerce emits `commerce.order.paid` only inside the verified Stripe settlement transaction.
2. This worker leases events through Commerce's authenticated internal outbox API.
3. It validates event type, schema version, event ID and `ownership_authority=verified_payment`.
4. It maps every immutable order line to Wardrobe's internal `POST /v1/purchases/verified` contract.
5. It acknowledges Commerce only after every line is accepted by Wardrobe.
6. On any failure, it requests bounded retry/dead-letter handling from Commerce. If the worker crashes before acknowledgement, the Commerce lease expires and the event can be replayed.
7. Wardrobe deduplicates each order line by owner and Commerce order-item ID, so partial delivery and replay do not create duplicate owned items.

Delivery is **at least once**, not exactly once. The idempotent Wardrobe sink is the protection against duplicate effects.

## Configuration

- `COMMERCE_SERVICE_URL`
- `COMMERCE_SYNC_TOKEN` — dedicated Commerce outbox credential, minimum 32 bytes.
- `WARDROBE_SERVICE_URL`
- `WARDROBE_SERVICE_TOKEN` — internal Wardrobe bearer credential, minimum 32 bytes.
- `SYNC_WORKER_ID` — stable worker identity.
- Optional: `SYNC_BATCH_SIZE` (1–100), `SYNC_TIMEOUT_SECONDS`, `SYNC_POLL_SECONDS`.

Do not reuse end-user JWTs or expose either service credential to browsers. Use the secret manager for deployment.

## Consent-bound checkout learning

Commerce snapshots an optional canonical TAL consent receipt onto the order at checkout. The receipt is resolved only after the identity service verifies the authenticated buyer, active personalization scope, bundle version and non-resource-bound consent. Checkout remains available when the user does not opt into personalization; an invalid supplied consent bundle fails closed.

For a verified paid order with that receipt, Sync emits one idempotent checkout.purchase_choice observation to the Identity Learning/TAL service after Wardrobe purchase ownership has been accepted and before acknowledging the Commerce outbox event. The observation contains only the buyer subject, opaque product/variant/merchant IDs, quantities, minor-unit prices, currency, order total, fulfilment mode and payment-method family. It excludes product names, email, delivery address, payment credentials, bank details and raw order snapshots. It is a weak transaction signal, never a permanent taste declaration, USI mutation or NPL hard veto. The TAL sink independently checks that the receipt is still active; revoked/invalid consent skips learning without blocking ownership synchronization. Identity sink outages retry the Commerce outbox event.

Configuration for this optional sink:
- IDENTITY_SERVICE_URL
- IDENTITY_SERVICE_TOKEN — internal Identity Learning service credential, minimum 32 bytes. Configure both or neither. A consented order cannot be acknowledged as fully synchronized if the TAL sink is not configured.

This is paid-purchase learning only. It does not yet capture abandoned checkouts, item removals/replacements before purchase, or uncompleted payment-method/fulfilment selections. Those need separate consented checkout interaction events; absence of a purchase must never be interpreted as dislike.

## Run

    python -m pip install -r requirements.txt
    python -m app.worker --once
    python -m app.worker

The container runs the long-lived worker. The worker does not log event payloads, user identifiers, tokens or exception text.

## Verification and release gates

    python -m pytest -q

Tests use mocked Commerce and Wardrobe endpoints. Before production, apply both service migrations, configure secrets, run a real signed Stripe test checkout, verify delivery and replay in PostgreSQL, inject downstream outages, verify dead-letter alerts and reconcile event counts. The worker now consumes Commerce's `commerce.order.refund.updated` event and writes the verified cumulative refund snapshot to Wardrobe's separate financial ledger; this is financial-state reconciliation only, not ownership reversal. Physical returns, cancellation lifecycle events, chargebacks/disputes, item-level allocation and restocking remain blocked pending their own verified Commerce events and operational workflows.
## Event types and ownership truth

The worker consumes two Commerce outbox event types:

- `commerce.order.paid`: a signed Stripe-paid settlement with immutable order-line snapshots. Each line is idempotently materialized as a Wardrobe purchase record before the event is acknowledged.
- `commerce.order.refund.updated`: a signed Stripe `charge.refunded` cumulative order-level refund snapshot. It is validated against the trusted provider authority, amount, currency, order, PaymentIntent and event schema before it is written to Wardrobe's owner/order refund ledger.

A refund snapshot is financial state only. It never archives, deletes, or de-owns garment records and must explicitly declare `physical_return_confirmed=false`. Partial refunds and full refunds are not proof of a physical return. Returns, chargebacks, item-level refund allocation and inventory restocking remain separate verified workflows. Unknown or malformed event types are never acknowledged as successful.

