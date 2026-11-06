# Cirvanna Privacy Governance Service

**Status: implementation scaffold with persistent case and consent APIs. Not production-enabled.**

This service owns three internal domains:
- purpose-bound Click It consent receipts and revocation;
- signed, versioned jurisdiction policy bundles and Click It policy evaluation;
- photographed-person image-rights intake, private status tracking, review decisions and deletion/quarantine acknowledgements.

It accepts no uploaded image, face crop, biometric template or identity document. It does not perform facial recognition, age estimation or identity resolution.

## Service contracts

### Consent
- `POST /internal/v1/consents/grant`: called by the authenticated Marketplace BFF after it resolves the subject through Commerce `/me` and confirms the user explicitly selected both Click It consent controls. When people are declared visible, the uploader must also explicitly attest to having permission to submit the photograph; this is recorded as a purpose-specific scope and is not represented as independent verification of every photographed person's consent.
- `POST /internal/v1/consents/verify`: verifies active scope, subject and optional resource binding for Virtual Twin.
- `POST /internal/v1/consents/{consent_id}/revoke`: revokes a subject-owned consent record.
- For a declared minor, guardian scope is added only when the external guardian-verification provider returns an active, purpose-matched authority receipt. Merely checking a box or typing a reference is not proof.

### Jurisdiction policy
- `POST /internal/v1/privacy/policies`: publishes an immutable policy bundle only when its Ed25519 signature verifies against the configured counsel-controlled public key.
- `POST /internal/v1/privacy/click-it/evaluate`: resolves all applicable jurisdictions through the trusted resolver and applies the strictest current signed policy bundle across them.
- Missing, stale, incomplete, conflicting, unlawful, or transfer-denied policy returns BLOCK. No jurisdiction, age threshold, legal basis, or retention rule is seeded in code.
- Policy bundles require legal-review metadata, an effective/expiry window, guardian-consent rules for declared minors, lawful-basis approval, transfer authorization, and explicit prohibitions on identity analysis, child behavioural profiling, image retention and public unmasked-face exposure.

### Public media publication gate

- `POST /internal/v1/privacy/assets/publication/evaluate` is a mandatory pre-publication contract for public profiles, community feeds, Marketplace media, merchant surfaces and shared links.
- The service requires a trusted Vision Privacy Attestation provider. The attestation must bind to the exact opaque asset ID and masking-attestation ID, prove all detected faces were masked before publication, report zero unmasked faces and confirm no facial recognition, face embeddings or age estimation ran.
- Missing, stale, mismatched, incomplete or unsafe masking evidence returns BLOCK. The service does not infer whether a face belongs to a child; it requires every detected face in a public asset to be masked. This is a conservative platform safeguard, not a legal classification.
- The Content Lifecycle/publication owner must call this gate before every public publish, restore, syndication or share-link activation path. A gate implementation that is not wired to all publication paths is not production protection.

### Image rights
- `POST /internal/v1/image-rights/requests`: accepts only an opaque Cirvanna asset reference. The service first validates the reference with the trusted Content Lifecycle provider. Urgent reasons require confirmed quarantine **and unpublishing** before a receipt is returned.
- `GET /internal/v1/image-rights/requests/{request_id}`: requester-only status, protected by an opaque one-time status token whose hash is stored.
- Each rights case records a configurable platform triage target (`PRIVACY_RIGHTS_TRIAGE_HOURS`, default 4 hours) and, only when every applicable jurisdiction resolves to a current signed bundle, a separate legal response deadline. The platform triage target is an operational service target, not a statutory deadline. An unresolved jurisdiction is explicitly labelled; it is never represented as a legal deadline.
- `GET /internal/v1/image-rights/queue`: internal reviewer queue.
- `POST /internal/v1/image-rights/requests/{request_id}/review`: requires a separate reviewer token. Approval requires verified requester authority and confirmation that source, derivatives, replicas, cache, CDN, merchant surfaces and shared links were all handled.
- The service records safe decision metadata only; it does not store the source image, status token, verification reference, or raw jurisdiction hint.

The status token is a bearer secret. The BFF exposes it only once on submission and requires it in a private header for subsequent status checks.

## External providers — mandatory before production

