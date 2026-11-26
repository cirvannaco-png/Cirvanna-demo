# Independent security and privacy assessment scope

**Status:** prepared for external commissioning; no assessor has been engaged and no independent report exists.

## Independence and assessor selection

The assessor must be independent of Cirvanna's implementation team and hosting/provider vendors, disclose conflicts, sign an NDA and data-processing terms, and provide named lead assessors, methodology, professional liability cover, secure evidence handling, and a fixed scope/price. The firm must be allowed to report critical findings directly to the founder and must not be paid contingent on a clean report.

Shortlist for an RFP (verify current accreditation, scope and availability directly before appointment):
- [Technovar](https://www.techinnovar.com/) — listed by CREST's Kenya provider directory for penetration testing.
- [RedLion](https://redlion.co.ke/) — listed by CREST's Kenya provider directory for penetration testing.
- [Secmentis](https://www.secmentis.com/kenya/) — listed by CREST's Kenya provider directory for penetration testing.
- [Cyber Security Africa](http://www.cybersecurityafrica.com/) — listed by CREST's Kenya provider directory for penetration testing.

A penetration test alone is insufficient. The CREST [Kenya provider directory](https://cmage.crest-approved.org/countries/kenya/reports/penetration_testing_providers.html) is the starting point for verifying current penetration-testing provider status; accreditation and service scope must be reconfirmed at procurement. The engagement must separately include an independent privacy/DPIA review by qualified privacy professionals familiar with Kenya's Data Protection Act and relevant target-market law. No privacy assessor has been selected. A firm may subcontract this work only with disclosure and approval. Do not treat penetration-testing accreditation as proof of privacy-assessment competence.

## Required assessment scope

1. **External attack surface:** internet-facing APIs, BFF, admin/merchant portals, CORS/CSP, TLS, rate limits, API discovery, authn/authz, SSRF, injection, deserialization, file upload, secrets, dependency/supply-chain and container configuration.
2. **Identity and session security:** OIDC issuer/audience/JWKS, role claims, session binding, refresh, logout, expiry, key rotation, replay, account recovery, cross-tenant access and browser token handling.
3. **Service and database isolation:** per-service credentials, secret-manager delivery/rotation, network boundaries, PostgreSQL grants, RLS policies, owner/bypass-role paths, backup access, migration roles and negative access tests.
4. **CAL and Commerce:** every display/cart/checkout surface, fail-closed behavior, signed subject/action/candidate/offer-snapshot receipts, replay and expiry, webhook idempotency, payment/ledger reconciliation and audit immutability.
5. **Click It and Look It:** route inventory from original upload through masking, processing, derivative creation, publish, restore, CDN/cache, share link, merchant display, deletion and backup lifecycle. Verify Click It remains disabled unless consent, rights and masking attestations pass; verify Look It's separate short-lived consent and revocation lifecycle.
6. **Face masking and children:** detector/model and dataset hashes, source-to-mask ordering, uncertainty fail-closed, subgroup false-negative confidence intervals, no face recognition or identity search, guardian controls where required, photographed-person reporting/quarantine and deletion propagation.
7. **Privacy/DPIA:** data inventory, purposes, lawful bases, data minimisation, consent granularity/revocation, retention, processor/subprocessor map, cross-border transfers, data subject rights, breach response, children's data and high-risk profiling.
8. **Virtual Twin and appearance data:** consent scope, subject binding, asset access, model/mesh provenance, persistence, revocation, deletion, backup restoration and cross-user isolation.
9. **Operational resilience:** telemetry redaction, alert routes, incident response, encrypted backup restore, rollback, measured RPO/RTO and reconciliation after recovery.

## Required deliverables and release evidence

- Signed rules of engagement and asset/endpoint inventory.
- Threat model and privacy/DPIA findings with data-flow diagrams.
- Reproducible technical findings with severity, evidence, affected exact commit/image digests and remediation guidance.
- Specific Click It source-to-mask and publish-route test evidence, including independent verification of zero unmasked-face escape on the exact deployed route inventory.
- Database privilege/RLS and cross-tenant isolation test results.
- Restore and rollback observation records with measured RPO/RTO.
- Remediation retest report and residual-risk register.
- Signed final report, report SHA-256, assessor identity/qualifications, test dates, scope exclusions and approval signatures.

## Commissioning gates

Do not commission live testing until a dedicated staging environment exists, data is synthetic or explicitly approved, test accounts and emergency contacts are ready, and the assessor has a signed scope. Do not grant production secrets or unrestricted production data. No release gate may be marked passed based only on this scope document or a vendor marketing claim.
