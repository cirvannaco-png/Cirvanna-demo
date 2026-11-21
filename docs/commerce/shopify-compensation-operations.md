# Shopify compensation manual-review operations

Paid Shopify-backed orders that cannot be safely compensated remain blocked from fulfilment and create a durable Commerce outbox event. The Sync-to-Wardrobe worker must not claim these events: it consumes only checkout-started, paid-order and refund-status contracts.

## Operator queue

An authenticated Commerce administrator can poll:

- `GET /admin/operations/manual-review?limit=50`

The endpoint returns only unacknowledged Shopify compensation and Stripe refund manual-review events. It exposes a minimized operational projection: event/order/case identifiers, merchant identifier where applicable, reason code, action requirement and fulfilment-blocked state. It does not expose Shopify customer, address or contact payloads.

After an operator has taken ownership of the case, acknowledge it with:

- `POST /admin/operations/manual-review/{event_id}/ack`
- JSON body: `{"action":"acknowledged" | "escalated" | "resolved","operator_note":"optional, max 500 characters"}`

Acknowledgement marks the queue item delivered and writes a separate deterministic `commerce.operations.manual_review.acknowledged` audit event containing the admin subject, action and acknowledgement timestamp. Acknowledgement is not proof that the underlying compensation or refund is complete; the order remains fulfilment-blocked until the appropriate recovery workflow changes its state.

## Shop redaction during compensation

Before Shopify `shop/redact` removes provider-linked connection, reservation and compensation rows, Commerce transitions every unresolved compensation case to manual review and writes the minimal order-level recovery event. The event survives provider-row deletion and is visible in the operator queue. No Shopify customer/contact/address payload is copied into the recovery event.

## Operational requirements

- Poll and staff the admin queue; this endpoint is a durable operator inbox, not an email/SMS/Slack alert.
- Investigate the exact provider state before manually changing order or refund state.
- Do not acknowledge a case as resolved merely because the queue item was read.
- Keep Shopify-backed production checkout disabled until live development-store cancellation, Stripe refund, PostgreSQL concurrency, worker scheduling and staffed manual-review procedures are evidenced.
