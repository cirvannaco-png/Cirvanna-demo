# Cirvanna Virtual Try-On

**Status:** persistent orchestration contract with private asset and Twin-registry integration. The first real-inference mode is restricted to flat-lay garment images and maskless person preprocessing. It remains unavailable until production consent, registry, PostgreSQL, private storage, pinned model artifacts and a GPU worker are independently configured and verified.

## Ownership

- Virtual Twin owns the canonical user representation and source asset references.
- Identity/Consent owns purpose-specific, resource-bound consent.
- Asset Service owns private binary storage, authorization, integrity and deletion.
- Virtual Try-On owns request reservation, renderer orchestration, provenance and output lifecycle.
- Catalog/Commerce own product truth; Wardrobe owns owned garments and outfit snapshots; CAL owns display authorization; FCI owns calibrated fit evidence.

## API and trust boundary

- `POST /v1/try-ons` accepts opaque private asset IDs only; no raw uploads, URLs or filesystem paths.
- Requests are internal service-to-service calls. The trusted BFF must derive the subject from its verified session; a browser-supplied subject ID is never authentication.
- Consent is checked server-side for `image_processing`, `virtual_try_on` and `virtual_twin_storage`, bound to the exact Twin resource and rechecked after inference and before completion.
- Twin authorization uses canonical `POST /internal/v1/twins/authorize`; it returns full-body mesh metadata and authorized source-image asset IDs. A pose skeleton is not a persistent Twin.
- Person, garment and output assets are checked against the private Asset Service for exact owner, purpose and parent. No public object URLs are issued.
- A durable PostgreSQL reservation is acquired before GPU work. Concurrent duplicate requests cannot launch duplicate renders; failed/stale reservations can be retried under the same payload hash and lease rules.
- Jobs retain look ID/version and wardrobe snapshot version when supplied, plus consent version, asset references and renderer/model provenance.

## Render lifecycle

1. Verify current consent and canonical Twin ownership.
2. Atomically reserve the subject/request idempotency key in PostgreSQL.
3. Authorize and resolve person and garment assets from private storage.
4. Invoke the pinned private worker with bounded timeout and validated image inputs; only `garment_photo_type=flat-lay` is accepted.
5. Re-check consent, Twin ownership and source asset authorization after inference.
6. Persist output privately, then re-check consent/Twin and authorize the stored output before marking complete.
7. On failure, delete any new output and mark the reservation failed; never report a placeholder as complete.

The visual result is not a fit guarantee. The pinned FASHN VTON 1.5 worker uses `segmentation_free=True` and a flat-lay garment image, so the separately licensed Human Parser package is not installed or invoked. Model-worn garment images are rejected until a replacement parser's code, weights and training-data provenance are cleared for commercial use. Real GPU inference, model-weight checksums, deployment and representative quality evaluation remain mandatory.

## Configuration

- `VIRTUAL_TRY_ON_DATABASE_URL`: managed PostgreSQL; SQLite is test-only.
- `VIRTUAL_TRY_ON_API_TOKEN`: internal BFF/service token.
- `CONSENT_API_URL` / `CONSENT_API_TOKEN`: trusted consent verifier.
- `TWIN_REGISTRY_API_URL` / `TWIN_REGISTRY_API_TOKEN`: canonical Twin registry endpoint and registry token.
- `ASSET_SERVICE_URL` / `ASSET_SERVICE_TOKEN`: private Asset Service.
- `VTON_WORKER_URL` / `VTON_WORKER_TOKEN`: private GPU worker.

Apply `migrations/0001_virtual_try_on_jobs.sql` through approved migrations. Do not auto-create production schema.

## Validation

The dedicated workflow runs API tests and builds the container. Tests use fakes and do not prove live providers, GPU inference, image realism, fit accuracy, deployment security, commercial rights or Android acceptance.


## 2026-11-21: first real inference mode

The orchestration API now accepts and forwards only `garment_photo_type="flat-lay"`. The private worker uses the pinned FASHN VTON 1.5 pipeline with `segmentation_free=True`, and its image build excludes the separately licensed Human Parser dependency. Model-worn garment photos are rejected. This is a genuine model-inference path once the pinned weights and GPU worker are provisioned; current CI uses a mock pipeline and does not prove GPU readiness or visual quality.


### Supported inference mode

The orchestration API and worker advertise `supported_garment_photo_types=["flat-lay"]`. The API rejects `model` garment photos. The worker forces `segmentation_free=True` and `garment_photo_type="flat-lay"` server-side, so client input cannot switch the pipeline into parser-dependent masking. CI uses mock inference and does not establish visual quality or a live GPU deployment.

## Dependency readiness semantics

The orchestration service's `GET /ready` and `GET /capabilities` do not treat a syntactically valid URL/token pair as a live dependency. They make bounded HTTPS readiness probes to the Consent, Asset Service and Twin Registry providers, require an authenticated HTTP 200 response with `ready=true`, and probe the pinned GPU worker's own readiness endpoint. A configured-but-unreachable, unauthorized, malformed or non-ready upstream keeps the orchestrator unavailable. These probes establish service readiness only; they do not certify rendering quality, fit accuracy, provider rights or production acceptance.
