# Cirvanna Virtual Twin and Click It API

**Status:** guarded pose-inference and Click It contracts plus a persistent Twin metadata-registry foundation. No production reconstruction worker, purpose-specific consent provider, mesh validator or asset provider is deployed/configured.

## Implemented flow

### Virtual Twin

POST /twin accepts **one still full-body image**, declared height, subject_id, consent_id, and explicit image/body-measurement consent flags. It requires a durable server-side consent receipt, forwards the image to the private Vision Intelligence service, and returns an ephemeral 3D pose skeleton with landmark visibility and image-quality diagnostics.

It does **not** create or persist a Twin record, generate a full body-surface mesh, make calibrated body measurements, or certify clothing fit. The response labels the result as partial inference and requires downstream review.

### Click It

POST /click-it accepts a product photo, subject_id, consent_id, the Twin ID and explicit image-processing/Click It consent flags. Before sending image bytes to the model worker, it verifies durable consent and verifies that the Twin is active and belongs to the requesting subject. It then runs image-quality checks and CLIP-based retrieval against live Commerce offers enriched by active Catalog product descriptions/attributes.

The response contains candidates, not display-authorized items. display_authorized is always false and decision_status is PENDING_CAL: downstream policy must apply NPL, explicit cultural identity requirements and CAL before presenting or acting on the candidates. Candidate scores are similarities, not probabilities.

Photo matching currently compares the input image embedding with text/metadata for each available offer. It does not yet compare to every catalog product photograph. A result may therefore be approximate; the UI should let the user confirm the intended product. Neither endpoint persists images, and successful responses carry Cache-Control: no-store, private.

## Required internal integrations

The adapters intentionally **fail closed** until these configurations and matching service contracts are available:

- VIRTUAL_TWIN_API_TOKEN: internal API bearer secret. Never place it in a browser.
- VISION_INTELLIGENCE_API_URL: private trusted HTTPS base URL of services/vision-intelligence.
- VISION_INTELLIGENCE_API_TOKEN: internal worker token, at least 32 bytes, identical to VISION_WORKER_TOKEN on that service.
- CONSENT_API_URL and CONSENT_API_TOKEN: trusted identity/consent service and internal token. This service calls POST /internal/v1/consents/verify with subject_id, consent_id, required_scopes, and (for Click It) resource_id. It requires JSON containing verified=true, active=true, the same subject_id and consent_id, granted_scopes covering every requested scope, and the same resource_id when one was supplied. Consent must be revocable and checked at request time.
- TWIN_REGISTRY_API_URL and TWIN_REGISTRY_API_TOKEN: point to this service's trusted internal base URL and the same private credential configured as VIRTUAL_TWIN_REGISTRY_TOKEN. The /internal/v1/twins/authorize endpoint is implemented, but requires the database migration and the consent, mesh-validation and asset providers below.

The registry API and SQL migration now exist in source control; this does not prove that a production database, consent provider, mesh validator or asset provider is deployed. A user-supplied subject_id is not authentication; only trusted server-side callers may call this service.

## Failure behavior

- 400/403: explicit or verified consent is missing/invalid, Twin access is denied, or image content is empty.
- 413/415/422: image bounds, MIME/content, pose/quality or body-landmark checks failed.
- 503/504: worker, consent verifier, Twin registry, credentials or inference dependencies are missing or unavailable.
- 502: a downstream response is malformed or inference fails unexpectedly.

Failure payloads use stable opaque codes and do not forward bearer secrets, full upstream bodies, local paths or stack traces. The API does not silently return demo products or fake Twin geometry.

## Remaining release gates

1. Deploy the pinned Vision Intelligence service and provision the CLIP revision and checksummed MediaPipe model asset.
2. Apply the reviewed Twin registry migration to the approved PostgreSQL instance and validate backup/restore; deploy the purpose-specific consent, independent mesh-validation, and asset authorization/deletion providers against the actual identity issuer and object store.
3. Put the service behind a trusted user-authenticated backend. Do not rely on form booleans or a client-submitted identity for proof.
4. Connect the returned candidate set to the real CAL decision gateway and verify NPL/cultural hard vetoes before UI display.
5. Run labeled image-quality and retrieval tests plus a consented full-body evaluation covering body/skin-tone variation, pose/occlusion and garment types. Confirm retention, redaction, alerting and incident response.

## Persistent Twin registry foundation

