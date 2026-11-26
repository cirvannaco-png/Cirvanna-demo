# Cirvanna independent security, privacy and AI-safety assessment — RFP

**Status:** Draft for external procurement. No assessor has been appointed and no engagement has been commissioned.

## Objective

Obtain an independent, evidence-led assessment of the exact Cirvanna release candidate before any production promotion. The assessor must not be the implementation team, hosting provider, payment provider or model vendor. The report must identify tested commit, deployed image digests, environment, test dates, scope, exclusions, reproducible evidence, severity and retest status.

## Required workstreams

### 1. Application and infrastructure security
- External and authenticated web/API penetration testing, including BFF, API Gateway, Commerce, Catalog, Identity, Twin, Vision, Decision and Privacy Governance boundaries.
- Authentication, authorization, JWT issuer/audience/subject validation, session lifecycle, refresh/logout/revocation, tenant and resource isolation.
- CAL bypass testing across every product-display route; test direct Catalog access, BFF, recommendations, Look It, merchant surfaces and alternate serializers.
- SSRF, injection, IDOR/BOLA, mass assignment, race conditions, replay/idempotency, rate limiting, CORS/CSP, file upload, secret leakage and dependency/supply-chain review.
- Supabase RLS and schema grants; Neon database/service-role separation; Render private networking, service identity, secrets, egress and deployment controls.
- Stripe sandbox-only payment, webhook signature, duplicate delivery, failed/expired session, ambiguous outcome and reconciliation tests. No live Stripe transactions.

### 2. Privacy and data protection
- Independent review of the data inventory, purposes, lawful basis, retention, consent wording, data-subject rights, controller/processor roles, DPAs, subprocessors, transfer locations and deletion evidence.
- DPIA covering image uploads, wardrobe photos, face masking, recommendation profiling, Virtual Twin/body measurements, children and vulnerable users, cross-market processing and automated decisions.
- Consent grant/revocation tests bound to subject, resource, purpose, version and expiry. Verify that revoked or expired grants block reads, writes, model calls, exports and media delivery.
- Verify source, derivative, replica, cache, CDN, backup and restore deletion behavior. A delete request or API 200 is not proof of erasure.

### 3. Click It and Look It separation
- Verify Click It is unavailable on public ingress until the complete masking, consent, photographed-person rights, guardian and publication-attestation pipeline is independently cleared.
- Verify no face recognition, face embeddings for identity, identity search or age estimation is performed.
- Independently evaluate the pinned detector artifact and dataset digest. Report false-negative rates and confidence intervals by relevant image/lighting/skin-tone/face-size/occlusion subgroups; document sample size, label quality and limitations.
- Verify source-to-mask ordering, fail-closed behavior for uncertain/missing detector output, transient source handling and no unmasked original/derivative escaping any publish, restore, syndication, share, CDN, merchant or media-delivery path.
- Verify Look It remains a separate user-supplied outfit-reference flow with short-lived resource-bound consent, no durable source-image persistence, no identity search, no implicit public publication, and no product details before CAL SHOW.
- Exercise photographed-person report/removal, urgent quarantine, guardian-authority and jurisdiction-policy paths.

### 4. Virtual Twin and private assets
- Verify Identity Consent, Twin Registry, Asset Service and mesh-validator authorization on every create/read/preview/delete path.
- Verify exact subject, resource, consent version/expiry, source and mesh asset digests, ownership, private object ACLs and revocation.
- Assess full-body generation model licensing, model-weight provenance, output rights, validation pipeline, mesh quality and reproducibility. A pose skeleton or mock attestation is not a validated Twin.
- Verify deletion, orphan cleanup, restore and failure-injection behavior.

### 5. Resilience and operations
- Review monitoring, security alerts, provider outage behavior, structured logs and redaction.
- Witness a backup restore into an isolated clean environment; verify database, object and ledger invariants.
- Witness a rollback to a known-good immutable image/configuration set.
- Measure and report achieved RPO/RTO; test idempotent recovery, replay, reconnect and duplicate events.
- Review incident response, privacy incident notification, support/removal, refund and operational runbooks.

## Required deliverables
1. Rules of engagement and complete route/service/data inventory.
2. Threat model and risk-ranked findings with evidence and exploitability.
3. Penetration-test report, privacy/DPIA gap report and AI/vision masking evaluation report.
4. Evidence matrix tied to exact Git commit, deployed image digests, provider versions and environment.
5. Proof of no unmasked public image escape across all inventoried routes, or explicit failed test and quarantine recommendation.
6. Backup/restore and rollback witness reports with measured RPO/RTO.
7. Remediation plan, retest results and signed final opinion.
8. Clear list of exclusions, limitations, residual risks and release recommendation.

## Independence and assessor qualifications
- Disclose financial, implementation, hosting, model-vendor and prior advisory relationships with Cirvanna and its suppliers.
- Provide current CREST company accreditation for the specific penetration-testing service, or equivalent independently verifiable accreditation and named tester qualifications.
- Demonstrate experience in privacy/DPIA under Kenya's Data Protection Act and cross-border regimes relevant to Cirvanna's operating markets.
- Provide demonstrable capability in AI/vision evaluation and statistical reporting; general web penetration testing alone is insufficient.
- Provide professional indemnity cover, secure evidence handling, data-processing terms, subcontractor list and data-location/retention commitments.

## Rules of engagement and safety
- Use an isolated staging environment and synthetic or explicitly consented test data.
- No production user media, real personal data or live payment credentials.
- Stripe testing must remain in `livemode=false`.
- No destructive testing against production, third-party providers or unrelated PAMASMMA/Midas resources.
- All test credentials are scoped, time-limited, logged and revoked at engagement close.
- Findings containing secrets or personal data must be redacted and transmitted through an agreed secure channel.

## Commercial response requested
Bidders should quote each workstream separately and as a combined engagement, state fixed-fee assumptions, estimated calendar duration, team composition, onsite/remote delivery, retest pricing, report delivery date and earliest availability. No purchase order or engagement begins until the founder approves scope, price, assessor and contract.