- `JURISDICTION_RESOLVER_API_URL/TOKEN`: resolves trusted subject/account, controller and processor establishments, capture context, processing/storage regions and all transfer destinations. The client's capture-country hint is never authoritative.
- `CONTENT_LIFECYCLE_API_URL/TOKEN`: resolves Cirvanna asset references and implements synchronous quarantine/unpublish, deletion propagation and unquarantine contracts. The service returns no urgent acknowledgement unless quarantine and unpublish are confirmed.
- `GUARDIAN_VERIFICATION_API_URL/TOKEN`: validates an opaque verification reference and returns a purpose-bound, active guardian-authority receipt. A missing provider means guardian-authorized consent cannot be issued.
- `PRIVACY_POLICY_BUNDLE_PUBLIC_KEY_PEM`: counsel-controlled Ed25519 public key. No default/private key or legal bundle is committed.
- `RIGHTS_AUTHORITY_VERIFICATION_API_URL/TOKEN`: independently verifies the photographed person's or representative's authority for a specific request before removal can be approved.
- Human privacy reviewer: independent authorization for approval, rejection and escalation. The reviewer cannot assert requester authority by setting a boolean; a provider receipt is mandatory.

Provider response schemas are enforced in the code. Test mocks do not constitute deployed-provider proof.

Every configured provider must also expose an authenticated `GET /ready` endpoint over the trusted HTTPS origin. The readiness request carries that provider's own bearer token, disables redirects and proxy-environment inheritance, and accepts only HTTP 200 with a JSON object containing `"ready": true`. A missing provider, bad URL/token, timeout, non-200 response, malformed body or `"ready": false` keeps Privacy Governance not-ready. The service probes all five providers concurrently; it does not expose provider URLs or tokens in its health response. A passing probe is still only an availability check—the operation-specific contracts below must be exercised against the real provider before production approval.


## Configuration

- `PRIVACY_GOVERNANCE_DATABASE_URL`: existing approved PostgreSQL database in staging/production; SQLite is local/test only.
- `PRIVACY_GOVERNANCE_ENVIRONMENT=production` in deployed environments.
- `PRIVACY_GOVERNANCE_AUTO_CREATE_SCHEMA=false` in production; apply `migrations/0001_privacy_governance.sql`.
- `PRIVACY_GOVERNANCE_INTERNAL_TOKEN`: service-to-service bearer token, at least 32 bytes.
- `PRIVACY_POLICY_PUBLISH_TOKEN`: separate policy publisher token, at least 32 bytes.
- `PRIVACY_RIGHTS_REVIEW_TOKEN`: separate reviewer token, at least 32 bytes.
- `PRIVACY_RIGHTS_TRIAGE_HOURS`: platform internal triage target between 1 and 24 hours; not a substitute for jurisdiction-specific statutory response deadlines.
- `PRIVACY_POLICY_BUNDLE_PUBLIC_KEY_PEM`: Ed25519 public key in PEM form.
- `VISION_PRIVACY_ATTESTATION_API_URL/TOKEN`: trusted Vision provider that verifies a signed masking attestation for the exact asset and public publication target.
- `RIGHTS_AUTHORITY_VERIFICATION_API_URL/TOKEN`: trusted provider that independently verifies a photographed person's, parent/guardian's or authorized representative's authority for the specific image-rights case.
- Provider URL/token pairs listed above.

Never store production credentials in GitHub files, browser JavaScript, or this README. Use the approved secret manager and rotate independent service/reviewer/publisher tokens.

## Local test

```sh
cd services/privacy-governance-service
python -m pip install -r requirements.txt
PRIVACY_GOVERNANCE_DATABASE_URL=sqlite:///./privacy-governance-test.db \
PRIVACY_GOVERNANCE_AUTO_CREATE_SCHEMA=true \
PRIVACY_GOVERNANCE_INTERNAL_TOKEN=local-test-internal-token-at-least-32-bytes \
PRIVACY_POLICY_PUBLISH_TOKEN=local-test-policy-publisher-token-32-bytes \
PRIVACY_RIGHTS_REVIEW_TOKEN=local-test-reviewer-token-at-least-32-bytes \
python -m pytest -q
```

## Release boundary

Passing tests prove adapter behavior, not global legal compliance. Production remains blocked until every provider is deployed, legally reviewed, independently tested, rate-limited at the edge, monitored, backup/restore tested and connected to the real asset/CDN/merchant surface inventory. The privacy queue must be staffed with a defined escalation path and jurisdiction-specific deadlines before public enablement.
