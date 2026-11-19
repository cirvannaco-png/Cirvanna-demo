# Release rollback procedure and evidence standard

**Status: procedure defined; no production rollback exercise is recorded.** This document makes the rollback path reproducible and auditable. It does not certify an environment, image, database restore, operator, or rollback drill.

## 1. Safety principles

1. Roll back to a previously deployed, approved immutable artifact. Do not rebuild an old source revision during an incident and assume it is equivalent to the former production image.
2. Application rollback and database recovery are separate decisions. Do not run an automatic destructive down-migration as part of an application rollback.
3. Keep checkout and other purchase capabilities fail-closed during rollback. The CAL purchase switch stays off until the Commerce owner has verified the restored version, current authorization evidence, and payment reconciliation.
4. Click It, public media publication, and any affected image-serving route remain disabled during a privacy incident. A rollback is not proof that already published media was quarantined or deleted.
5. Preserve provider event identifiers and durable business records. A database restore can discard transactions written after the backup; reconcile orders, payments, consent revocations, rights cases, and deletion events before reopening affected paths.
6. The operator performing the rollback cannot be the sole approver of the evidence record.

## 2. Required pre-deployment rollback package

Before promoting a candidate, the release owner must record and verify:

- exact release commit SHA and immutable image digest for every deployed service, recorded as a service-ID → `sha256:` digest map;
- exact previous known-good commit SHA and immutable image digest for every service in the rollback set; candidate and rollback maps must cover the same service inventory;
- deployment and environment identifiers, region, a reviewable service-inventory reference, expected service IDs, and current traffic-routing configuration;
- configuration and secret-version references (never secret values), feature-flag state, queue/worker version, and migration revision;
- candidate migration revision, explicit rollback-target schema compatibility decision, and the chosen database strategy (`backward_compatible_application_rollback`, `forward_fix`, or `point_in_time_restore`);
- latest encrypted pre-release backup reference, backup timestamp, retention class, restore-point window, schema-validation reference, external-event reconciliation reference, and isolated restore reference whenever point-in-time restore is selected;
- owner for application rollback, database recovery, payments, privacy, and incident command;
- approved RPO/RTO and tested health checks for the exact deployment topology.

If any required artifact, digest, schema compatibility result, or responsible owner is missing, do not start a production promotion.

## 3. Rollback triggers

The incident commander declares rollback or traffic hold for any of the following:

- a critical authorization, consent, NPL hard-veto, or CAL decision leak;
- a non-SHOW candidate or unverified media becoming visible;
- a payment/order amount, currency, inventory, or reconciliation mismatch;
- failed identity/session validation or cross-tenant access;
- a material privacy, deletion, or unmasked-media exposure;
- persistent critical-service readiness failure or release-correlated error/latency beyond the approved SLO/error budget;
- a failed migration or data-integrity invariant that cannot be repaired safely while serving traffic.

Privacy/authorization failures require immediate containment; do not wait for an aggregate error-rate threshold.

## 4. Execution sequence

### A. Contain and record

1. Declare the incident, assign an incident commander, and record UTC start time, candidate commit, deployment ID, service/image digests, trigger, and affected capabilities.
2. Freeze promotion and automated deployment. Stop further traffic ramp-up.
3. Disable checkout at the BFF purchase gate and pause fulfillment for uncertain orders. Keep the purchase kill switch off.
4. For privacy incidents, disable Click It and all affected publish, restore, share, syndication, and media-serving paths. Quarantine affected asset versions and stop in-flight workers.
5. Preserve redacted request IDs, provider event IDs, deployment references, and audit references. Do not copy tokens, secrets, customer photos, face crops, embeddings, or raw personal data into incident records.

### B. Restore the previous application version

1. Select the recorded previous known-good deployment; verify its commit SHA and image digests against the pre-deployment package.
2. Verify the target images are still present, signed/approved as required, and match the recorded digests. Do not rebuild or retag them.
3. Switch traffic to the previous deployment using the platform's approved traffic-routing mechanism. Record the change/deployment reference and UTC completion time.
4. Keep background workers paused until their code version, queue message compatibility, and idempotency behavior have been checked.
5. Confirm every service in the rollback set reports the expected version and authenticated readiness state.

