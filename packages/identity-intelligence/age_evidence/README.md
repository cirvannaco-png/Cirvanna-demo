# Age evidence package

This package defines a minimized, purpose-bound threshold attestation and a server-side Yoti Age Verification Service client.

## Provider method

The Yoti adapter creates an OVER session with Digital ID enabled. It explicitly disables age estimation and document scan, so it does not fall back to face-based age estimation or document collection. If Digital ID is unavailable to a user or in a target market, the result is UNKNOWN/REVIEW; no weaker method is silently substituted.

## Integration requirements

The caller must persist a one-time opaque session mapping in a durable database before returning the hosted verification URL. The mapping must bind the provider session/reference to the verified Cirvanna subject, request, purpose, exact policy ID/version, threshold, creation time and expiry. The reference ID must be random and contain no personal information.

After the browser returns, the server must retrieve the authoritative result using Yoti's authenticated result endpoint. Browser parameters and webhooks are not authority. If webhooks are enabled for asynchronous provider methods in a future approved profile, verify the published RSA-PSS/SHA-256 signature, replay/sequence constraints and then retrieve the server-side result. Never trust the webhook body alone.

Only a terminal, exact-session, exact-SDK, exact-reference, exact-threshold Digital ID result can become a threshold attestation. Pending, expired, cancelled, failed-to-verify, unknown method/state, mismatch, missing evidence ID or provider outage must not produce a PASS attestation.

The HMAC signing key is a dedicated service-to-service secret, not the Yoti API key. The attestation is bound to subject, request, purpose, policy ID/version and threshold; it contains no DOB, age in years, selfie, document, face embedding or raw provider response. Downstream decision services must verify the signature, binding and expiry on every use.

## Current status

**Adapter and contract foundation only. Not yet deployed or enabled.** The repository still needs:
- durable session-to-subject/request/policy mapping and one-time session lifecycle endpoints;
- internal API authentication and replay protection;
- decision-service and API Gateway integration with EEPL threshold semantics;
- secret-manager provisioning for Yoti SDK/API credentials and the separate HMAC key;
- Yoti account onboarding, market/method availability confirmation, executed DPA and commercial approval;
- staging evidence for success, under-threshold, pending, expiry, cancellation, mismatch, replay, outage and key rotation;
- independent privacy/security review.

Until those items pass, all age-dependent decisions remain UNKNOWN/REVIEW. Supabase user metadata and self-declared age are not accepted.


## Decision Service integration

The Decision Service verifies the signed threshold attestation against the authenticated request subject, request ID, purpose and exact active policy. Client-supplied `age_years` remains untrusted and is ignored. Only minimum-age OVER evidence is currently supported; maximum-age policies remain unsupported by threshold-only evidence. Configure a separate `AGE_EVIDENCE_HMAC_SECRET` in the Decision Service secret manager. This integration is code-level verification only: durable session mapping, attestation revocation lookup, provider onboarding and live staging evidence remain open.
