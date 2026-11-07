# Wardrobe service

**Status:** authenticated API and SQLAlchemy persistence contract implemented; production database and object-storage deletion worker still require deployment and validation.

The service owns user wardrobe item records and saved outfit compositions. Item records include lifecycle, catalog-product references, user-authorized opaque image asset IDs, explicit photo-storage consent, optimistic version checks and a durable asset-deletion outbox. Saved outfits contain references to active, owner-scoped wardrobe items; they do not copy Catalog facts or make unpurchased marketplace products owned. The PostgreSQL schema is applied through ordered migrations `0001_initial.sql`, `0002_wardrobe_learning_events.sql` and `0003_saved_outfits.sql` and `0004_verified_purchase_ownership.sql`; `0005_outfit_wear_history.sql` adds consented outfit-level wear snapshots. The application does not automatically create the production schema. SQLite is test-only.

## Configuration

- `WARDROBE_DATABASE_URL`: production must use `postgresql+psycopg://`.
- `WARDROBE_SERVICE_TOKEN`: internal bearer token, at least 32 bytes.
- `WARDROBE_ASSET_DELETION_READY=true`: only set after the worker has been deployed, authenticated and tested end-to-end. The API stays not-ready while the outbox would have no capable consumer.

## API

- `POST /v1/items` creates an owner-scoped user-added item.\n- `POST /v1/purchases/verified` accepts only a trusted internal `commerce.order.paid` event with `ownership_authority=verified_payment`; it creates one owner-scoped purchased line item and deduplicates by Commerce order-line ID. The record retains order/event provenance, quantity, currency, agreed unit price and paid timestamp. Missing product taxonomy is explicitly marked `other` for user correction, not guessed.
- `GET /v1/items?owner_user_id=...` lists only the requested owner's items.
- `GET /v1/items/{item_id}?owner_user_id=...` gets an owner-scoped item.
- `POST /v1/items/{item_id}/transition` applies a version-checked lifecycle command.
- `PATCH /v1/items/{item_id}` edits only one owned item with optimistic concurrency and command replay protection.
- `POST /v1/outfits` creates a saved outfit from active items owned by the same user.\n- `POST /v1/outfits/{outfit_id}/wear` records a consented, version-checked outfit-wear event, snapshots the exact pieces and delivers idempotent item-level wear signals to USI/TAL.\n- `GET /v1/wear-history` returns the owner-scoped wear history for outfit graph and anti-repeat ranking.
- `GET /v1/outfits?owner_user_id=...` lists that user's saved outfits and hydrates each piece from its current wardrobe item record.
- `POST /v1/outfits/{outfit_id}/pieces` adds one owned item to an outfit.
- `PATCH /v1/outfits/{outfit_id}/pieces/{slot_id}` replaces or removes one piece; every unaffected piece remains unchanged. Mutations require expected version and command ID.
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

Apply migrations in order: `0001_initial.sql`, `0002_wardrobe_learning_events.sql`, then `0003_saved_outfits.sql`, then `0004_verified_purchase_ownership.sql`, then `0005_outfit_wear_history.sql`. The learning table is an audit mirror; USI/TAL and NPL remain the authoritative stores. Service readiness now requires the `wardrobe_outfits` table as well as the existing item, learning and deletion-outbox schema.


Outfit wear events are an auditable history foundation, not yet a recommendation-ranking policy. Anti-repeat cooldowns, frequency balancing, context-aware diversity, user-edit/rejection metrics and offline evaluation must be implemented and validated separately before enabling automatic look rotation.
