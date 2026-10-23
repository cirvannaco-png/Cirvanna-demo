# Wardrobe domain

**Status:** deterministic item and lifecycle contract implemented; API, durable storage, asset lifecycle, and service integration remain unimplemented.

This package owns the user wardrobe item model and allowed state transitions. It deliberately stores only opaque image asset IDs, never image bytes or arbitrary URLs. Adding an image asset requires explicit storage consent. Item access is owner-scoped, and deletion is represented as a lifecycle transition that a durable service must audit and execute.

## Lifecycle

- `draft -> active | archived | deleted`
- `active -> archived | deleted`
- `archived -> active | deleted`
- `deleted` is terminal.

The domain kernel is pure Python. It does not imply that a database exists or that a deletion event has physically purged stored assets. Production promotion requires a PostgreSQL-backed repository, row/tenant isolation, event idempotency, audit delivery, retention/deletion workers, catalog contract tests, and authorization integration.
