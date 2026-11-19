# Production release gate remediation plan — 19 November 2026

**Baseline:** `main` at `17b8a685a2d84e44d17ded2154b43f0f1921664d`.  
**Registry:** 23 required gates; all 23 blocked; all evidence arrays empty; all verified commits null.  
**Release policy:** no production deployment, checkout enablement or public Click It/Twin launch until all applicable gates pass with evidence tied to one exact candidate SHA and reviewed by the named owner.

This plan sequences the existing 23 gates. It does not mark any gate passed. Code and synthetic CI prepare evidence; they do not replace real providers, staging transactions, customer outcomes, restores or independent assessment.

## Current verified baseline

- Canonical inventory: 21 services; all `production_enabled=false`.
- Four services are not containerized: Wardrobe, NPL, Cultural Identity and Xari. The first three sit on the intended marketplace path; Xari's launch scope must be decided under REL-12.
- Eight logical PostgreSQL stores are listed; all are unprovisioned for production and have unverified backup/restore.
- Production host/platform, environment ID, release SHA and operational-complete flag are unset.
- All 17 external provider integrations are unconfigured and not operationally verified.
- Central telemetry backend, alerts, on-call owner and restore-drill evidence are unconfigured.
- No Cirvanna service/database exists in the connected Render workspaces. The connected Supabase project is healthy at platform level but has no application migrations or public application tables; its advisor flags `public.rls_auto_enable()` as a SECURITY DEFINER event-trigger function executable by `anon` and `authenticated`. Direct RPC reachability has not been established. It is not accepted as staging/production pending owner designation and privilege review.
- Rollback procedure/validator are in the repository, but the record remains `not_executed`. No traffic reversal, isolated restore or measured RTO/RPO is recorded.

## Wave 0 — release integrity and scope

| Gate | Required work | Exit evidence |
|---|---|---|
| REL-01 Exact-candidate CI | Run required workflows on one immutable candidate SHA. Run source archive/snapshot/candidate-lineage audit in strict mode, without `--allow-unreconciled`; resolve or formally approve every content-difference exception. | Exact-head workflow links; strict lineage report with zero unresolved paths; dispositions for skips/warnings; verified candidate SHA. |
| REL-12 Capability claims and scope | Publish live/limited/unavailable/deferred status for FCI, safety, USI/NPL, CAL, DSI, Twin, Try-On, PNELLY, Look It and Click It. Approve the smallest launch boundary. | Signed product/risk decision tied to the candidate SHA; every public claim supported by evidence. |

## Wave 1 — platform, database, identity, security and telemetry

| Gate | Dependencies | Required work | Exit evidence |
|---|---|---|---|
| REL-02 Approved infrastructure | None | Select canonical host/workspace, region, budget, data residency, recovery owner, alert recipient, RPO/RTO and service inventory. Do not reuse unrelated project resources. | Approved provider/workspace/resource IDs, budget, named accountable operators and signed recovery objectives. |
| REL-03 Managed DB and restore | REL-02 | Decide physical cluster vs isolated logical DB/schema layout for eight stores; implement migrations and schema/runtime role separation; test CAL audit immutability; encrypted backup and isolated restore. | Exact schema versions; runtime cannot mutate/disable audit guards; UPDATE/DELETE/TRUNCATE rejected; encrypted backup, isolated restore and app invariants verified. |
| REL-04 Real OIDC | REL-02, REL-09 | Select provider; pin issuer/audience/JWKS/trusted roles; implement browser login, refresh, logout, expiry, key rotation and negative cases. | Provider-issued lifecycle tests and role/tenant isolation evidence. |
| REL-09 Security/privacy | REL-02 | Threat review; least privilege, private networking, HTTPS, CORS/CSP/rate limits, secrets rotation, log redaction, consent revocation, retention, export/deletion and tenant isolation. Review the Supabase advisor warning before any adoption. | Signed security review, scan results, access/secret review and consent/deletion propagation evidence. |
| REL-23 Telemetry/alerting | REL-02, REL-09 | Instrument all production services/workers; choose private logs/metrics/traces backend; configure dashboards, SLOs and named alert routes. | Service coverage matrix, private collector config, dashboard links, tested notifications, retention/access policy and named rota. |

