# Cirvanna private asset service

**Status:** provider-neutral application boundary implemented; an S3-compatible object store and PostgreSQL still must be provisioned and live-tested.

This service is the sole private binary boundary for Twin source images, Twin representations, catalog/wardrobe garment images, try-on outputs, appearance source photos and appearance render outputs. It stores only opaque asset metadata in Postgres and binary objects in private S3-compatible object storage. Use AWS S3 or a compatible object-storage provider by configuring the endpoint; product services do not receive public URLs or direct bucket credentials.

## Contracts

- `POST /internal/v1/assets`: trusted service upload with owner, purpose and parent binding for still images; content is decoded, orientation-normalized and EXIF-stripped before being stored as PNG. This image endpoint rejects `twin_representation` so a PNG cannot be mislabeled as a full-body mesh. Appearance source photos use `appearance_source_image` with the new look ID as parent; rendered outputs use `appearance_render_output` with their look ID as parent.
- `POST /internal/v1/twin-meshes`: trusted service upload for the canonical Twin representation. It accepts only `model/gltf-binary` GLB 2.0, up to 100 MiB, checks the GLB header/chunks, embedded buffer, mesh/float32 `POSITION` accessors and rejects external buffer/image URIs. It stores the original GLB bytes privately and returns an opaque asset ID plus byte size and SHA-256. It does **not** validate body geometry, topology quality, anatomical coverage, scale, measurement accuracy, identity fidelity or privacy leakage; a separately configured validator must inspect the actual stored bytes before Twin Registry enrollment.
- `POST /internal/v1/assets/authorize`: verifies exact owner, asset purpose, parent record, active status and retention window. The Twin Registry bulk contract (`asset_ids`, `purpose=virtual_twin_storage`, exact `parent_id`) must contain exactly one GLB `twin_representation` and at least one normalized PNG `twin_source_image` or `twin_person_image`, all for that owner and Twin parent.
- `POST /internal/v1/assets/{asset_id}/publication/approve`: requires exact owner, active image asset, consent receipt, masking attestation and target surface. It calls Privacy Governance over authenticated HTTPS, which verifies active resource-bound consent and exact-byte masking evidence with independent human review. It stores the returned receipt IDs and exact approved surface; any provider failure, mismatch, revoked consent or minor-media publication request is denied.
- `POST /internal/v1/assets/{asset_id}/publication/revoke`: owner-bound, idempotent revocation; switches scope to private-only and records the revocation timestamp. This changes authorization metadata; downstream publisher/cache/CDN unpublishing still requires explicit integration and confirmation.
- `GET /internal/v1/assets/{asset_id}/content`: returns image or GLB bytes only when owner, purpose and parent all match. Responses are private and `no-store`; GLB reads are SHA-256 checked and rechecked for container validity.
- `DELETE /v1/assets/{asset_id}`: idempotent owner-checked deletion. Compatible with Wardrobe's existing deletion outbox worker.
- `POST /internal/v1/assets/delete`: parent-bound Twin deletion contract. It verifies all requested assets belong to the same owner and exact parent, then deletes all Twin source/representation and derived try-on assets under that parent. Replays return the same deleted asset set.
- `GET /ready`: verifies database connectivity, object-store access and privacy controls. Bucket versioning must be absent/disabled; Enabled or Suspended versioning fails readiness because the current delete path does not remove historical object versions.

### Lifecycle provenance contract

Migration `0002_asset_lifecycle_provenance.sql` adds provider-neutral lifecycle fields to each asset row:

- `asset_role`: source, derivative, representation or legacy unclassified. New uploads are classified from their declared purpose; pre-migration rows remain unclassified.
- `source_asset_id` and `source_sha256`: reserved for a derivative's exact source-asset relationship and source digest. For newly ingested source images, `source_sha256` records the digest of the received bytes before EXIF-stripping/re-encoding; `sha256` remains the digest of the stored normalized bytes. Derivative source links are not yet populated by the upload contract.
- `transformation_name` and `transformation_version`: transformation provenance references; currently nullable and not asserted by this service.
- `consent_receipt_id` and `consent_version`: exact resource-bound consent receipt identity and version.
- `masking_attestation_id`, `masking_model_sha256`, `human_privacy_review_receipt_id`, `human_privacy_reviewer_ref` and `human_privacy_reviewed_at`: the exact masking attestation, approved model digest and independent human-review provenance returned by Privacy Governance. These are persisted only after the trusted response matches the exact asset digest, subject, consent receipt and destination surface.
- `publication_scope`, `publication_state` and `revoked_at`: every new upload defaults to `private_only`. No upload parameter or public URL is provided to elevate that state. Database constraints require an approved-public scope and a consent reference before approval/publication; all image assets additionally require a masking-attestation reference (including a verifier result for images where no face is detected). Revocation requires a timestamp.

