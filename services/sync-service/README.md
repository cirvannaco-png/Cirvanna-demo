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

## Run

    python -m pip install -r requirements.txt
    python -m app.worker --once
    python -m app.worker

The container runs the long-lived worker. The worker does not log event payloads, user identifiers, tokens or exception text.

## Verification and release gates

    python -m pytest -q

Tests use mocked Commerce and Wardrobe endpoints. Before production, apply both service migrations, configure secrets, run a real signed Stripe test checkout, verify delivery and replay in PostgreSQL, inject downstream outages, verify dead-letter alerts and reconcile event counts. Refund/cancellation ownership reconciliation is blocked until Commerce implements those lifecycle events.