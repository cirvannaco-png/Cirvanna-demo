# USI and TAL service

Internal service for persistent User Style Index profiles and consented Temporal Learning Layer events.

## Ownership and database strategy

This service is the canonical API owner for explicit positive style preferences and consented temporal observations. It uses its own table namespace (`identity_usi_*` and `identity_tal_*`) in the existing managed PostgreSQL database. Point `IDENTITY_DATABASE_URL` at the existing approved database instance (for example the Commerce Postgres instance); do not create a second database merely for this service. No Commerce tables are read or modified by this service.

The namespace is physically isolated in the non-exposed `identity_private` schema. PostgreSQL connections are pinned to `search_path=identity_private` by the service engine; migrations create/use that schema explicitly. Do not add `identity_private` to Supabase API Exposed Schemas. The current application connection still requires a database login with the documented schema privileges; a dedicated least-privilege login/credential must be provisioned before deployment and must not be replaced by the broad project `postgres` credential.

The API is internal-only. The API Gateway must first resolve the end-user bearer token through Commerce `GET /me`, then pass the verified subject ID using its machine credential. A caller-supplied subject ID is not proof of identity.


## PNELLY conversation continuity

The service owns a short-lived, subject-scoped store for normalized PNELLY discovery context. It accepts only an explicit `pnelly_conversation` consent receipt bound to the exact conversation UUID and an expiry no later than 24 hours. Each turn uses optimistic state-version checks and an idempotent turn ID. Revocation, explicit conversation deletion, user data deletion, expiry and the retention job remove the stored context.

Only structured discovery fields are retained (latest query, category, currency, declared location/occasion/climate, bounded constraints and owned-item exclusion choice). **Raw conversation messages and transcripts are not stored.** This table is not a language model, intent parser or conversation generator; the conversational orchestration/provider still has to interpret follow-up language and map it into this typed state before using CAL-protected discovery.

Apply `migrations/0005_pnelly_conversation_context.sql` after `0004_consent_expiry.sql`, then `0006_consent_revocation_outbox.sql`, `0007_dsi_capture_challenges.sql`, and `0008_cil_provider_consent_revocation.sql`. Apply `0009_foreign_key_indexes.sql` last. Apply `0010_runtime_role_grants.sql` after that; create a separate LOGIN role with a managed password at deployment and grant it membership in `identity_learning_service`. Apply `0011_supabase_auth_app_role_hook.sql` to install the private Custom Access Token Hook. Enable it explicitly in Supabase Authentication → Hooks and set Commerce `COMMERCE_JWT_ROLE_CLAIM=app_role`. The hook copies only server-controlled `app_metadata.app_role` (default `customer`) into the top-level claim; Supabase's reserved `role=authenticated` remains unchanged. Merchant/admin promotion must come only from a verified server-side role-assignment workflow. The identity workflow tests the migration chain and isolated PostgreSQL restore.

## Local setup

    python -m pip install -r requirements.txt
    IDENTITY_DATABASE_URL=sqlite:///./identity-test.db IDENTITY_SERVICE_TOKEN='local-random-token-at-least-32-bytes' IDENTITY_AUTO_CREATE_SCHEMA=true uvicorn app.main:app --host 127.0.0.1 --port 8092

Run tests:

    python -m pytest -q

## Configuration

