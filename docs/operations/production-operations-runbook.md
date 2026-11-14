# Production operations and incident runbook

**Status:** operational template; production ownership and deployment are not yet attested.  
**Rule:** do not mark REL-10 or REL-16 passed until all placeholders are replaced with real values and drills are evidenced.

## 1. Ownership record — mandatory before deployment

| Role | Named primary | Named backup | Contact / escalation |
|---|---|---|---|
| Incident commander | **UNASSIGNED** | **UNASSIGNED** | **REQUIRED** |
| Platform/SRE owner | **UNASSIGNED** | **UNASSIGNED** | **REQUIRED** |
| Database/recovery owner | **UNASSIGNED** | **UNASSIGNED** | **REQUIRED** |
| Identity/security owner | **UNASSIGNED** | **UNASSIGNED** | **REQUIRED** |
| Privacy/rights owner | **UNASSIGNED** | **UNASSIGNED** | **REQUIRED** |
| Marketplace/merchant operations | **UNASSIGNED** | **UNASSIGNED** | **REQUIRED** |
| Commerce/payments owner | **UNASSIGNED** | **UNASSIGNED** | **REQUIRED** |
| Customer support/refunds | **UNASSIGNED** | **UNASSIGNED** | **REQUIRED** |

Do not invent names, contact details, pager routes, service IDs, regions or recovery objectives. Record approved values in the deployment inventory/secret manager and access-controlled operations system, not in public documentation.

## 2. Monitoring baseline

Centralize structured logs, metrics and traces with correlation IDs. Redact authorization headers, cookies, personal data, image bytes, payment data, provider secrets and raw webhook payloads. Restrict access and retention by purpose.

### Service health and reliability

Monitor per service and dependency:

- request rate, p50/p95/p99 latency, 4xx/5xx, timeouts and saturation;
- readiness/liveness transitions, restarts, memory/CPU and queue depth/age;
- database connection pool, query latency, migration version, locks, storage and backup age;
- identity issuer/JWKS refresh, token validation failures and session lifecycle errors;
- provider availability, rate limits, latency, retry volume and circuit-breaker state.

### Security, CAL and privacy

- Any non-SHOW candidate returned to a user: page immediately and stop affected serving route.
- Missing/malformed CAL receipt, receipt persistence failure or CAL unavailable: fail closed; alert on sustained failures and any bypass attempt.
- Purchase without candidate-bound authorization or mismatched order/payment totals: page immediately; disable purchase proxy.
- Consent mismatch, unauthorized subject access, tenant-isolation failure or privacy deletion failure: page immediately and contain.
- Any original/unmasked Click It image egress or unauthorized publication: critical privacy incident; disable Click It and affected egress/publication routes.
- Secret exposure, signature verification failure spike, unexpected admin action or suspicious account activity: security incident.

### Commerce and fulfilment

Monitor inventory reservation conflicts, oversell attempts, quote expiry/revalidation failures, FX/tax/fulfilment provider mismatch, payment/webhook reconciliation backlog, duplicate event suppression, shipment exception age, refund/return backlog and merchant suspension propagation.

### Virtual Twin and recommendation quality

Monitor provider/validator failures, generation latency, invalid mesh receipts, asset digest mismatch, consent revocation propagation, render authorization denials, recommendation provider errors and explicit feedback pipeline failures. Do not monitor or retain raw image content for observability.

## 3. Alert policy

Each alert must have a named owner, severity, runbook link, routing destination, deduplication key and tested notification path. Suggested severity:

- **SEV-1:** privacy/security exposure, unauthorized purchase, non-SHOW display leak, data loss, broad outage or payment/order integrity breach. Page incident commander and relevant security/privacy/commerce owners immediately.
- **SEV-2:** critical dependency unavailable, sustained checkout failure, database degradation, provider outage affecting a market, restore/backup failure or material queue backlog. Page service owner; incident commander decides customer-facing degradation.
- **SEV-3:** isolated degraded capability with safe fallback and no integrity/privacy breach. Create tracked incident/task with owner and deadline.

Thresholds must be derived from measured staging/production baselines and approved SLOs. Do not hard-code arbitrary thresholds and call them validated.