### C. Decide database treatment separately

1. Record the exact migration revisions applied by the candidate and whether they are backward compatible with the previous application.
2. Prefer an application rollback against a backward-compatible expanded schema. Use reviewed expand-and-contract migrations; destructive contract steps must not be part of the same release that first removes old application compatibility.
3. Do not run down-migrations automatically. If schema incompatibility exists, keep affected writes and traffic held while the database owner chooses a tested forward repair or an isolated point-in-time restore.
4. Before any restore, identify the recovery point and calculate the potential data-loss interval against approved RPO. Restore to an isolated database first; validate schema, constraints, row counts, ordering, inventory, and payment invariants.
5. Never promote a restored database until post-backup Commerce orders/payments, provider webhooks, consent grants/revocations, image-rights cases, deletion requests, and queue events have been reconciled from authoritative sources. Do not overwrite newer durable events with an older backup.
6. Record restore and reconciliation references, observed data-loss interval, unresolved gaps, and database-owner approval.

### D. Verify the rolled-back system

The release owner runs and records the following against the rolled-back environment:

- deployment version and immutable image digests match the rollback target;
- public ingress, internal service readiness, and dependency health pass;
- OIDC login, subject binding, refresh, expiry, logout, and tenant boundaries pass;
- discovery executes USI/NPL/EEPL/FCI/CAL; explicit NPL exclusions still withhold candidates; missing evidence remains REVIEW; only CAL SHOW plus CIL serving eligibility releases candidate/offer details;
- cart and checkout remain disabled unless the purchase owner separately approves a staging-only controlled test; any enabled path requires fresh subject/action/candidate/offer-bound CAL purchase receipts;
- payment webhook signatures, idempotency, amount/currency binding, duplicate delivery, and provider reconciliation remain correct; uncertain orders stay on hold;
- consent revocation, privacy quarantine, deletion propagation, and worker/queue state are correct; Click It and public media routes remain disabled where independent privacy acceptance is incomplete;
- no unexpected queue backlog, duplicate job, inventory oversell, or cross-tenant access is observed;
- monitoring and alert routes are receiving signals from the rolled-back versions.

A successful HTTP health response alone is insufficient.

## 5. Evidence record and approval

Complete a copy of rollback-evidence-template.json for each exercised environment and rollback event. The record must include:

- full candidate and rollback commit SHAs;\n- a per-service map of candidate and rollback immutable image digests covering every service in the referenced deployment inventory;\n- database migration revision, recovery strategy, schema compatibility proof, backup/restore proof, external-event reconciliation, measured data-loss interval and approved RPO;
- immutable candidate and rollback image digests;
- environment/deployment identifiers;
- trigger, start/end timestamps, and traffic-switch reference;
- pre-rollback and post-rollback health-check evidence;
- database compatibility or isolated restore evidence;
- payment/order and consent/privacy reconciliation evidence;
- operator and independent approver;
- measured rollback duration, approved RTO, data-loss observation, and reconciliation-gap count;
- explicit result for each post-rollback critical path.

Evidence references must point to an approved private evidence store or reviewable CI/deployment record. References must be redacted and must not disclose secrets or customer information. The template intentionally remains not_executed until a real exercise supplies evidence.

## 6. Release gate mapping

- REL-03 remains blocked until each owned managed database has a successful encrypted backup and isolated restore with application/business invariants.
- REL-10 remains blocked until incident roles, alerts, operational procedures, and an actual rollback/incident exercise are approved and evidenced.
- REL-16 remains blocked until the canonical deployment has immutable image/version evidence, managed data stores, successful recovery, monitoring, and an exact-release operational rollback exercise.
- A document, unit test, synthetic CI fixture, deployment manifest, or unexecuted template is not rollback evidence.
- Any rollback failure, RTO breach, data loss, or reconciliation gap keeps the release blocked and requires an incident review before another promotion.