- `IDENTITY_DATABASE_URL`: existing shared managed Postgres URL in staging/production; SQLite is local/test only.
- `IDENTITY_SERVICE_TOKEN`: internal gateway bearer token, at least 32 bytes.
- `IDENTITY_CRON_TOKEN`: separate retention-job token, at least 32 bytes.
- `IDENTITY_CIL_CONSENT_ISSUER_TOKEN`: separate 32+ byte credential held only by the trusted age/eligibility assertion service that has verified the adult claim. It is the only credential accepted by the skin-analysis provider receipt issuer; the ordinary Identity service token cannot mint adult-scoped receipts.
- `IDENTITY_CIL_CONSENT_VERIFIER_TOKEN`: separate 32+ byte credential held only by the private CIL service. It authorizes live per-task checks against the canonical skin-analysis consent record; it cannot issue age assertions or create new consent.
- `IDENTITY_DSI_CAPTURE_SERVICE_TOKEN`: separately rotated machine credential, at least 32 bytes, held only by the trusted DSI Vision verifier for the internal challenge and receipt APIs. Do not give this credential to browsers or Android clients; do not reuse `IDENTITY_SERVICE_TOKEN`.
- `TWIN_REGISTRY_API_URL` / `TWIN_REGISTRY_API_TOKEN`: trusted private Twin Registry URL and separate internal bearer used for consent-revocation cleanup. Keep the token out of browsers and mobile binaries.
- `CIL_CONTRIBUTOR_TOKEN_HMAC_SECRET`: separate 32+ byte key held by Identity Learning only. It derives a stable `hmac-sha256:<64 hex>` contributor pseudonym from the verified subject. Do not share this key with a browser or external provider.
- `CIL_SKIN_ANALYSIS_CONSENT_KEY`: at least 32 bytes and shared only between Identity Learning (canonical issuer) and the internal CIL verifier. It signs short-lived provider consent receipts.
- `CIL_SERVICE_URL` / `CIL_SERVICE_TOKEN`: trusted private CIL URL and its dedicated internal bearer for provider-revocation callbacks. This is distinct from `IDENTITY_SERVICE_TOKEN`.
- `CIL_SKIN_ANALYSIS_RECEIPT_TTL_SECONDS`: short-lived signed receipt window, 60–900 seconds (default 600).
- `IDENTITY_AUTO_CREATE_SCHEMA`: local/test only. Must be false in production; apply reviewed SQL migration instead.

## Contracts

