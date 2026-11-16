# Appearance Intelligence service

**Status:** persistent, owner-scoped look-session API and version history implemented. The service does not render images, store image bytes, or make appearance measurements. Production deployment remains blocked until managed PostgreSQL, Identity Learning, Asset Service and (for Twin-backed looks) Twin Registry are configured and independently tested.

## Ownership

- This service owns the versioned look composition, edit history, favorite state and render-fidelity metadata.
- Identity Learning owns explicit consent. Every create, edit, reset, undo, favorite and branch operation verifies an active, expiring consent receipt bound to the exact subject and look resource.
- Asset Service owns binary source and rendered images. This service stores opaque asset IDs only and verifies exact owner, purpose and parent binding.
- Twin Registry owns persistent Twin metadata and its authorization lifecycle. The appearance service accepts a Twin only after Twin Registry authorizes the current subject and confirms a full-body representation.
- Virtual Try-On or another separately approved renderer owns image generation. It must use a dedicated renderer credential to attach a result and supply a complete fidelity assessment.
- PNELLY and the Marketplace BFF are clients. They cannot nominate a subject ID; the BFF must resolve the user's identity through Commerce GET /me and bind it to the internal request.
- CAL remains the only product-display authority. This service does not authorize Marketplace product display or checkout.

## API

All routes except /health require an internal bearer token. They are private service APIs, not browser endpoints.

- POST /v1/looks: create a persistent photo- or Twin-based look. Source-photo assets must already exist in Asset Service with purpose appearance_source_image and exact parent look_id. The request is authorized by appearance_session_storage, appearance_source_storage and image_processing consent; Twin-backed looks additionally require a currently authorized Twin.
- GET /v1/looks/{look_id}: retrieve the current composition for its verified subject.
- GET /v1/looks/{look_id}/versions: retrieve immutable version metadata.
- GET /v1/looks/{look_id}/compare?from_version=N&to_version=M: compare component operations across two versions.
- POST /v1/looks/{look_id}/operations: apply or replace one component operation with optimistic concurrency and command idempotency.
- POST /v1/looks/{look_id}/reset: create a new version with no transformations, returning to that look's chosen base.
- POST /v1/looks/{look_id}/undo: create a new version from an earlier version in the same look history.
- POST /v1/looks/{look_id}/favorite: set the saved/favorite state.
- GET /internal/v1/looks/{look_id}/consent-context: private minimum metadata to renew a session after expiry.
- POST /internal/v1/looks/{look_id}/renew-consent: bind a newly verified consent bundle and append an immutable consent-renewal event.
- POST /v1/looks/{look_id}/branch: create a new look from a previously rendered version only when its output has a passing fidelity assessment and Asset Service authorizes the output.
- DELETE /v1/looks/{look_id}: soft-delete a look and create a durable outbox job to revoke its exact consent bundle and delete appearance-owned assets that are not referenced by another active look.
- POST /internal/v1/deletions/process: retry queued, failed or stale-processing deletion jobs. It is protected by the private service token.
- POST /internal/v1/looks/{look_id}/render-result: renderer-only handoff, protected by a separate APPEARANCE_RENDERER_TOKEN. It accepts only SHA-256-pinned renderer revisions, exact look/version binding and a complete fidelity report whose gates are releasable.

A render result is attached to a specific immutable look version. An edit creates a new version and does not silently carry forward the old render asset. A failed or uncertain fidelity report is rejected; it cannot become the base of a later branch.

## Consent model

The new appearance_session_storage scope is distinct from DSI analysis, Twin storage, image processing, style learning and global model training. A source-photo look requires appearance_session_storage, appearance_source_storage and image_processing in one resource-bound bundle whose resource is the exact look ID. Renewal after expiry creates a new bundle; source-photo renewal requires session-storage, source-storage and image-processing consent, while Twin-backed renewal requires only session-storage consent. A Twin-based look requires the session-storage grant for the new look; the Twin Registry separately checks the Twin's existing consent and owner authorization. Consent is rechecked at each read, mutating operation and before a render result is attached. An expired grant blocks access until the BFF records fresh explicit consent; renewal preserves the previous bundle ID, new bundle ID, version and scope set in append-only history.

## Data and privacy

- No source or output image bytes are persisted here.
- No public image URLs or arbitrary filesystem paths are accepted.
- Only opaque private asset references and normalized look metadata are stored.
- All responses are private/no-store through the BFF.
- Database rows use owner-scoped queries; a mismatched subject returns not-found.
- Each mutation uses an expected version and a command ID. Replaying the same command/payload returns its prior version; reusing a command with a different payload returns a conflict.
- The service does not store prompts, transcripts, face embeddings, raw DSI observations or training data.
- Look deletion is durable: the service stores a deletion job before contacting Identity Learning or Asset Service. One resource-bound receipt revokes the full exact consent bundle. Asset deletion is owner-scoped and idempotent; a render still referenced by an active child look is retained until the final reference is removed. Failed operations remain in the outbox and stale `processing` jobs are retryable. `.github/workflows/appearance-deletion-reconciliation.yml` runs every 15 minutes once the `APPEARANCE_SERVICE_URL` and `APPEARANCE_SERVICE_TOKEN` repository secrets are configured. The workflow's existence is not evidence that production secrets or live provider access are configured.

## Configuration

- APPEARANCE_DATABASE_URL: managed PostgreSQL URL in production; SQLite only for tests.
- APPEARANCE_SERVICE_TOKEN: private BFF/service bearer, at least 32 bytes.
- APPEARANCE_RENDERER_TOKEN: separate renderer-only bearer, at least 32 bytes.
- The deletion reconciliation workflow also needs repository secrets `APPEARANCE_SERVICE_URL` and `APPEARANCE_SERVICE_TOKEN`; do not reuse a renderer credential for this purpose.
- IDENTITY_SERVICE_URL / IDENTITY_SERVICE_TOKEN.
- ASSET_SERVICE_URL / ASSET_SERVICE_TOKEN.
- TWIN_REGISTRY_API_URL / TWIN_REGISTRY_API_TOKEN for Twin-based looks.
- APPEARANCE_AUTO_CREATE_SCHEMA=true only for local tests. Production must apply migrations/0001_appearance_look_sessions.sql, migrations/0002_appearance_consent_events.sql and migrations/0003_appearance_deletion_outbox.sql, then verify backup/restore.

## Local checks

    python -m pip install -r requirements.txt
    APPEARANCE_DATABASE_URL=sqlite:///./appearance-test.db APPEARANCE_AUTO_CREATE_SCHEMA=true pytest -q

Contract tests do not prove image fidelity, photorealism, real consent-provider availability, production data isolation or successful asset deletion. Those require staging evidence and independent evaluation.
