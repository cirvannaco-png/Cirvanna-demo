# Cirvanna private asset service

**Status:** provider-neutral application boundary implemented; an S3-compatible object store and PostgreSQL still must be provisioned and live-tested.

This service is the sole private binary boundary for Twin source images, Twin representations, catalog/wardrobe garment images, try-on outputs, appearance source photos and appearance render outputs. It stores only opaque asset metadata in Postgres and binary objects in private S3-compatible object storage. Use AWS S3 or a compatible object-storage provider by configuring the endpoint; product services do not receive public URLs or direct bucket credentials.

## Contracts

- `POST /internal/v1/assets`: trusted service upload with owner, purpose and parent binding for still images; content is decoded, orientation-normalized and EXIF-stripped before being stored as PNG. This image endpoint rejects `twin_representation` so a PNG cannot be mislabeled as a full-body mesh. Appearance source photos use `appearance_source_image` with the new look ID as parent; rendered outputs use `appearance_render_output` with their look ID as parent.
- `POST /internal/v1/twin-meshes`: trusted service upload for the canonical Twin representation. It accepts only `model/gltf-binary` GLB 2.0, up to 100 MiB, checks the GLB header/chunks, embedded buffer, mesh/float32 `POSITION` accessors and rejects external buffer/image URIs. It stores the original GLB bytes privately and returns an opaque asset ID plus byte size and SHA-256. It does **not** validate body geometry, topology quality, anatomical coverage, scale, measurement accuracy, identity fidelity or privacy leakage; a separately configured validator must inspect the actual stored bytes before Twin Registry enrollment.
- `POST /internal/v1/assets/authorize`: verifies exact owner, asset purpose, parent record, active status and retention window. The Twin Registry bulk contract (`asset_ids`, `purpose=virtual_twin_storage`, exact `parent_id`) must contain exactly one GLB `twin_representation` and at least one normalized PNG `twin_source_image` or `twin_person_image`, all for that owner and Twin parent.
- `GET /internal/v1/assets/{asset_id}/content`: returns image or GLB bytes only when owner, purpose and parent all match. Responses are private and `no-store`; GLB reads are SHA-256 checked and rechecked for container validity.
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

The service normalizes image orientation and strips EXIF metadata from image uploads; Twin GLB representations are stored byte-for-byte after container validation. It keeps objects private, does not issue presigned public URLs, enforces subject/purpose/parent ownership on reads, and checks asset expiry on access. Deletion removes the private object and marks its metadata deleted; repeated deletion is safe. Configure a bucket lifecycle policy as a second line of defense and run reconciliation for metadata rows whose physical deletes fail.

The service does not infer identity or grant consent. The calling domain service must verify current purpose-specific consent before uploading or reading Twin source images, GLB representations or try-on output. The Asset Service enforces owner, binary purpose, exact parent binding and format boundary independently. GLB container checks are not the independent mesh validator and must never be used as evidence of a valid body model. The bulk Twin deletion endpoint is idempotent for the same owner/parent; the Twin registry's deletion outbox remains responsible for command-key conflict detection and retry orchestration.

## Local tests

```sh
python -m pip install -r services/asset-service/requirements.txt
cd services/asset-service
python -m pytest -q
```

CI fakes the S3 client. Production promotion requires a real object-store bucket, a least-privilege key, Postgres migration/backup verification, private network policy, deletion/reconciliation tests and a live staging smoke test.
