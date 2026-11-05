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


## Wardrobe learning integration

Internal endpoint POST /v1/feedback records a clear user interaction against an active wardrobe item. The trusted BFF must resolve the end-user using Commerce /me and bind owner_user_id to that verified subject. The browser must not supply a trusted subject ID directly.

- like, wear and modify are advisory positive signals persisted through purpose-scoped USI/TAL events; they do not directly create a hard preference.
- dislike is delivered to NPL as a learned rejection. NPL's existing three-unique-event threshold governs when it becomes a hard veto.
- avoid is a user-declared NPL exclusion and is therefore an immediate hard veto while active.
- A negative target must be the item itself or an attribute actually present on the owned wardrobe item. Unknown material or style claims cannot be learned from an ungrounded label.
- The API requires an active style_learning or personalization receipt from Identity Learning. Revocation and denial are respected on each write. Feedback events are event-ID idempotent, payload immutable, and user scoped.
- The Wardrobe service does not import the quarantined CFRP V6 candidate or emit the unverified CRFP concept. See ADR-0002 and issue #76; neither is authorized in runtime.
- Configure IDENTITY_SERVICE_URL, IDENTITY_SERVICE_TOKEN, NPL_SERVICE_URL, and NPL_SERVICE_TOKEN in the service secret manager. Missing providers or consent fail closed.

Apply migrations/0002_wardrobe_learning_events.sql after 0001_initial.sql. This table is an audit mirror; USI/TAL and NPL remain the authoritative stores.
