# Age evidence package

This package defines a minimized, purpose-bound threshold attestation and a server-side Yoti Age Verification Service client.

## Provider method

The Yoti adapter creates an OVER session with Digital ID enabled. It explicitly disables age estimation and document scan, so it does not fall back to face-based age estimation or document collection. If Digital ID is unavailable to a user or in a target market, the result is UNKNOWN/REVIEW; no weaker method is silently substituted.

## Integration requirements

The Identity Learning service persists an opaque session mapping in its private database before returning the hosted verification URL. The mapping binds the provider session/reference to the subject, request, purpose, exact server-resolved policy ID/version, threshold, creation time and expiry. A unique constraint prevents duplicate sessions for the same subject/request/purpose/policy version. The reference ID is random and contains no personal information.

After the browser returns, the server must retrieve the authoritative result using Yoti's authenticated result endpoint. Browser parameters and webhooks are not authority. If webhooks are enabled for asynchronous provider methods in a future approved profile, verify the published RSA-PSS/SHA-256 signature, replay/sequence constraints and then retrieve the server-side result. Never trust the webhook body alone.

Only a terminal, exact-session, exact-SDK, exact-reference, exact-threshold Digital ID result can become a threshold attestation. Pending, expired, cancelled, failed-to-verify, unknown method/state, mismatch, missing evidence ID or provider outage must not produce a PASS attestation.

The HMAC signing key is a dedicated service-to-service secret, not the Yoti API key. The attestation is bound to subject, request, purpose, policy ID/version and threshold; it contains no DOB, age in years, selfie, document, face embedding or raw provider response. The durable store persists the minimized attestation payload and signature so a lost polling response can be retried without creating a second provider result or JTI. Each attestation has a unique JTI and one-time atomic redemption. Redemption checks the exact subject/request/purpose/policy/version/threshold/signature binding, expiry, source-session state and revocation state in the database. Downstream Decision Service verifies the HMAC, bindings and expiry, then redeems the JTI through a separately authenticated private Identity endpoint before using the threshold result.

## Current status

**Durable lifecycle code and staging schema are present; provider integration is not yet live.** The repository now includes:
- durable session-to-subject/request/purpose/policy mapping and server-side create/poll/revoke endpoints;
- unique request/policy session constraint and provider-session uniqueness;
- separate internal orchestrator and attestation-redemption bearer credentials;
- one-time JTI storage with atomic replay prevention and session/attestation revocation checks;
- idempotent retrieval of the same minimized attestation after a lost polling response;
- a server-owned, version-pinned policy registry; the browser cannot supply an age threshold;
- PostgreSQL migration and integration-test coverage, plus SQLite service/API regression tests.

The additive lifecycle and retry-delivery migrations have been applied to the Cirvanna staging Supabase database. Both tables have RLS enabled, anon and authenticated have no SELECT privilege, and the Identity Learning service role has the required write privileges. This is schema/privilege evidence only; the service is not deployed and no real Yoti session has been created.

Still required:
- private Identity Learning runtime and secret-manager provisioning for database login, Yoti SDK/API credentials, HMAC key, policy registry and separate internal tokens;
- Yoti account onboarding, market/method availability confirmation, executed DPA and commercial approval;
- live staging evidence for success, under-threshold, pending, expiry, cancellation, mismatch, replay, revocation, outage and key rotation;
- independent security review and exact-head CI success.

Until those items pass, age-dependent decisions without valid server-issued evidence remain UNKNOWN/REVIEW. Supabase user metadata and self-declared age are not accepted.

## Decision Service integration

The Decision Service verifies the signed threshold attestation against the authenticated request subject, request ID, purpose and exact active policy. Client-supplied `age_years` remains untrusted and is ignored. Only minimum-age OVER evidence is currently supported; maximum-age policies remain unsupported by threshold-only evidence. Configure a separate `AGE_EVIDENCE_HMAC_SECRET` in the Decision Service secret manager. This integration is code-level verification only: durable session mapping, attestation revocation lookup, provider onboarding and live staging evidence remain open.
