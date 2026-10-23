# Wardrobe service

**Status:** authenticated API and SQLAlchemy persistence contract implemented; production database and object-storage deletion worker still require deployment and validation.

The service owns user wardrobe item records, including item lifecycle, catalog-product references, user-authorized opaque image asset IDs, explicit photo-storage consent, optimistic version checks and a durable asset-deletion outbox. The PostgreSQL schema is in `migrations/0001_initial.sql`. The application does not automatically create the production schema. SQLite is test-only.

## Configuration

- `WARDROBE_DATABASE_URL`: production must use `postgresql+psycopg://`.
- `WARDROBE_SERVICE_TOKEN`: internal bearer token, at least 32 bytes.
- `WARDROBE_ASSET_DELETION_READY=true`: only set after the worker has been deployed, authenticated and tested end-to-end. The API stays not-ready while the outbox would have no capable consumer.

## API

- `POST /v1/items` creates an owner-scoped item.
- `GET /v1/items?owner_user_id=...` lists only the requested owner's items.
- `GET /v1/items/{item_id}?owner_user_id=...` gets an owner-scoped item.
- `POST /v1/items/{item_id}/transition` applies a version-checked lifecycle command.
- Moving an image-bearing item to deleted records a pending asset deletion in the same transaction. This confirms enqueueing only; it does not mean an object has been physically purged.

All routes are internal. The trusted ingress must bind the caller's authenticated user to `owner_user_id`; do not pass through an arbitrary client-supplied owner ID from public ingress without comparing it to the verified identity. Catalog remains the owner of product metadata; Wardrobe stores only catalog IDs.

## Verification

    python -m pip install -r requirements.txt
    python -m pytest -q

Production promotion requires real PostgreSQL migration/restore tests, concurrent version/conflict tests, live object-store deletion worker and retry/DLQ validation, audit delivery, and ingress identity-binding tests.
