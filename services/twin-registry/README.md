# Cirvanna Twin Registry

**Status:** persistent owner-bound Twin and asset metadata API implemented; storage data plane and full-mesh production pipeline remain separate release gates.

## Ownership

This internal service is the canonical registry for persistent Twin records and asset metadata. It stores no image or mesh bytes and exposes no download URLs. A trusted upload/renderer must write bytes to a private object store, validate the exact file, and then register the opaque storage object key and cryptographic digest. Do not accept a user-supplied URL, path, bucket, or public object URL.

Private assets are isolated to a tenant whose identifier equals the verified owner subject. Catalog garment assets are explicitly registered as catalog-visible and bound to a canonical Catalog product ID. Authorization checks both the owned Twin and the exact person/garment asset pair for the requested product.

## Internal APIs

All endpoints except `/health` require the private `TWIN_REGISTRY_API_TOKEN` bearer.

- `POST /internal/v1/assets/register`: register metadata after a trusted storage adapter has written and validated bytes; returns a server-generated opaque asset ID.
- `POST /internal/v1/twins`: persist a Twin only when its private mesh asset belongs to the same subject/Twin and a pinned model revision, model-release SHA-256 and validation-report SHA-256 are supplied by a trusted validated pipeline.
- `POST /internal/v1/twins/authorize`: the Virtual Twin service uses this exact subject/Twin authorization contract.
- `POST /internal/v1/assets/authorize`: the Try-On authorizer uses this to bind a user's reference asset, owned Twin, catalog/user garment asset and canonical product.
- `POST /internal/v1/twins/revoke`: revoke the Twin and block future authorization.
- `POST /internal/v1/assets/revoke`: revoke a private asset; revoking the registered mesh also revokes its Twin.
- `GET /ready`: checks the database tables exist and are reachable.

No API returns storage object keys to browsers. The registry is metadata/authorization only: it does not create 3D meshes, upload bytes, issue object-store credentials, or prove that a model output is physically accurate. The model artifact and validation report hashes are bound into a canonical HMAC-SHA256 validation attestation. Configure the same independent `TWIN_REGISTRY_VALIDATION_HMAC_SECRET` only in the trusted validation pipeline and this registry. Registry readiness and Twin creation fail closed without it. This proves the attested fields were signed by the trusted pipeline; it does not replace independent model-quality evaluation.

## Database

Use the existing approved managed PostgreSQL instance with a dedicated table namespace. Apply `migrations/0001_twin_registry.sql`; never enable auto-create schema in production. Configure:

- `TWIN_REGISTRY_DATABASE_URL`: existing managed PostgreSQL URL.
- `TWIN_REGISTRY_API_TOKEN`: independent high-entropy internal service token (at least 32 bytes).
- `TWIN_REGISTRY_VALIDATION_HMAC_SECRET`: separate high-entropy attestation secret (at least 32 bytes), accessible only to the trusted mesh-validation pipeline and the registry.

Local tests use SQLite:

```sh
python -m pip install -r services/twin-registry/requirements.txt
cd services/twin-registry
python -m pytest -q
```

## Remaining production gates

1. Provision private object storage and a trusted image/mesh ingest adapter that hashes bytes, strips image metadata, validates decoded dimensions/pixels, enforces tenant ownership and registers only after successful storage.
2. Deploy a pinned full-body mesh model and validation pipeline; current Virtual Twin pose inference is not a mesh and cannot register as a persistent Twin.
3. Configure the identity service consent bundles for `twin_storage`, `asset_storage`, `asset_reuse` and other exact purposes; verify and revoke at request time.
4. Connect the real Try-On renderer to a private asset resolver and output storage adapter. A registered metadata record alone is not an image renderer.
5. Validate tenant isolation, revocation, deletion propagation, storage lifecycle and independent model quality before enabling any Try-On action.
