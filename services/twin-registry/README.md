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
- `POST /internal/v1/twins/revoke`: revokes the Twin metadata and blocks future authorization.
- `GET /ready`: validates schema reachability and required identity, asset-service and model-validation credentials are configured. It does not claim a GPU renderer or production deployment is live.

No endpoint accepts or returns public URLs, file-system paths, object-store keys, signed download links or image/mesh bytes.

## Required configuration

- `TWIN_REGISTRY_DATABASE_URL`: managed PostgreSQL; SQLite is test-only.
- `TWIN_REGISTRY_API_TOKEN`: unique high-entropy service token, at least 32 bytes.
- `TWIN_REGISTRY_VALIDATION_HMAC_SECRET`: independent secret shared only by the trusted model-validation pipeline and this registry.
- `CONSENT_API_URL` / `CONSENT_API_TOKEN`: current Identity Consent service.
- `ASSET_SERVICE_URL` / `ASSET_SERVICE_TOKEN`: current private Asset Service.

Apply `migrations/0001_twin_registry.sql` through the approved migration process. Do not enable production auto-create schema.

## Remaining release gates

1. Deploy a licensed, pinned full-body mesh model and an independently reviewed mesh-quality validator that produces the signed validation attestation. Current pose inference is not a mesh.
2. Configure managed PostgreSQL, Asset Service private object storage, consent service, service secrets and deletion propagation; complete restore and failure drills.
3. Run multi-tenant ownership, asset revocation, consent revocation/expiry, model rollback and concurrency/replay tests against staging providers.
4. Connect and validate a licensed commercial renderer and output lifecycle. The registry itself never renders.
5. Keep Try-On unavailable until consent, Twin, Asset Service, renderer, private output storage and output validation are all independently operationally verified.

Unit tests use SQLite and mocked internal providers; they do not demonstrate live provider operation or physical fit accuracy.
