# Xari compatibility package

Xari is a retired runtime name. The only canonical implementation is now
[services/pnelly](../pnelly). This directory is a compatibility shim for
existing deployments, imports and XARI/TARI configuration during the migration.

The shim preserves these v1 HTTP contracts:

- GET /health, /ready and /capabilities
- POST /v1/route
- POST /v1/marketplace/search

Request/response schemas, consent keys and historic XARI_* error codes remain
stable. Configuration precedence is PNELLY_API_TOKEN, then XARI_API_TOKEN,
then TARI_API_TOKEN. New deployments must use PNELLY variables. All aliases
resolve to the same runtime and state; no second assistant may be deployed.

Do not add business logic here. Update services/pnelly and keep this shim tested.
Remove it only after observing zero legacy traffic for the agreed migration period.