The API now includes a **database-backed metadata registry** for a validated Twin artifact. This is separate from the `POST /twin` pose-inference endpoint: that endpoint still returns an ephemeral pose skeleton and never registers it as a saved Twin. The registry accepts only `representation_type=full_body_mesh`; it does not generate meshes, infer measurements, or certify fit.

### Registry operations

- `POST /internal/v1/twins/register` registers a full-body mesh asset reference only after current consent and ownership of the derived mesh plus every source-image asset are verified.
- `POST /internal/v1/twins/authorize` checks the subject/Twin ownership pair, active record state, current consent receipt/version, and all referenced assets on every authorization request.
- `POST /internal/v1/twins/deactivate` immediately changes the record to `deletion_pending`, blocks new authorization, and writes an asset-deletion outbox command.
- `POST /internal/v1/twins/revoke-consent` is the trusted consent-service callback for queueing deletion of Twins created under a withdrawn receipt.
- `POST /internal/v1/twins/deletions/dispatch` is a separately authenticated worker operation. A Twin is marked `deleted` only after the asset service confirms deletion of all requested assets. Provider failure leaves the record pending and retryable.
- `GET /internal/v1/twins/{twin_id}/status?subject_id=...` returns lifecycle metadata to an authenticated internal caller.

### Required configuration and provider contracts

- `VIRTUAL_TWIN_DATABASE_URL`: the approved existing PostgreSQL instance, not a new hosting-provider-specific database. Apply `migrations/0001_virtual_twin_registry.sql` through the controlled migration process; production schema auto-creation is not supported.
- `VIRTUAL_TWIN_REGISTRY_TOKEN`: a private machine credential of at least 32 bytes for registry calls. Never expose it in browser code.
- `VIRTUAL_TWIN_DELETION_TOKEN`: a distinct private credential for the deletion dispatcher.
- `CONSENT_API_URL` / `CONSENT_API_TOKEN`: the consent provider must return a verified, active receipt for the same subject, receipt ID and consent version, with all scopes `image_processing`, `body_measurements`, and `virtual_twin_storage`, for purpose `virtual_twin_persistence`.
- `TWIN_VALIDATION_API_URL` / `TWIN_VALIDATION_API_TOKEN`: a separate validator endpoint `POST /internal/v1/twins/validate-mesh` must inspect the actual stored artifact and return an active validation receipt bound to the same subject, Twin ID, asset ID, representation type and exact model version. A caller-provided `full_body_mesh` label alone is never accepted.
- `TWIN_ASSET_API_URL` / `TWIN_ASSET_API_TOKEN`: trusted asset provider endpoints `POST /internal/v1/assets/authorize` and `POST /internal/v1/assets/delete`. Authorization must echo the exact subject and all requested asset IDs. Deletion must be idempotent, cascade to derived artifacts, and return a deletion receipt covering every requested asset.
- For Click It integration, set `TWIN_REGISTRY_API_URL` to this service's trusted internal base URL and `TWIN_REGISTRY_API_TOKEN` to the registry credential; the service calls `/internal/v1/twins/authorize`.

All registry endpoints require internal bearer authentication; deletion dispatch requires the separate `X-Twin-Deletion-Token`. The registration caller must be a trusted backend/generator that has independently validated a full-body mesh. Client-supplied subject IDs and form booleans are not identity or consent evidence.

### Completion boundary

This is a persistence and authorization foundation, **not a live Twin-generation system**. The repository still has no validated full-body reconstruction worker, deployed general-purpose consent provider for the required scopes, or asset authorization/deletion provider implementing these contracts. Consequently, no real user can yet register or render a persistent Twin in production. The asset-deletion worker remains unavailable until the provider exists. Virtual Try-On remains independently disabled until its renderer, asset authorizer, consent verifier and output validation are operational.

## Optional Xari and Complementer assistance

Xari may be offered as an optional conversational guide from the Virtual Twin experience. Complementer may be invoked through Xari, or surfaced as an explicit optional styling action, for advisory look coordination. Both remain outside this service's ownership: the Twin service owns its consent-gated representation and authorization; Complementer owns styling advice; Catalog/Commerce own product truth; FCI owns calibrated fit evidence; CAL owns display authorization.

The present pose-skeleton response is not a persistent full Twin. Do not present it as a saved avatar or enable marketplace Try-On until a user-scoped Twin registry, persistent asset authorization and the separate Virtual Try-On renderer are operational.