# Cirvanna Privacy Governance Service

**Status: implementation scaffold with persistent case and consent APIs. Not production-enabled.**

This service owns three internal domains:
- purpose-bound Click It consent receipts and revocation;
- signed, versioned jurisdiction policy bundles and Click It policy evaluation;
- photographed-person image-rights intake, private status tracking, review decisions and deletion/quarantine acknowledgements.

It accepts no uploaded image, face crop, biometric template or identity document. It does not perform facial recognition, age estimation or identity resolution.

## Service contracts

### Consent
- `POST /internal/v1/consents/grant`: called by the authenticated Marketplace BFF after it resolves the subject through Commerce `/me` and confirms the user explicitly selected both Click It consent controls.
- `POST /internal/v1/consents/verify`: verifies active scope, subject and optional resource binding for Virtual Twin.
- `POST /internal/v1/consents/{consent_id}/revoke`: revokes a subject-owned consent record.
- For a declared minor, guardian scope is added only when the external guardian-verification provider returns an active, purpose-matched authority receipt. Merely checking a box or typing a reference is not proof.

### Jurisdiction policy
- `POST /internal/v1/privacy/policies`: publishes an immutable policy bundle only when its Ed25519 signature verifies against the configured counsel-controlled public key.
- `POST /internal/v1/privacy/click-it/evaluate`: resolves all applicable jurisdictions through the trusted resolver and applies the strictest current signed policy bundle across them.
- Missing, stale, incomplete, conflicting, unlawful, or transfer-denied policy returns BLOCK. No jurisdiction, age threshold, legal basis, or retention rule is seeded in code.
- Policy bundles require legal-review metadata, an effective/expiry window, guardian-consent rules for declared minors, lawful-basis approval, transfer authorization, and explicit prohibitions on identity analysis, child behavioural profiling, image retention and public unmasked-face exposure.

### Image rights
- `POST /internal/v1/image-rights/requests`: accepts only an opaque Cirvanna asset reference. The service first validates the reference with the trusted Content Lifecycle provider. Urgent reasons require confirmed quarantine **and unpublishing** before a receipt is returned.
- `GET /internal/v1/image-rights/requests/{request_id}`: requester-only status, protected by an opaque one-time status token whose hash is stored.
- `GET /internal/v1/image-rights/queue`: internal reviewer queue.
- `POST /internal/v1/image-rights/requests/{request_id}/review`: requires a separate reviewer token. Approval requires verified requester authority and confirmation that source, derivatives, replicas, cache, CDN, merchant surfaces and shared links were all handled.
- The service records safe decision metadata only; it does not store the source image, status token, verification reference, or raw jurisdiction hint.

The status token is a bearer secret. The BFF exposes it only once on submission and requires it in a private header for subsequent status checks.

## External providers — mandatory before production

- `JURISDICTION_RESOLVER_API_URL/TOKEN`: resolves trusted subject/account, controller and processor establishments, capture context, processing/storage regions and all transfer destinations. The client's capture-country hint is never authoritative.
- `CONTENT_LIFECYCLE_API_URL/TOKEN`: resolves Cirvanna asset references and implements synchronous quarantine/unpublish, deletion propagation and unquarantine contracts. The service returns no urgent acknowledgement unless quarantine and unpublish are confirmed.
- `GUARDIAN_VERIFICATION_API_URL/TOKEN`: validates an opaque verification reference and returns a purpose-bound, active guardian-authority receipt. A missing provider means guardian-authorized consent cannot be issued.
- `PRIVACY_POLICY_BUNDLE_PUBLIC_KEY_PEM`: counsel-controlled Ed25519 public key. No default/private key or legal bundle is committed.
- Human privacy reviewer: independent authorization for requester verification, approval, rejection and escalation.

Provider response schemas are enforced in the code. Test mocks do not constitute deployed-provider proof.

## Configuration

- `PRIVACY_GOVERNANCE_DATABASE_URL`: existing approved PostgreSQL database in staging/production; SQLite is local/test only.
- `PRIVACY_GOVERNANCE_ENVIRONMENT=production` in deployed environments.
- `PRIVACY_GOVERNANCE_AUTO_CREATE_SCHEMA=false` in production; apply `migrations/0001_privacy_governance.sql`.
- `PRIVACY_GOVERNANCE_INTERNAL_TOKEN`: service-to-service bearer token, at least 32 bytes.
- `PRIVACY_POLICY_PUBLISH_TOKEN`: separate policy publisher token, at least 32 bytes.
- `PRIVACY_RIGHTS_REVIEW_TOKEN`: separate reviewer token, at least 32 bytes.
- `PRIVACY_POLICY_BUNDLE_PUBLIC_KEY_PEM`: Ed25519 public key in PEM form.
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
