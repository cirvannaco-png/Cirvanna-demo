# Age assurance provider decision — 23 November 2026

**Decision status:** technical provider candidate selected; commercial, privacy, legal and live-staging gates remain open. No production age proof is enabled by this decision.

## Decision

Select **Yoti Age Verification Service (AVS)** as Cirvanna's preferred age-assurance integration candidate, subject to provider onboarding, executed DPA, regional/legal review, security review, pricing and staging acceptance.

The initial integration profile should request a threshold result (OVER) rather than a full age value. Prefer the Yoti Digital ID method with the threshold configured by Cirvanna's active policy. Do not enable facial age estimation. Document scan should remain disabled unless its subprocessor retention and deletion terms are explicitly accepted in the executed DPA. If the user cannot complete the approved method, the evidence state remains UNKNOWN and age-dependent EEPL returns REVIEW.

Yoti's public developer documentation describes a server-side session API, threshold-based OVER/UNDER checks, a server-side result endpoint and signed notifications. It describes age verification as data-minimizing and says the relying party receives the threshold outcome rather than directly identifying information. This makes it a stronger initial candidate than trusting profile metadata or a client-supplied age. It does not establish that the required method is contractually available to Cirvanna in every target market. Yoti describes Digital ID as globally available, but its current supported-documents table lists a Kenyan passport and does not list a Kenyan national ID for Digital ID enrollment. That is a material conversion/accessibility limitation for Kenya: the Digital ID-only profile must not be presented as a complete Kenyan age-assurance solution until Yoti confirms accepted credentials and local onboarding in writing. Keep the fallback outcome UNKNOWN/REVIEW; do not silently enable age estimation or document scan to compensate.

## Evidence contract Cirvanna must enforce

A provider result is not accepted merely because the browser returns a session ID or a webhook arrives. The server must:

1. Create the AVS session using server-held API credentials and a random opaque reference ID that contains no subject identifier or personal data.
2. Persist a one-time mapping from the opaque reference/session ID to the verified Cirvanna subject, request ID, purpose, minimum-age threshold, policy ID/version, issuer, creation time and expiry.
3. Retrieve the authoritative result from Yoti's authenticated result API. A webhook is only a notification; verify its RSA-PSS/SHA-256 signature using the provider's published key, then retrieve the authoritative result server-to-server.
4. Require the expected SDK ID, session ID, opaque reference ID, OVER session type, exact threshold, COMPLETE state, supported method, not-expired session and exact policy binding.
5. Map FAIL to BLOCK only when the provider's documented terminal result is authenticated and bound to the same session/policy. Map PENDING, IN_PROGRESS, ERROR, CANCELLED, EXPIRED, unknown states, mismatch, provider outage or missing fields to UNKNOWN/REVIEW.
6. Emit a short-lived signed threshold attestation bound to subject, request, purpose, policy ID/version, threshold, provider issuer/session/evidence IDs, issued-at and expiry. Do not put raw age, DOB, ID data, selfie, face template or document image in the attestation.
7. Recheck attestation expiry and subject/session revocation at the point of each age-dependent decision. Never let Supabase Auth user metadata or self-declared profile fields populate this contract.

## Hard gates before production

- Provider onboarding confirms AVS account eligibility, Digital ID method availability in Kenya and each intended market, fallback method policy, service levels, pricing and rate limits.
- Executed DPA and subprocessor schedule; documented international transfer, retention, deletion, incident notification, no-training and audit rights.
- Security review of API credential storage, webhook signature verification, replay protection, TLS, request correlation and key rotation.
- Live staging tests for success, under-threshold, pending, cancellation, expiry, wrong session, wrong subject, wrong policy version, duplicate/replayed webhook, invalid signature, provider outage and key rotation.
- Independent privacy review of the chosen user flow and all collection/retention behavior.
- Production keys provisioned in secret manager only after these gates pass.

## References

- Yoti AVS methods and regional configuration: https://developers.yoti.com/age-verification/methods
- Yoti Digital ID supported documents by issuing country: https://developers.yoti.com/digital-id/supported-documents
- Session creation and API authentication: https://developers.yoti.com/age-verification/create-a-session
- Authoritative session results: https://developers.yoti.com/age-verification/results
- Signed notification verification: https://developers.yoti.com/age-verification/notifications
- Data privacy: https://developers.yoti.com/age-verification/data-privacy

## Rejected shortcuts

- Supabase Auth `user_metadata`, app profile date-of-birth, request-body `age_years`, email address or a self-declared checkbox are not age evidence.
- A browser redirect, client-supplied session ID, unsigned webhook or provider readiness probe is not a verified age result.
- Face analysis by Cirvanna, Click It, Look It, a Twin model or a style model must never be used to infer age.
- Provider integration code or a passing mock test does not mean provider onboarding, DPA or live evidence is complete.
