# Cirvanna Twin Registry

**Status:** canonical owner-bound Twin metadata and authorization API implemented. It is not a mesh generator, binary object store, or production proof of a validated avatar pipeline.

## Single sources of truth

- **Twin Registry** owns the persistent Twin ID, owner, model/release provenance, validation-report digest, representation type and source-asset references.
- **Asset Service** remains the only authority for binary bytes, asset IDs, tenant ownership, active/revoked state, private storage and deletion lifecycle. Twin Registry does not duplicate its asset table or store object keys.
- **Identity Learning / Consent** remains the only authority for resource-bound consent. Twin Registry verifies the exact subject, consent ID, consent version, Twin resource ID and required scopes on creation and every authorization.
- **Virtual Try-On** owns renderer orchestration and job persistence; it asks Twin Registry for the owner-bound full-body mesh and source-image asset IDs, then resolves bytes through Asset Service.
- **Virtual Twin** owns ephemeral image/pose inference and Click It candidate retrieval. A pose skeleton is not a persistent Twin and does not satisfy the full-body-mesh registration contract.
- **CAL** remains the only authority for display; registry authorization is not product-display authorization.

## Internal contract

All routes except `/health` require the internal `TWIN_REGISTRY_API_TOKEN` bearer.

- `POST /internal/v1/twins`: registers a Twin only after a trusted model-validation HMAC, active resource-bound consent and Asset Service authorization of the mesh plus all source images.
- `POST /internal/v1/twins/authorize`: re-checks owner, active consent/version, mesh and every source asset on every call. Its response includes `representation_type=full_body_mesh` and `source_image_asset_ids` required by the current Virtual Try-On contract.
- `POST /internal/v1/twins/deactivate`: immediately blocks authorization and creates a versioned deletion-outbox command.
- `POST /internal/v1/twins/revoke-consent`: queues deletion for every active Twin belonging to the exact owner and withdrawn consent receipt.
- `POST /internal/v1/twins/deletions/dispatch`: a separately authenticated worker dispatches idempotent deletion to Asset Service and marks records deleted only after the provider confirms the full asset set.
- `GET /internal/v1/twins/{twin_id}/status`: returns owner-scoped lifecycle state and version.
- `POST /internal/v1/twins/revoke`: compatibility route; it now queues deletion rather than merely flipping a metadata flag.
- `GET /ready`: validates schema reachability, consent, asset, validation and deletion credentials. It does not claim a GPU renderer or production deployment is live.

No endpoint accepts or returns public URLs, file-system paths, object-store keys, signed download links or image/mesh bytes.

## Required configuration

- `TWIN_REGISTRY_DATABASE_URL`: managed PostgreSQL; SQLite is test-only.
- `TWIN_REGISTRY_API_TOKEN`: unique high-entropy service token, at least 32 bytes.
- `TWIN_REGISTRY_VALIDATION_HMAC_SECRET`: independent secret shared only by the trusted model-validation pipeline and this registry.
- `TWIN_REGISTRY_DELETION_TOKEN`: separate high-entropy token for the asset-deletion worker; never reuse the registry API token.
- `CONSENT_API_URL` / `CONSENT_API_TOKEN`: current Identity Consent service.
- `ASSET_SERVICE_URL` / `ASSET_SERVICE_TOKEN`: current private Asset Service.

Apply `migrations/0001_twin_registry.sql` followed by `migrations/0002_twin_registry_deletion_outbox.sql` through the approved migration process. The `0002` downgrade must only be used after no record remains in `deletion_pending`/`deleted` state and the outbox is empty. Do not enable production auto-create schema. CI applies both migrations, exercises the downgrade/re-upgrade path, and verifies a PostgreSQL dump/restore.

## Remaining release gates

1. Deploy a licensed, pinned full-body mesh model and an independently reviewed mesh-quality validator that produces the signed validation attestation. Current pose inference is not a mesh.
2. Configure managed PostgreSQL, Asset Service private object storage, consent service, service secrets and deletion propagation; complete restore and failure drills.
3. Run multi-tenant ownership, asset revocation, consent revocation/expiry, model rollback and concurrency/replay tests against staging providers.
4. Connect and validate a licensed commercial renderer and output lifecycle. The registry itself never renders.
5. Keep Try-On unavailable until consent, Twin, Asset Service, renderer, private output storage and output validation are all independently operationally verified.

Unit tests use SQLite and mocked internal providers; they do not demonstrate live provider operation or physical fit accuracy.
