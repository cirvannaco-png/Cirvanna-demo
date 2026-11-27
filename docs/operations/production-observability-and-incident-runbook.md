# Production observability, SLOs and incident runbook

**Status: code-level telemetry hooks added to the Marketplace BFF, Commerce, Privacy Governance and Decision API Gateway services. Central collection, alert routing, on-call ownership, dashboards and production incident drills remain unconfigured.** A metrics endpoint is not proof of an operational monitoring system.

## 1. Telemetry implemented in the release-readiness branch

The three critical services now share a small, dependency-free telemetry module.

- `GET /internal/metrics` exposes Prometheus text format only when `METRICS_ENABLED=true` and a dedicated `OBSERVABILITY_METRICS_TOKEN` of at least 32 bytes is configured.
- Scrapers must send `X-Observability-Token`; the endpoint is not part of the public customer navigation or API contract. Missing configuration returns 404; an invalid token returns 401. **The bearer token is application authentication, not a network firewall:** production ingress/network policy must separately allow only the monitoring network or private service mesh to reach this route, and the proxy must preserve a trustworthy client address. Do not expose `/internal/metrics` through public routing.
- `http_server_requests_total` and `http_server_request_duration_seconds` use only service name, HTTP method, route template and status code. Dynamic identifiers, query strings and request content are not metric labels.
- Each request gets a generated `X-Request-ID` response header. Structured stdout logs contain only request ID, method, route template, status and elapsed milliseconds.
- Request bodies, query strings, Authorization headers, user IDs, asset IDs, image bytes, face crops, embeddings and exception messages are not recorded by this middleware.
- Counters are process-local and reset on restart. They must be scraped frequently and correlated with platform logs/traces; they are not a durable audit ledger or a replacement for provider, database or business-event monitoring.

This slice covers the public ingress, Commerce transaction service, Privacy Governance service and Decision API Gateway. The remaining services (Asset, Vision, Twin Registry, Virtual Twin, Gateway, Catalog, Identity, Wardrobe, NPL, CIL and workers) still need consistent instrumentation before full platform SLOs can be measured.

## 2. Deployment configuration

Set per service in the approved secret manager:

- `METRICS_ENABLED=true`;
- unique high-entropy `OBSERVABILITY_METRICS_TOKEN` (32+ random bytes; rotate independently per service);
- `OTEL_SERVICE_NAME` matching the canonical service ID;
- `OTEL_EXPORTER_OTLP_ENDPOINT` and approved protocol/headers only for the selected private telemetry collector;
- `LOG_LEVEL=INFO` for normal operations; do not switch production logging to verbose body/debug capture.

Scrape `/internal/metrics` over a private service network with a dedicated monitoring identity. Enforce this at the platform ingress/service-mesh layer; the path name and bearer token do not make a public listener private. Do not make the scrape route public, proxy it through the browser, add it to CORS, or store the scrape token in frontend configuration. Confirm that the collector strips or rejects sensitive labels and that log retention and access meet the approved privacy schedule.

No monitoring vendor, collector, alert route, dashboard or pager is selected/configured by this repository. The platform owner must approve the service, data region, retention, encryption, access roles, budget, retention/deletion and alert recipient before activation.

## 3. Initial SLOs and alerts (proposed; not measured)

Treat the following as launch candidates. Measure them in staging and agree error budgets with the service owner before production; do not report them as achieved performance.

| Signal | Initial trigger | Owner/action |
|---|---|---|
| Public BFF 5xx rate | >2% for 5 minutes with at least 100 requests | Marketplace on-call; check BFF and upstream readiness; rollback if release-correlated |
| Public BFF latency | p95 >1.5 seconds for 10 minutes | Marketplace on-call; identify slow upstream and shed non-critical optional work |
| Critical service readiness | two consecutive failed authenticated readiness probes | Service owner; hold new traffic and investigate DB/provider state |
| Commerce payment reconciliation | any paid/amount/currency mismatch or unverified payment settlement | Commerce/payment owner; stop order fulfillment, preserve event IDs, reconcile provider source |
| Checkout/webhook backlog | oldest pending payment/webhook reconciliation item >2 minutes | Commerce on-call; inspect provider delivery, retry safely, never infer payment from browser redirect |
| Fulfilment booking mismatch | paid order without confirmed shipment or duplicate booking | Commerce operations; put affected order on hold, reconcile with carrier before retry |
| Privacy Governance provider health | any required jurisdiction/content-lifecycle/guardian/authority/attestation provider not ready for >5 minutes | Privacy on-call; keep Click It and affected media paths disabled |
| Urgent image-rights quarantine | any `quarantine_failed` case or unconfirmed unpublish | P1 privacy incident; disable publication, manually quarantine through approved console, keep request open |
| Deletion propagation | any missing source/derivative/replica/cache/CDN/shared-link surface | Privacy incident owner; do not close case or re-enable media |
| Database recovery | backup missing, backup age above approved RPO, or restore drill fails | Database owner; freeze release and execute recovery runbook |

Proposed initial public marketplace availability objective: 99.5% monthly. Checkout, consent and privacy critical-path SLOs must be separately defined and cannot be hidden by average marketplace availability. A critical privacy/authorization failure is a release blocker even when aggregate uptime is high.

## 4. Incident roles

