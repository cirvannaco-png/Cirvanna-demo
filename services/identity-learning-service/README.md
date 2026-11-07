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
- `IDENTITY_SERVICE_TOKEN`: internal gateway bearer token, at least 32 bytes.
- `IDENTITY_CRON_TOKEN`: separate retention-job token, at least 32 bytes.
- `IDENTITY_AUTO_CREATE_SCHEMA`: local/test only. Must be false in production; apply reviewed SQL migration instead.

## Contracts

- Versioned USI profile upsert with optimistic concurrency (`expected_version`).
- Versioned consent receipts and consent bundles. Multiple scope receipts may share one consent ID; each receipt can be bound to an exact resource ID. Verification checks subject, bundle, every required scope, current revocation state and exact resource equality (including rejecting an omitted resource ID for a bound grant).
- `POST /internal/v1/consents/verify` is the server-side media-consent authority used by Virtual Twin and Click It. It requires the service bearer token and never trusts client consent booleans.
- Event writes require an active `personalization` or `style_learning` receipt; USI profile reads and writes require active `profile_storage` consent.
- TAL append supports event-ID and per-subject idempotency; changed replay payloads return 409.
- Corrections are append-only, must belong to the same subject and feature, and point to the superseded event.
- Export returns the subject's profile, consent receipts and event history.
- Deletion removes profile, consent and event records, retaining only a subject-hash deletion receipt.
- Retention purges events after their declared expiry.

All endpoints except `/health` require internal bearer authentication. Retention also requires a distinct cron header token.

## Production gates

Before deployment: provision the service on the selected existing Render workspace; configure its database URL to the already approved Postgres instance; apply `migrations/0001_identity_tal.sql` and `migrations/0002_resource_bound_media_consent.sql`; set independently rotated service and cron tokens; verify database backup/restore and deletion behavior; then enable gateway hydration. No production credentials or live identity-provider assertion are embedded here.
