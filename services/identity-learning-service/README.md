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
- Structured Style Desk colour preferences (`liked_colors`, `disliked_colors`, `best_version_colors`) with consent gating, optimistic versions, export and deletion. These are user-declared preferences, not inferred skin tone or objective colour analysis. The API reports objective analysis as unavailable until a validated model is deployed.
- Versioned consent receipts with a bundle ID, optional exact resource ID and optional expiry. Legacy receipts with null expiry remain compatible; a supplied expiry must be timezone-aware and in the future, and expired grants are excluded from profile/TAL operations and resource-bundle verification. Resource-bound revocation withdraws every active scope in that bundle for that resource only; it cannot revoke another Twin/resource. Internal `POST /internal/v1/consents/verify` checks the trusted subject, complete requested scope set, consent version, exact resource, revocation and expiry.
- Event writes require an active `personalization` or `style_learning` receipt; USI profile reads and writes require active `profile_storage` consent.
- TAL append supports event-ID and per-subject idempotency; changed replay payloads return 409.
- Corrections are append-only, must belong to the same subject and feature, and point to the superseded event.
- Export returns the subject's profile, consent receipts and event history.
- Deletion removes profile, consent and event records, retaining only a subject-hash deletion receipt.
- Retention purges events after their declared expiry.

All endpoints except `/health` require internal bearer authentication. Retention also requires a distinct cron header token.

## Production gates

Before deployment: provision the service on the approved Cirvanna workspace; configure its database URL to the approved PostgreSQL instance; apply `migrations/0001_identity_tal.sql`, `migrations/0002_color_profile.sql`, `migrations/0003_resource_bound_media_consent.sql` and `migrations/0004_consent_expiry.sql` in order; set independently rotated service and cron tokens; verify database backup/restore and deletion behavior; then enable gateway hydration. No production credentials or live identity-provider assertion are embedded here.


## Resource-bound consent expiry

Migration `0004_consent_expiry.sql` adds an expiry timestamp to the existing consent receipt authority. It deliberately does not create a second consent-bundle table. New grants may supply an ISO-8601 timezone-aware `expires_at`; verification and all active-consent checks reject expired records. Existing null-expiry records are retained for backward compatibility and must be migrated through the approved consent renewal process rather than silently treated as newly issued time-bounded consent.
