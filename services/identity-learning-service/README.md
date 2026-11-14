# USI and TAL service

Internal service for persistent User Style Index profiles and consented Temporal Learning Layer events.

## Ownership and database strategy

This service is the canonical API owner for explicit positive style preferences and consented temporal observations. It uses its own table namespace (`identity_usi_*` and `identity_tal_*`) in the existing managed PostgreSQL database. Point `IDENTITY_DATABASE_URL` at the existing approved database instance (for example the Commerce Postgres instance); do not create a second database merely for this service. No Commerce tables are read or modified by this service.

The API is internal-only. The API Gateway must first resolve the end-user bearer token through Commerce `GET /me`, then pass the verified subject ID using its machine credential. A caller-supplied subject ID is not proof of identity.


## PNELLY conversation continuity

The service owns a short-lived, subject-scoped store for normalized PNELLY discovery context. It accepts only an explicit `pnelly_conversation` consent receipt bound to the exact conversation UUID and an expiry no later than 24 hours. Each turn uses optimistic state-version checks and an idempotent turn ID. Revocation, explicit conversation deletion, user data deletion, expiry and the retention job remove the stored context.

Only structured discovery fields are retained (latest query, category, currency, declared location/occasion/climate, bounded constraints and owned-item exclusion choice). **Raw conversation messages and transcripts are not stored.** This table is not a language model, intent parser or conversation generator; the conversational orchestration/provider still has to interpret follow-up language and map it into this typed state before using CAL-protected discovery.

Apply `migrations/0005_pnelly_conversation_context.sql` after `0004_consent_expiry.sql`, then `0006_consent_revocation_outbox.sql`. The identity workflow tests the migration chain and isolated PostgreSQL restore.

## Local setup

    python -m pip install -r requirements.txt
    IDENTITY_DATABASE_URL=sqlite:///./identity-test.db IDENTITY_SERVICE_TOKEN='local-random-token-at-least-32-bytes' IDENTITY_AUTO_CREATE_SCHEMA=true uvicorn app.main:app --host 127.0.0.1 --port 8092

Run tests:

    python -m pytest -q

## Configuration

- `IDENTITY_DATABASE_URL`: existing shared managed Postgres URL in staging/production; SQLite is local/test only.
- `IDENTITY_SERVICE_TOKEN`: internal gateway bearer token, at least 32 bytes.
- `IDENTITY_CRON_TOKEN`: separate retention-job token, at least 32 bytes.
- `TWIN_REGISTRY_API_URL` / `TWIN_REGISTRY_API_TOKEN`: trusted private Twin Registry URL and separate internal bearer used for consent-revocation cleanup. Keep the token out of browsers and mobile binaries.
- `IDENTITY_AUTO_CREATE_SCHEMA`: local/test only. Must be false in production; apply reviewed SQL migration instead.

## Contracts

- Versioned USI profile upsert with optimistic concurrency (`expected_version`).
- Structured Style Desk colour preferences (`liked_colors`, `disliked_colors`, `best_version_colors`) with consent gating, optimistic versions, export and deletion. These are user-declared preferences, not inferred skin tone or objective colour analysis. The API reports objective analysis as unavailable until a validated model is deployed.
- Versioned consent receipts with a bundle ID, optional exact resource ID and optional expiry. DSI adds separate opt-in scopes for facial geometry analysis, body-tone analysis, appearance correction and global model training. These are never implied by image processing, skin analysis, body measurements, enrollment or one another. DSI consumers must verify the exact user subject, consent bundle, scope set, version, resource and expiry at request time. Legacy receipts with null expiry remain compatible; a supplied expiry must be timezone-aware and in the future, and expired grants are excluded from profile/TAL operations and resource-bundle verification. Resource-bound revocation withdraws every active scope in that bundle for that resource only; it cannot revoke another Twin/resource. Internal `POST /internal/v1/consents/verify` checks the trusted subject, complete requested scope set, consent version, exact resource, revocation and expiry.
- Resource-bound Twin consent withdrawal writes an idempotent cleanup command into `identity_consent_revocation_outbox` in the same database transaction. The service immediately attempts the dedicated Twin Registry endpoint; failed/missing-provider attempts remain pending with an error code and are retried by the scheduled `/internal/retention/purge` worker or through `POST /internal/v1/consent-revocations/dispatch`. Every retention run retries all older pending cleanup commands, not only newly expired receipts. `twin_cleanup_status=delivered` means the Twin Registry accepted the resource-scoped deletion command; it does **not** claim the physical Asset Service deletion has finished. The Twin Registry retains its own deletion outbox until Asset Service confirms the exact asset set. Twin authorization is denied as soon as consent is revoked, regardless of cleanup dispatch state.
- Event writes require an active `personalization` or `style_learning` receipt; USI profile reads and writes require active `profile_storage` consent.
- TAL append supports event-ID and per-subject idempotency; changed replay payloads return 409.
- Corrections are append-only, must belong to the same subject and feature, and point to the superseded event.
- Export returns the subject's profile, consent receipts and event history.
- Deletion removes profile, consent and event records, retaining only a subject-hash deletion receipt.
- Retention purges events after their declared expiry and retries pending resource-bound Twin deletion notifications on every scheduled run. The scheduler must call `/internal/retention/purge` with both the internal service credential and the separate `IDENTITY_CRON_TOKEN`.

All endpoints except `/health` require internal bearer authentication. Retention also requires a distinct cron header token.

## Production gates

Before deployment: provision the service on the approved Cirvanna workspace; configure its database URL to the approved PostgreSQL instance; apply migrations `0001` through `0006` in numeric order, including the PNELLY conversation-context and consent-revocation outbox migrations; set independently rotated service and cron tokens; verify database backup/restore and deletion behavior; then enable gateway hydration. No production credentials or live identity-provider assertion are embedded here.


## Resource-bound consent expiry

Migration `0004_consent_expiry.sql` adds an expiry timestamp to the existing consent receipt authority. It deliberately does not create a second consent-bundle table. New grants may supply an ISO-8601 timezone-aware `expires_at`; verification and all active-consent checks reject expired records. Existing null-expiry records are retained for backward compatibility and must be migrated through the approved consent renewal process rather than silently treated as newly issued time-bounded consent.