The approval endpoint now delegates to Privacy Governance for active resource-bound consent and exact-asset masking-attestation verification, then persists the verified consent/attestation references and exact target surface. This is a storage authorization transition, **not** proof that every public publisher, share-link resolver, restore path, CDN or cache checks the state at delivery time. No public-serving endpoint is implemented here. Revocation updates the authoritative row but does not yet prove downstream unpublishing/cache purge. Derivative lineage and transformation metadata also remain unpopulated. Never publish bytes based only on an approved row unless the serving route independently checks the current state and exact surface.

Every operation is private and requires `ASSET_SERVICE_TOKEN`. Cross-tenant or wrong-purpose probes return 404. Asset IDs are opaque UUIDs; callers must not use URLs as asset identifiers. All responses containing image bytes are marked no-store.

## Configuration

- `ASSET_DATABASE_URL`: existing managed PostgreSQL URL (SQLite test-only).
- `ASSET_SERVICE_TOKEN`: unique internal bearer token, at least 32 bytes.
- `ASSET_S3_BUCKET`, `ASSET_S3_ACCESS_KEY_ID`, `ASSET_S3_SECRET_ACCESS_KEY`, `ASSET_S3_REGION`.
- `ASSET_S3_ENDPOINT_URL`: optional S3-compatible endpoint; non-local endpoints must use HTTPS.
- The service's runtime object-store identity must be able to read bucket public-access, bucket policy status, encryption, ownership controls and versioning state. In particular, it needs `s3:GetBucketVersioning`; missing/unsupported control reads fail readiness.
- `ASSET_AUTO_CREATE_SCHEMA`: local/test only. Apply `migrations/0001_asset_objects.sql` followed by `migrations/0002_asset_lifecycle_provenance.sql` in staging/production.

## Privacy and lifecycle

The service normalizes image orientation and strips EXIF metadata from image uploads; Twin GLB representations are stored byte-for-byte after container validation. It keeps objects private, does not issue presigned public URLs, enforces subject/purpose/parent ownership on reads, and checks asset expiry on access. Readiness requires bucket versioning to be absent or disabled: Enabled or Suspended versioning can preserve prior object versions after a normal delete and is rejected. Deletion removes the private object and marks its metadata deleted; repeated deletion is safe only under the required non-versioned bucket configuration. Configure a bucket lifecycle policy as a second line of defense and run reconciliation for metadata rows whose physical deletes fail. If versioning is required by the storage provider, implement and independently test version-aware deletion of every object version and delete marker before changing this readiness gate.

The service does not infer identity or grant consent. The calling domain service must verify current purpose-specific consent before uploading or reading Twin source images, GLB representations or try-on output. The Asset Service enforces owner, binary purpose, exact parent binding and format boundary independently. GLB container checks are not the independent mesh validator and must never be used as evidence of a valid body model. The bulk Twin deletion endpoint is idempotent for the same owner/parent; the Twin registry's deletion outbox remains responsible for command-key conflict detection and retry orchestration.

## Local tests

```sh
python -m pip install -r services/asset-service/requirements.txt
cd services/asset-service
python -m pytest -q
```

CI fakes the S3 client. Production promotion requires a real object-store bucket, a least-privilege key, Postgres migration/backup verification, private network policy, deletion/reconciliation tests and a live staging smoke test.


### Flat-lay-only Virtual Try-On source purposes

Two additional source purposes are available for the first maskless VTON mode: `catalog_garment_flat_lay` and `wardrobe_garment_flat_lay`. They remain private source assets. Only trusted catalog/wardrobe ingestion paths may assign these purposes after the image has been reviewed/classified as a flat-lay garment image. Generic `catalog_garment_image` and `wardrobe_garment_image` assets are not eligible for the parser-free renderer.
