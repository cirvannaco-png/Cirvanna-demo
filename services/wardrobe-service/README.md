# Wardrobe service

**Status:** pure wardrobe domain kernel implemented; API and durable storage are not yet implemented.

The canonical value object and lifecycle rules live in `packages/wardrobe`. This service will own PostgreSQL wardrobe records and user-authorized opaque asset references. Catalog product metadata remains Catalog-owned; wardrobe records may store the catalog product ID but must not duplicate or write the catalog product table.

The domain covers draft, active, archived and deleted states; owner-only transitions; monotonically increasing item versions; same-command idempotency; terminal deletion state; and explicit image-storage consent for opaque asset references. It does not store image bytes, accept arbitrary URLs, or claim to physically delete an object-storage asset.

## Remaining implementation gates

- PostgreSQL repository and migrations, with transactional version checks and uniqueness for commands.
- Authentication and per-user row-level authorization.
- Asset-service authorization, retention, deletion worker and audit delivery.
- Catalog lookup contract and end-to-end integration tests.
- Backup/restore and concurrency validation.