Before staging sign-off, name an incident commander, service owner, privacy/security owner, database/reliability owner, payment/commerce owner and communications/legal contact. Record a 24/7 escalation route or explicit business-hours coverage and the escalation response target. A role label in documentation is not an assigned on-call person.

## 5. Runbook — suspected unmasked photo or privacy exposure

1. Declare a privacy/security incident and assign an incident commander.
2. Disable Click It at the public BFF (the current route is already hard-disabled) and disable all media publish, restore, share, syndication and serving paths in the affected environment.
3. Quarantine the asset/source and preserve minimal metadata/audit evidence. Do not duplicate photo bytes, face crops or identity signals into chat, tickets or logs.
4. Revoke relevant consent and stop outstanding processing/worker jobs. Disable affected credentials if compromise is suspected.
5. Identify affected object versions, derivatives, replicas, backup copies, caches, CDN origins, shared links and merchant surfaces.
6. Start the photographed-person rights process; urgent possible-minor, unmasked-face and non-consensual reports must remain quarantined until verified resolution.
7. Verify deletion/unpublish propagation for every required surface; document any backup/legal-retention exception and its expiry.
8. Complete legal/jurisdiction and notification assessment with the authorized privacy/legal owner. Do not guess reporting deadlines.
9. Re-enable nothing until the independent assessor signs a new exact-release verification and the privacy release owner approves.

## 6. Runbook — payment or order reconciliation incident

1. Stop new checkout at the BFF purchase gate; retain the current default-off CAL purchase proxy configuration until the incident is resolved.
2. Do not trust client redirects or screenshots as proof of payment. Identify the Commerce order, Checkout Session, PaymentIntent, provider event IDs and idempotency key.
3. Verify webhook signature, timestamp tolerance, provider account, amount, currency, order binding and event deduplication.
4. Reconcile against the provider dashboard/API and durable Commerce payment/audit records. Never manually flip an order to paid without authoritative evidence.
5. Pause fulfillment for mismatched/unknown state; only process refunds/voids using the verified payment record and documented approval.
6. Replay the webhook only through the idempotent verified handler; record the replay result and immutable audit reference.
7. Resume checkout only after the Commerce owner verifies payment, CAL authorization, audit persistence and duplicate/replay controls in staging.

## 7. Runbook — merchant or fulfilment provider outage

1. Mark the affected provider capability unavailable; do not issue estimated quotes or seller-created values as authoritative provider evidence.
2. Withhold affected markets/modes/offers when no fresh valid quote exists. Do not silently route to a different carrier or market.
3. For already paid orders, do not book a second shipment blindly. Query by idempotency/provider reference and reconcile accepted booking state.
4. If the provider cannot confirm a booking, place the order in an operations hold queue and contact the merchant/customer using the approved workflow.
5. Retry only with the same idempotency key after the provider state is known. Log provider reference and normalized reason codes, never secrets or unnecessary personal data.
6. Reconcile quote expiry, booking state, carrier charge and delivery status before closing the incident.

## 8. Runbook — database degradation or restore

1. Stop releases and any migration/worker action that could worsen the database state.
2. Identify the affected database owner and exact last known migration revision. Do not point one service to another service's database.
3. Verify backup existence, encryption, age, point-in-time recovery window and restore owner.
4. Restore to an isolated environment first; validate schema revision, constraints, record counts and application read/write invariants.
5. Reconcile Commerce orders/payments, Privacy Governance consent/revocation/rights cases and Identity/Wardrobe deletion state against their external event sources.
6. Promote the restored database only under the approved change/incident procedure. Preserve evidence and run the full critical-path smoke tests.
7. Close only after application owners confirm correctness and a second restore drill is scheduled.

## 9. Release and operational checklist

Before REL-10/REL-16 can pass, provide evidence for:

- central metrics, logs and traces configured for all production services with least-privilege access and tested retention;
- dashboards and alert rules enabled with successful test notifications to named owners;
- tested readiness probes and synthetic end-to-end checks for sign-in, discovery/CAL, cart/checkout/payment, rights report/quarantine and deletion propagation;
- database backup and point-in-time restore drills for each owned data store with measured RPO/RTO;
- secrets rotation, access review, rollback, rate limits, queue retry/dead-letter, provider outage and disaster recovery drills;
- incident commander/on-call assignments, escalation tree, customer/privacy communication templates and after-action review process;
- exact release commit, image digests, migration revisions, provider/API versions, SLO report, test-run links and operator sign-off.

Do not set REL-10 or REL-16 to passed because the metrics endpoint returns text, a CI test succeeds, or a runbook exists. They require deployed collection, alert delivery, a real restore and an exercised incident procedure.

### Shopify compensation and Stripe refund manual review

Commerce emits durable manual-review events when a seller-side compensation or Stripe refund cannot safely complete. Before enabling the worker's manual-review consumer, configure an approved HTTPS receiver using `COMMERCE_OPERATIONS_WEBHOOK_URL` and `COMMERCE_OPERATIONS_WEBHOOK_SECRET`. The receiver must verify the exact-body HMAC, persist by idempotency key, notify the assigned Commerce operator, and return success only after durable acceptance. Missing configuration or a failed receiver must leave the Commerce outbox event unacknowledged for retry. The repository does not currently prove that a production recipient, pager, dashboard or on-call rotation exists; REL-10 remains blocked until a real notification delivery test reaches a named owner.