**Build prerequisite:** containerize and verify build contexts for Wardrobe, NPL and Cultural Identity. Decide whether Xari is required in launch scope. Validate all 21 service build contexts; a Dockerfile alone is not proof of a reproducible image.

## Wave 2 — marketplace, decision and commerce

| Gate | Dependencies | Required work | Exit evidence |
|---|---|---|---|
| REL-06 Catalog/merchant/inventory | REL-02/03/04/09 | Approve a small merchant cohort and legal/KYC decisions; load reviewed real product/variant/offer/inventory; enforce freshness, suspension and oversell controls. | Verified merchants, reviewed staging catalog/inventory, freshness evidence, concurrency/oversell tests and owner isolation. |
| REL-08 Safety and FCI | REL-02/09 | Select licensed safety/fit providers; curate human-reviewed corpora and participant/time-disjoint splits; assess calibration, subgroup performance, uncertainty, drift and provider failure. | Signed independent reports, pinned artifact hashes, sample counts, calibration/subgroup metrics and failure evidence. Mock PASS fixtures do not count. |
| REL-07 CAL display/receipts | REL-03/04/06/08/09 | Require SHOW before any product/offer detail; persist receipt before response; enforce subject/context binding, CIL review veto and fresh signed purchase receipts; preserve immutable Commerce audit. | Deployed route coverage, SHOW/BLOCK/REVIEW evidence, durable receipts, replay/stale/mismatch/revocation tests and database privilege/trigger proof. |
| REL-13 Multi-market | REL-02/03/04/06/22 | Reconcile to one migration chain; implement trusted FX/tax/payment/fulfilment capability adapters, market/currency separation, like-for-like comparison, radius and quote revalidation. | Provider-attested quotes bound to variant/merchant/market/destination/value/currency/validity; consistent order/payment/webhook totals; stale evidence withheld. |
| REL-22 Merchant verification/fulfilment | REL-02/03/04/06/09/13 | Select per-market legal-entity/beneficial-owner and logistics providers; implement activation, revocation/recheck, quote-to-booking binding, idempotent shipping and reconciliation. | Authenticated provider checks, human approval, staging booking/tracking/cancellation/exception and reconciliation evidence. |
| REL-05 Stripe | REL-03/04/06/07/09/13 | Configure test mode; bind order/amount/currency, reserve inventory, implement idempotency, signed webhooks, expiry and ambiguous-payment reconciliation. | Test-mode transaction set, invalid/duplicate webhook tests and provider reconciliation. Redirect alone never proves payment. |

**Checkout stays disabled by default.** Do not enable it until REL-05, REL-07, REL-13, REL-22 and operational controls pass in staging with release-owner approval.

## Wave 3 — privacy, personalization and partner services

