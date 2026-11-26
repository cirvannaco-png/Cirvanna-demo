# Staging database security verification — 2026-11-26

**Classification:** partial engineering evidence; not production certification.  
**Candidate source revision reviewed:** `075beb105c37b182c627c371976012e46a5589bb`.  
**No production promotion is authorized by this report.**

## Neon staging

Cirvanna-only Neon project in Frankfurt, PostgreSQL 17:

- Project: `cirvanna-catalog-staging` (`twilight-leaf-50209271`)
- Default branch: `main` (`br-empty-unit-bhpa7igy`)
- Existing PAMASMMA/Midas Neon project was not reused.
- A manual snapshot was restored to a separate branch and source/restore structure matched for Catalog, Commerce and Decision stores. The source branch was not replaced.
- Automatic snapshot schedule is empty; instant-restore history is six hours. The manual snapshot has a seven-day expiry. No production RPO/RTO is claimed.

| Database | Tables | Migration evidence |
|---|---:|---|
| `cirvanna_catalog` | 4 | Alembic `20261104_0002` |
| `cirvanna_commerce` | 30 | Alembic `20261121_0016` |
| `cirvanna_cil` | 8 | Alembic `20261120_0006` |
| `cirvanna_asset` | 1 | SQL migrations; lifecycle-provenance columns from `0002` are present; no Alembic ledger |
| `cirvanna_appearance` | 4 | Tables present; no Alembic ledger |
| `cirvanna_cultural_identity` | 3 | Tables present; no Alembic ledger |
| `cirvanna_npl` | 4 | Tables present; no Alembic ledger |
| `cirvanna_privacy_governance` | 4 | Tables present; no Alembic ledger |
| `cirvanna_wardrobe` | 8 | Tables present; no Alembic ledger |
| `cirvanna_decision_audit` | 8 | Decision migrations `0001` and `0002` are reflected in the tables; no Alembic ledger |
| `cirvanna_decision_receipts` | 8 | Separate duplicate Decision schema; no Alembic ledger |

Nine application runtime principals were previously checked for non-superuser, non-BYPASSRLS, no CREATEROLE/CREATEDB, and no database/public-schema CREATE. These checks do not prove live service-to-database connectivity.

### Commerce CAL purchase-audit immutability

Database: `cirvanna_commerce`.

Verified:
- `commerce_cal_purchase_audits` owner is `cirvanna_commerce_schema_owner`.
- Runtime principal is `cirvanna_commerce_runtime`, not the table owner.
- PostgreSQL UPDATE/DELETE and TRUNCATE guards are enabled.
- Runtime has SELECT/INSERT, but no TRUNCATE, database CREATE or schema CREATE.
- Runtime is not superuser and does not bypass RLS.

A rollback-only probe, executed as `cirvanna_commerce_runtime`, inserted a sentinel audit row and attempted UPDATE, DELETE and TRUNCATE. Each mutation was rejected. The transaction rolled back; a subsequent query confirmed zero sentinel rows remained.

This is database-level immutability evidence only. It does not prove deployed cart/checkout requests receive valid receipts.

### Decision governance store and runtime identity

The application README specifies `cirvanna_decision_audit` and the `DECISION_AUDIT_DATABASE_URL` connection for both receipt persistence and the governance store. That database contains all eight tables from Decision migrations `0001` and `0002`, owned by `cirvanna_decision_audit_schema_owner`.

A dedicated LOGIN principal, `cirvanna_decision_audit_runtime`, was created with read-only database-scoped access and added as a member of the NOLOGIN `cirvanna_decision_audit` group. Effective privileges were checked while logged in as the runtime principal:

- All eight tables: SELECT.
- Receipts, CAM audits, CIL contributions, CIL aggregates and VSL events: INSERT.
- CIL contributions: DELETE only, for the documented retention path.
- CIL privacy budget, VSL profiles and VSL proposals: UPDATE where required.
- No UPDATE/DELETE on append-only receipts, CAM audits, CIL aggregates or VSL events.
- No TRUNCATE on any table; no schema CREATE.

A rollback-only probe executed as `cirvanna_decision_audit_runtime` inserted and read a receipt-shaped row, then rolled back. The row was visible inside the transaction and did not persist afterward. Schema USAGE is allowed; schema CREATE is denied.

