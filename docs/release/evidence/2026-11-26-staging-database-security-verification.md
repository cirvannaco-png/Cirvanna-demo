# Staging database security verification — 2026-11-26

**Classification:** partial engineering evidence; not production certification.  
**Candidate source revision reviewed:** `bfa8ad52613f2d8e355a659fd5fb0240d5a8e475`.  
**No production promotion is authorized by this report.**

## Neon staging

A Cirvanna-only Neon project is provisioned in Frankfurt on PostgreSQL 17:

- Project: `cirvanna-catalog-staging`
- Project ID: `twilight-leaf-50209271`
- Branch: `main` (`br-empty-unit-bhpa7igy`)
- Existing PAMASMMA/Midas Neon project was not reused.

The following service databases were present:

| Database | Tables | Migration state |
|---|---:|---|
| `cirvanna_catalog` | 4 | Alembic `20261104_0002` |
| `cirvanna_commerce` | 30 | Alembic `20261121_0016` |
| `cirvanna_cil` | 8 | Alembic `20261120_0006` |
| `cirvanna_decision_audit` | 0 | Not initialized |
| `cirvanna_asset` | 1 | No Alembic ledger found |
| `cirvanna_appearance` | 4 | No Alembic ledger found |
| `cirvanna_cultural_identity` | 3 | No Alembic ledger found |
| `cirvanna_npl` | 4 | No Alembic ledger found |
| `cirvanna_privacy_governance` | 4 | No Alembic ledger found |
| `cirvanna_wardrobe` | 8 | No Alembic ledger found |

Nine corresponding runtime principals were tested. Each had LOGIN and each returned:

- `rolsuper = false`
- `rolbypassrls = false`
- `rolcreaterole = false`
- `rolcreatedb = false`
- no database CREATE
- no `public` schema CREATE

This verifies principal privilege posture, not successful service-to-database deployment or end-to-end application authentication.

## Commerce CAL purchase-audit immutability

Database: `cirvanna_commerce`.

Verified:
- `commerce_cal_purchase_audits` owner is `cirvanna_commerce_schema_owner`.
- Runtime principal is `cirvanna_commerce_runtime`, not the table owner.
- PostgreSQL UPDATE/DELETE trigger and TRUNCATE trigger are enabled.
- Runtime role has SELECT and INSERT; it has no TRUNCATE, database CREATE or schema CREATE.
- Runtime role is not superuser and does not bypass RLS.

A rollback-only SQL probe, executed as `cirvanna_commerce_runtime`, inserted a sentinel audit row and attempted UPDATE, DELETE and TRUNCATE. Each operation was rejected. The enclosing probe rolled back and a subsequent query confirmed zero sentinel rows remained.

This is database-level immutability evidence for the Commerce purchase-audit table. It does not prove that every production cart/checkout request receives a valid receipt, or that the API has been deployed.

## Supabase private schemas

Project: `cirvanna-staging`, PostgreSQL 17.12, region `eu-central-1`, status `ACTIVE_HEALTHY`.

Migrations present:
- Identity `0017_private_service_rls`
- Twin `0005_private_service_rls`
- BFF Auth `0001_auth_private_sessions`

All 16 tables across `identity_private`, `twin_private`, and `auth_private` have RLS enabled. Service-specific policies are present. `anon` and `authenticated` have no schema USAGE on those schemas. Supabase security advisor returned zero lints.

Outstanding:
- The group roles `identity_learning_service`, `twin_registry_service`, and `cirvanna_bff_auth` remain NOLOGIN.
- No dedicated LOGIN members were found.
- Real service credential delivery, application-level negative-access tests, and deployed identity/session lifecycle tests remain unproven.
- RLS is enabled but `FORCE ROW LEVEL SECURITY` is false; owner/bypass-role behavior still requires an explicit service-role access test.



## Durable CAL decision-receipt store

A separate database `cirvanna_decision_receipts` was created in the same Cirvanna-only Neon project. It contains the exact table contract from `services/decision-service/migrations/0001_catacaci_decision_receipts.sql`:

- `decision_private.catacaci_decision_receipts`
- Unique request/candidate constraint
- Verdict and `may_display` consistency constraint
- Policy, contract, signal, reason and candidate snapshot digest fields
- Candidate/verdict time indexes

The dedicated runtime principal is `cirvanna_decision_receipts_runtime`. Database privilege checks confirmed:
- schema USAGE: allowed; schema CREATE: denied
- table SELECT/INSERT: allowed
- table UPDATE/DELETE/TRUNCATE: denied

A rollback-only probe inserted a receipt-shaped test row, read it back, then attempted UPDATE, DELETE and TRUNCATE. All mutation attempts were denied. The probe rolled back and the follow-up count was zero.

**Not yet complete:** `DECISION_AUDIT_DATABASE_URL` has not been bound to a deployed Decision Gateway or Decision Service. The code-level `persist_decision_receipt` integration, duplicate-request hash replay, and production readiness probe have not been exercised against this database. The previous empty `cirvanna_decision_audit` database remains unused.

## Known deployment and provider blockers

- Render private Catalog service blueprint planning returns `need_payment_info`. No public/free Catalog endpoint was created because the service is internal and exposing it publicly would create an avoidable CAL bypass surface.
- Neon Decision Audit database is empty. The Decision Gateway's production PostgreSQL receipt adapter therefore is not yet provisioned or verified.
- Stripe sandbox is confirmed `livemode=false`; it has no product and no webhook endpoint. Stripe Tax settings are `pending`. No Checkout Session or payment was created.
- No production services, real payment transactions, independent assessor reports, backup restore drill, rollback drill, or full staging E2E run are evidenced here.

## Gate disposition

REL-03 and REL-07 remain **BLOCKED**. This report is partial supporting evidence only. No `verified_commit` is set. Gate promotion requires the complete acceptance criteria in `docs/release/release-gates.json`, exact deployed commit/image digests, and independent review where required.
