# Cirvanna Virtual Twin and Click It API

**Status:** the API now has a real worker adapter contract. The worker can perform partial pose inference and CLIP-based marketplace-candidate retrieval when its pinned models and trusted services are configured. No production worker, consent provider or Twin registry is currently assumed to exist.

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
- TWIN_REGISTRY_API_URL and TWIN_REGISTRY_API_TOKEN: trusted Twin registry. This service calls POST /internal/v1/twins/authorize with subject_id and twin_id, and requires authorized=true, active=true, and matching IDs.

No existing deployed consent or Twin-registry endpoint was found in the repository, so these adapter contracts do not imply that those services are live. Do not expose the service until those contracts are implemented and tested against the actual identity provider and persistent Twin store. A user-supplied subject_id is not authentication; only trusted server-side callers may call this service.

## Failure behavior

- 400/403: explicit or verified consent is missing/invalid, Twin access is denied, or image content is empty.
- 413/415/422: image bounds, MIME/content, pose/quality or body-landmark checks failed.
- 503/504: worker, consent verifier, Twin registry, credentials or inference dependencies are missing or unavailable.
- 502: a downstream response is malformed or inference fails unexpectedly.

Failure payloads use stable opaque codes and do not forward bearer secrets, full upstream bodies, local paths or stack traces. The API does not silently return demo products or fake Twin geometry.

## Remaining release gates

1. Deploy the pinned Vision Intelligence service and provision the CLIP revision and checksummed MediaPipe model asset.
2. Implement/configure the real consent-verification and Twin-ownership adapters using the actual identity issuer and persistent Twin registry.
3. Put the service behind a trusted user-authenticated backend. Do not rely on form booleans or a client-submitted identity for proof.
4. Connect the returned candidate set to the real CAL decision gateway and verify NPL/cultural hard vetoes before UI display.
5. Run labeled image-quality and retrieval tests plus a consented full-body evaluation covering body/skin-tone variation, pose/occlusion and garment types. Confirm retention, redaction, alerting and incident response.
