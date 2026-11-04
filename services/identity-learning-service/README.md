# USI and TAL service

Internal service for persistent User Style Index profiles and consented Temporal Learning Layer events.

## Ownership and database strategy

This service is the canonical API owner for explicit positive style preferences and consented temporal observations. It uses its own table namespace (`identity_usi_*` and `identity_tal_*`) in the existing managed PostgreSQL database. Point `IDENTITY_DATABASE_URL` at the existing approved database instance (for example the Commerce Postgres instance); do not create a second database merely for this service. No Commerce tables are read or modified by this service.

The API is internal-only. The API Gateway must first resolve the end-user bearer token through Commerce `GET /me`, then pass the verified subject ID using its machine credential. A caller-supplied subject ID is not proof of identity.

## Local setup

    python -m pip install -r requirements.txt
    IDENTITY_DATABASE_URL=sqlite:///./identity-test.db IDENTITY_SERVICE_TOKEN='local-random-token-at-least-32-bytes' IDENTITY_AUTO_CREATE_SCHEMA=true uvicorn app.main:app --host 127.0.0.1 --port 8092

Run tests:

    python -m pytest -q

## Configuration

- `IDENTITY_DATABASE_URL`: existing shared managed Postgres URL in staging/production; SQLite is local/test only.
- `IDENTITY_SERVICE_TOKEN` or `CONSENT_API_TOKEN`: internal bearer token, at least 32 bytes. Configure the same high-entropy secret as `CONSENT_API_TOKEN` in PNELLY, Marketplace BFF and Virtual Twin.
- `IDENTITY_CRON_TOKEN`: separate retention-job token, at least 32 bytes.
- `IDENTITY_AUTO_CREATE_SCHEMA`: local/test only. Must be false in production; apply reviewed SQL migration instead.

## Contracts

- Versioned USI profile upsert with optimistic concurrency (`expected_version`).
- Versioned TAL consent receipts remain available for profile/learning scopes. Image, Twin, asset and Try-On operations use immutable purpose-scoped bundles stored in `identity_consent_bundles`; internal record/verify/revoke operations bind a receipt to a subject, exact purposes and optional resource. A revoked bundle cannot be reused.
- Event writes require an active `personalization` or `style_learning` receipt; USI profile reads and writes require active `profile_storage` consent.
- TAL append supports event-ID and per-subject idempotency; changed replay payloads return 409.
- Corrections are append-only, must belong to the same subject and feature, and point to the superseded event.
- Export returns the subject's profile, consent receipts and event history.
- Deletion removes profile, consent and event records, retaining only a subject-hash deletion receipt.
- Retention purges events after their declared expiry.

All endpoints except `/health` require internal bearer authentication. Retention also requires a distinct cron header token.

## Production gates

Before deployment: provision the service on the selected existing Render workspace; configure its database URL to the already approved Postgres instance; apply `migrations/0001_identity_tal.sql` and `migrations/0002_consent_bundles.sql`; set independently rotated service and cron tokens; verify database backup/restore and deletion behavior; then enable gateway hydration. No production credentials or live identity-provider assertion are embedded here.


## Purpose-scoped image and Twin consent

The internal consent bundle API supports `image_processing`, `look_it`,
`click_it`, `dermalsight`, `virtual_try_on`, `body_measurements`,
`twin_storage`, `asset_storage`, `asset_reuse`, and
`marketplace_search` scopes.

- `POST /internal/v1/consents/record`: record immutable consent against a verified subject, purpose set, consent version and optional resource.
- `POST /internal/v1/consents/verify`: verify exact subject, requested purpose set and optional resource; returns active state and granted scopes.
- `POST /internal/v1/consents/revoke`: revoke the complete bundle; later verification fails and the same ID cannot be re-granted.

For PNELLY Look It, Marketplace BFF derives subject from the signed Commerce session,
records `image_processing` + `look_it` only after both explicit user actions,
executes the search, and revokes that one-request bundle after processing.
If the provider is unavailable, recording fails closed before the image is sent.