- Versioned USI profile upsert with optimistic concurrency (`expected_version`).
- Structured Style Desk colour preferences (`liked_colors`, `disliked_colors`, `best_version_colors`) with consent gating, optimistic versions, export and deletion. These are user-declared preferences, not inferred skin tone or objective colour analysis. The API reports objective analysis as unavailable until a validated model is deployed.
- Versioned consent receipts with a bundle ID, optional exact resource ID and optional expiry. DSI uses separate opt-in scopes for facial geometry analysis, body-tone analysis, appearance correction and global model training. Appearance look sessions use `appearance_session_storage` for retaining look metadata and `appearance_source_storage` for retaining a user-uploaded source photo in Asset Service. Source-photo sessions also require `image_processing`. These permissions are distinct from DSI analysis, Twin storage, style learning and global model training. Consumers verify the exact subject, consent bundle, scope set, consent version, resource and expiry at request time. Legacy receipts with null expiry remain compatible; supplied expiries must be timezone-aware and in the future. Resource-bound revocation withdraws every active scope in that exact bundle/resource and cannot revoke another resource. Internal `POST /internal/v1/consents/verify` checks subject, requested scopes, consent version, exact resource, revocation and expiry.
- DSI capture challenge state is stored in the existing Identity Learning database namespace, not a second consent store or separate database. `POST /internal/v1/dsi/capture-challenges` checks the exact active, expiring purpose/resource-bound consent bundle and creates a server-generated 256-bit nonce. Only its SHA-256 digest, opaque challenge ID, consent receipt IDs and a maximum three-minute expiry are persisted; raw nonce bytes are returned once to the authenticated Vision service and are never stored.
- The dedicated DSI service credential protects challenge creation, one-time consumption and receipt verification; it is separate from the general internal token. Vision may consume a challenge only after its Android key-attestation and Play Integrity verifier has independently succeeded. The Identity endpoint is a persistence/consent boundary, not a Google certificate or Play Integrity verifier.
- The resulting verification receipt binds subject, original consent receipt IDs, resource, purpose, canonical-manifest/image/device-pipeline digests, app certificate/version, verifier policy and the summarized attestation/integrity verdicts. The CIL-only live consent verifier checks the exact receipt ID, consent bundle, resource and HMAC pseudonym immediately before provider task creation and before each result poll; it returns the canonical grant expiry, not the short signed-receipt TTL. Receipts expire no later than the challenge and consent, and every use re-checks the exact original consent receipts. Revocation denies future receipt verification; user deletion removes challenge and receipt records; retention deletes expired state.
- Resource-bound Twin consent withdrawal writes an idempotent cleanup command into `identity_consent_revocation_outbox` in the same database transaction. The service immediately attempts the dedicated Twin Registry endpoint; failed/missing-provider attempts remain pending and are retried by `/internal/retention/purge` or `POST /internal/v1/consent-revocations/dispatch`. `twin_cleanup_status=delivered` means Twin Registry accepted the deletion command; it does **not** claim Asset Service deletion has finished.
- Skin-analysis consent is resource-bound, expiring and assigned a stable keyed contributor pseudonym by Identity Learning. The raw canonical subject ID is never sent to CIL or the external analysis provider. A trusted internal caller obtains a short-lived image-digest-bound CIL receipt from `POST /internal/v1/consents/skin-analysis-provider-receipts`, supplying age from a verified identity/eligibility result; the service signs it with the shared CIL skin-analysis consent key. The returned receipt contains the pseudonym, exact consent bundle, image digest, single-subject assertion, adult age and short expiry, but no canonical subject ID.
- Skin-analysis consent withdrawal, denial, exact-resource bundle revocation, user deletion and expiry add an idempotent command to `identity_cil_provider_consent_revocation_outbox` in the same transaction as the consent change. Identity Learning calls CIL `POST /providers/perfectcorp/revoke-consent`; failures remain pending and retry through `/internal/retention/purge` or `POST /internal/v1/cil/provider-consent-revocations/dispatch`. The callback carries the exact consent ID and stored pseudonym. For legacy records without a stored mapping, CIL permits fallback only when the consent ID maps to exactly one contributor; ambiguous mappings are rejected before any task is changed.
- `cil_provider_cleanup_status=delivered` means CIL accepted the canonical revocation and initiated provider-task cleanup. It does **not** prove the vendor has physically deleted every file: tasks still running are withheld from result release and remain in CIL's retry/reaper process until terminal deletion. Provider credentials, DPA/retention approval and actual staging cleanup evidence remain separate release requirements.
- Event writes require an active `personalization` or `style_learning` receipt; USI profile reads and writes require active `profile_storage` consent.
- TAL append supports event-ID and per-subject idempotency; changed replay payloads return 409.
- Corrections are append-only, must belong to the same subject and feature, and point to the superseded event.
- Export returns the subject's profile, consent receipts and event history.
- Deletion removes profile, consent and event records, retaining only a subject-hash deletion receipt.
- Retention purges events after their declared expiry and retries pending resource-bound Twin deletion notifications on every scheduled run. The scheduler must call `/internal/retention/purge` with both the internal service credential and the separate `IDENTITY_CRON_TOKEN`.

All endpoints except `/health` require internal bearer authentication. Retention also requires a distinct cron header token.

## Production gates

Before deployment: provision the service on the approved Cirvanna workspace; configure its database URL to the approved PostgreSQL instance; apply migrations `0001` through `0008` in numeric order, including PNELLY context, Twin cleanup, DSI capture and CIL provider-consent revocation; set independently rotated service, DSI capture and cron tokens; verify database backup/restore and deletion behavior; then enable gateway hydration. No production credentials or live identity-provider assertion are embedded here.


## Resource-bound consent expiry

Migration `0004_consent_expiry.sql` adds an expiry timestamp to the existing consent receipt authority. It deliberately does not create a second consent-bundle table. New grants may supply an ISO-8601 timezone-aware `expires_at`; verification and all active-consent checks reject expired records. Existing null-expiry records are retained for backward compatibility and must be migrated through the approved consent renewal process rather than silently treated as newly issued time-bounded consent.
