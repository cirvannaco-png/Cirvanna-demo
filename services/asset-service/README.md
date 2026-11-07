# Cirvanna private asset service

**Status:** provider-neutral application boundary implemented; an S3-compatible object store and PostgreSQL still must be provisioned and live-tested.

This service is the sole private binary boundary for Twin source images, Twin representations, catalog/wardrobe garment images and try-on outputs. It stores only opaque asset metadata in Postgres and image bytes in private S3-compatible object storage. Use AWS S3 or a compatible object-storage provider by configuring the endpoint; product services do not receive public URLs or direct bucket credentials.

## Contracts

- `POST /internal/v1/assets`: trusted service upload with owner, purpose and parent binding; image bytes are validated and EXIF is stripped before storing as PNG.
- `POST /internal/v1/assets/authorize`: verifies exact owner, asset purpose, parent record, active status and retention window. It also supports the Twin registry's bulk contract (`asset_ids`, `purpose=virtual_twin_storage`, and exact `parent_id`) and returns the complete authorized ID set.
- `GET /internal/v1/assets/{asset_id}/content`: returns bytes only when owner, purpose and parent all match.
- `DELETE /v1/assets/{asset_id}`: idempotent owner-checked deletion. Compatible with Wardrobe's existing deletion outbox worker.
- `POST /internal/v1/assets/delete`: parent-bound Twin deletion contract. It verifies all requested assets belong to the same owner and exact parent, then deletes all Twin source/representation and derived try-on assets under that parent. Replays return the same deleted asset set.
- `GET /ready`: verifies database connectivity and object-store bucket access; a process health check is not storage readiness.

Every operation is private and requires `ASSET_SERVICE_TOKEN`. Cross-tenant or wrong-purpose probes return 404. Asset IDs are opaque UUIDs; callers must not use URLs as asset identifiers. All responses containing image bytes are marked no-store.

## Configuration

- `ASSET_DATABASE_URL`: existing managed PostgreSQL URL (SQLite test-only).
- `ASSET_SERVICE_TOKEN`: unique internal bearer token, at least 32 bytes.
- `ASSET_S3_BUCKET`, `ASSET_S3_ACCESS_KEY_ID`, `ASSET_S3_SECRET_ACCESS_KEY`, `ASSET_S3_REGION`.
- `ASSET_S3_ENDPOINT_URL`: optional S3-compatible endpoint; non-local endpoints must use HTTPS.
- `ASSET_AUTO_CREATE_SCHEMA`: local/test only. Apply `migrations/0001_asset_objects.sql` in staging/production.

## Privacy and lifecycle

The service normalizes image orientation and strips EXIF metadata, keeps objects private, does not issue presigned public URLs, enforces subject/purpose/parent ownership on reads, and checks asset expiry on access. Deletion removes the private object and marks its metadata deleted; repeated deletion is safe. Configure a bucket lifecycle policy as a second line of defense and run reconciliation for metadata rows whose physical deletes fail.

The service does not infer identity or consent. The calling domain service must verify current purpose-specific consent before uploading or reading a Twin/try-on image. The asset service enforces ownership, asset purpose and exact parent binding independently. The bulk Twin deletion endpoint is idempotent for the same owner/parent; the Twin registry's deletion outbox remains responsible for command-key conflict detection and retry orchestration.

## Local tests

```sh
python -m pip install -r services/asset-service/requirements.txt
cd services/asset-service
python -m pytest -q
```

CI fakes the S3 client. Production promotion requires a real object-store bucket, a least-privilege key, Postgres migration/backup verification, private network policy, deletion/reconciliation tests and a live staging smoke test.