| Gate | Dependencies | Required work | Exit evidence |
|---|---|---|---|
| REL-14 Click It privacy/rights/children | REL-02/03/09/16/23 | Keep disabled; inventory every publish/restore/share/syndication/media route; select licensed masking, rights, jurisdiction, guardian and lifecycle providers; fail closed before downstream exposure. | Independent exact-release assessor report, asset/detector digests, subgroup false-negative intervals, zero unmasked escapes, rights/quarantine/deletion propagation. |
| REL-17 Persistent Twin | REL-03/04/09/16 | Integrate private Asset Service, Twin Registry and resource-bound consent; license full-body model/validation; implement revocation, deletion and restore. | Independent signed representation report, pinned model/licence/asset digests, real create/read/revoke/delete and restore tests. Structural mesh checks alone do not pass. |
| REL-18 PNELLY Look It | REL-03/04/07/09 | BFF subject binding, short-lived purpose/resource consent, independent PNELLY re-verification, transient image processing and mandatory revocation; keep separate from Click It. | Real consent/expiry/revocation tests, no image persistence, withholding before CAL SHOW, processor privacy approval where applicable. |
| REL-19 Brand/distributor portals | REL-02/03/04/06/22/23 | Distinct business tenants, owner/member roles, audited invitations, access revocation, row-level isolation and event-backed dashboards. | Verified tenants, row-level tests, invite/revoke evidence and metrics from durable commerce events. |
| REL-20 CIL outcomes | REL-03/04/07/09/23 | Trusted server adapter with purpose consent, pseudonymous contributors, exact CAL receipt binding, explicit suitability reports only, idempotency and cohort suppression. | Real service-identity grant/revoke/replay/expiry tests, 30-contributor suppression and CIL→CAL retrieval evidence. |
| REL-21 PNELLY wardrobe loop | REL-03/04/06/07/15/20 | Authenticated discovery with consented wardrobe/style context, bounded memory, reset/export/delete and persistent rotation; Complementer remains advisory. | Subject isolation, wardrobe event lineage, three-look rotation, consented feedback and CAL-only product/offer release. |

## Wave 4 — operation, measured quality and final acceptance

| Gate | Dependencies | Required work | Exit evidence |
|---|---|---|---|
| REL-10 Operations/recovery | REL-02/03/16/23 | Assign incident/on-call roles; test support/refund/fulfilment; exercise provider, privacy, payment, database and rollback runbooks. | Named rota and tested alerts; real rollback record with per-service immutable digests, DB strategy, measured RTO/RPO, zero gaps and independent approver. |
| REL-16 Canonical deployment | REL-02/03/04/09/10/23 | Deploy full agreed graph on one platform with immutable images, secrets, managed stores, telemetry, backups and rollback. | Exact-release service inventory, image digests, migrations/provider bindings, successful restore/rollback and promotion evidence. |
| REL-15 Decision quality | REL-07/08/20/21/23 | Collect genuine fit/suitability outcomes; compare PNELLY, Complementer and baseline on identical human-reviewed, participant/time-disjoint pools. | Holdout/calibration metrics, subgroup slices, uncertainty/sample counts, zero hard-exclusion violations and owned monitoring. |
| REL-11 Deployed staging journey | REL-03/04/05/06/07/08/09/10/13/16/22/23 | Run authenticated customer path through consent/profile, PNELLY, USI/NPL/EEPL, Catalog, FCI/safety, CAL, offer, cart, payment, webhook, persistence and recovery. | Redacted request IDs tied to exact SHA; positive/negative/failure paths; latency/error/conversion/fit measures; rollback/restore evidence. |

## Decisions required before real provisioning

1. **Hosting provider/workspace and region:** no Cirvanna staging deployment is recorded. Connected Render workspaces do not contain Cirvanna resources; nothing was created there.
2. **Database authority:** the connected Supabase project is not accepted as Cirvanna staging. Its app migration list/public app schema are empty and its security warning needs review. Do not apply the eight-store migrations until it is designated and existing objects are dispositioned.
3. **Cost and operations:** approve provider plan/budget, data region, recovery owner, alert recipients, RPO and RTO.
4. **External providers:** OIDC, Stripe, FX, tax, fulfilment, merchant verification, safety/FCI, image rights/masking, private storage, licensed rendering and telemetry remain unconfigured.

## Stop conditions

- No checkout before fresh CAL purchase authorization, payment reconciliation and explicit release-owner approval.
- Click It stays disabled until independent route/masking assessment passes.
- Twin/Try-On remain unavailable until licensed model, consent, asset and independent validation evidence exists.
- No gate passes from documentation, mocks, synthetic CI, an unexecuted template or a healthy-but-empty database project.
- Keep all gates blocked until evidence is reviewed and tied to the exact candidate commit.