## 4. Safe degradation and kill switches

- CAL unavailable or uncertain: do not show candidates; no cached authorization bypass.
- Identity unavailable or invalid session: deny protected routes.
- Payment provider or reconciliation unavailable: stop new checkout; preserve existing order state for reconciliation.
- FX/tax/fulfilment quote stale or provider unavailable: mark the offer unavailable or require a fresh quote; never estimate silently.
- Merchant suspended or inventory uncertain: stop new display/purchase eligibility and invalidate affected caches.
- Complementer unavailable: omit advisory content; core PNELLY discovery may continue only if its own required dependencies and CAL gates pass.
- Virtual Twin provider/validator unavailable: disable generation; do not substitute a skeleton/mock and call it a Twin.
- Click It: remain disabled until all activation gates pass. Any privacy control failure disables processing and publication immediately.

Kill switches must be server-side, access-controlled, audited and tested. Browser-only hiding is not a kill switch.

## 5. Incident procedure

1. **Declare:** record incident ID, severity, start time, affected services/markets/capabilities and incident commander.
2. **Contain:** disable the affected feature/route or provider integration. Preserve logs and evidence without copying sensitive payloads.
3. **Assess:** determine customer, data, payment, privacy, jurisdiction and partner impact. Identify exact release commit and artifact digests.
4. **Communicate:** notify internal owners and affected providers/customers/regulators as required by approved jurisdiction-specific policy. Do not speculate or promise unverified restoration times.
5. **Recover:** restore the last known-good, approved release or safe degraded mode. Validate identity, CAL, data integrity, payment and privacy invariants before re-enabling.
6. **Verify:** run smoke, authorization-denial, reconciliation and data-integrity checks; obtain owner sign-off.
7. **Close:** document timeline, root cause, impact, evidence, corrective actions, owners and deadlines. Conduct blameless post-incident review.

## 6. Backup and restore

Before launch, define and approve numeric RPO/RTO for each datastore. Document backup encryption, retention, region, key custody, restore permissions and immutable backup protections.

Restore drill:

1. Select a recent encrypted backup and record its digest and timestamp.
2. Restore to an isolated clean database/storage namespace; never overwrite production during a drill.
3. Apply only the documented migration sequence and verify schema head.
4. Check referential, tenant, inventory, order, payment, consent and audit invariants.
5. Verify deleted/expired privacy assets are not inadvertently resurrected; apply tombstones and deletion replay before any restored data is served.
6. Run application integration tests and compare record counts/checksums where appropriate.
7. Record measured recovery time, data-loss window, operator, reviewer and evidence reference.
8. Obtain database/reliability owner approval.

## 7. Rollback and deployment

- Deploy immutable image digests built from the exact approved commit.
- Record schema compatibility and migration rollback/forward-fix strategy before release.
- Prefer backward-compatible expand/migrate/contract changes.
- Do not roll back a database migration blindly. Use a reviewed forward fix or restore plan where destructive changes exist.
- After rollback, verify readiness, identity, CAL display, purchase disablement/authorization, order/payment reconciliation, privacy routes and queue processing.
- Re-enable feature flags only after incident commander and accountable capability owner approve.

## 8. Required operational drills

- identity provider/JWKS outage and key rotation;
- CAL/Decision service timeout and malformed receipt;
- Catalog/Commerce/database outage;
- Stripe invalid signature, duplicate webhook and ambiguous payment;
- FX, tax and fulfilment provider outage or stale quote;
- merchant suspension and stock-race propagation;
- Click It consent revocation, rights complaint, CDN purge and deletion failure (in isolated staging only; Click It remains disabled);
- Twin provider timeout, validator mismatch, consent revocation and asset deletion;
- database restore and application rollback;
- alert routing and on-call acknowledgement.

## 9. Evidence template

For every drill, record: run ID; exact commit; environment; image digests; date/time; operator; independent reviewer; scenario; expected behavior; observed behavior; customer/data impact; measured latency/RPO/RTO; sanitized logs/trace IDs; pass/fail; remediation issue; approval.

REL-10 and REL-16 remain blocked while any required owner, alert route, recovery objective, drill, runbook, monitoring dashboard or evidence record is missing.