A second database, `cirvanna_decision_receipts`, also contains a duplicate eight-table Decision schema. Its separate role `cirvanna_decision_receipts_runtime` has now been narrowed to SELECT/INSERT on `catacaci_decision_receipts` only; it has no access to the other seven governance tables and cannot UPDATE/DELETE/TRUNCATE the receipt table. This duplicate database is not the intended canonical target for the combined receipt/governance adapter. It has not been deleted; database consolidation requires a reviewed migration/retention decision.

**Not yet complete:** neither database URL has been bound to a deployed Decision Service/Gateway. No application-level receipt persistence, duplicate-request hash replay, CAM/CIL/VSL workflow, or fail-closed readiness test has run through the deployed API.

### Asset database

The `cirvanna_asset` database has one `asset_objects` table. Its 0002 lifecycle/provenance fields are present, including private-only publication defaults, consent/masking attestation references, human review fields, publication state and revocation timestamp. No Alembic ledger exists because the service uses ordered SQL migrations. The actual S3-compatible bucket, least-privilege object-store identity, bucket policy/encryption/versioning controls, and live object upload/read/delete tests remain unprovisioned or unverified. The database table alone does not make Asset Service operational.

## Supabase private schemas

Project: `cirvanna-staging`, PostgreSQL 17.12, region `eu-central-1`, status `ACTIVE_HEALTHY`.

Migration history includes the private Identity Learning (`0017_private_service_rls`), Twin Registry (`0005_private_service_rls`) and BFF Auth (`0001_auth_private_sessions`) migrations. The full project migration history also contains the identity age-evidence lifecycle and retry/idempotency migrations.

The Supabase security advisor returned zero lints. The private Identity/Twin/BFF tables have RLS enabled; `anon` and `authenticated` lack schema USAGE on the private schemas. Service-specific policies are present.

Outstanding:
- Identity Learning, Twin Registry and BFF Auth group roles remain NOLOGIN; dedicated LOGIN credentials are not provisioned.
- Real service credential delivery, API-level negative-access tests and deployed identity/session lifecycle tests remain unproven.
- RLS is enabled but FORCE ROW LEVEL SECURITY is false; owner/bypass-role behavior still needs explicit service-role access testing.

## Render Catalog staging plan

A Render Blueprint exists in the selected workspace:

- Blueprint: `exs-dc3s0k6i0phs738ctmj0`
- Planned service: `cirvanna-catalog-staging-qmrw`
- Branch: `integration/private-identity-age-evidence-2026-11-25`
- Candidate commit in the latest plan: `075beb105c37b182c627c371976012e46a5589bb`
- Frankfurt, free public web service; auto-deploy disabled; existing resources left unchanged.
- Production mode enabled; automatic schema creation disabled.
- Separate generated Catalog read and write bearer credentials.
- One manual secret is required: `CATALOG_DATABASE_URL`.

The Blueprint plan is successful but **not approved/applied**. The database URL must be entered through the Render Dashboard or another approved secret-entry path; it must not be committed to Git or exposed in a public client. The CIL gateway URL is intentionally empty at this stage, so Catalog strips CIL-governed product-intelligence fields rather than serving unverified metadata. This is fail-closed behavior, not completed CAL/CIL integration.

After deployment, required tests include TLS, missing/wrong/read-vs-write bearer tokens on every route, rate limiting/abuse controls, token absence from browser assets/logs, database readiness and confirmation that CIL-sensitive fields remain withheld.

## Stripe sandbox

The connected Cirvanna Stripe account is confirmed test mode (`livemode=false`). Read-only API checks returned:
- Products: 0
- Prices: 0
- Checkout Sessions: 0
- Webhook endpoints: 0
- Tax registrations: 0
- Stripe Tax settings: `pending`, missing `head_office`

No test transaction or live-mode operation was performed. Creating test products/prices or Checkout Sessions is held until the business confirms its tax collection position and provides the required head-office details. The sandbox checkout/webhook/reconciliation acceptance gate remains blocked.

## Exact-head CI and release status

On candidate `075beb105c37b182c627c371976012e46a5589bb`, the strict source-lineage audit, architecture validation, release-gate contracts and the listed Catalog, Commerce, Identity, Twin, Wardrobe, PNELLY, Decision, Marketplace, Privacy Governance, NPL, Appearance, Vision and cultural-identity checks completed successfully. The 24-workflow container build run was still in progress at the latest check; no final all-images pass is claimed.

## Gate disposition

REL-03, REL-07, REL-09, REL-10 and REL-16 remain **BLOCKED**. This report is partial supporting evidence only. No `verified_commit` is set. No release gate is promoted. Full acceptance requires the criteria in `docs/release/release-gates.json`, exact deployed commit/image digests, and independent review where required.
