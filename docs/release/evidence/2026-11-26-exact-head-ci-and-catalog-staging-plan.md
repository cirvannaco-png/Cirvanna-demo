# Exact-head CI and public Catalog staging plan — 2026-11-26

**Candidate commit:** `23cec18cedfb877a9b1ffcb1138b5e3f6d2cd182`  
**Pull request:** [#338](https://github.com/cirvannaco-png/Cirvanna-demo/pull/338)  
**Status:** CI passed; Render Blueprint planned; deployment not applied.  
**Production certification:** Not granted.

## Exact-head CI

GitHub Actions returned 24 PR-triggered workflow runs for the candidate commit. All 24 completed with `conclusion=success`. This includes:

- Container image builds
- Source lineage strict audit
- Architecture validation
- Catalog, Commerce, Marketplace BFF, Decision Gateway and Decision Service
- Identity/temporal learning, Twin Registry, Wardrobe, Privacy Governance, NPL, Appearance and Vision
- Release-gate contract tests

This is source/CI evidence only. It is not a deployed service test.

## Catalog public-staging security review

The current `render.yaml` declares one Frankfurt Docker web service on the free plan, with auto-deploy disabled. It uses the Catalog production mode and disables automatic schema creation. Render's plan generated separate read and write bearer secrets; the database URL is the sole required manual environment value.

Source review of `services/catalog-service/app/main.py` confirms:

- Product and variant read endpoints require the read-scoped bearer credential.
- Product and variant mutation endpoints require the write-scoped bearer credential.
- Production readiness reports only generic ready/not-ready output; detailed diagnostics are not exposed.
- Liveness is separate from readiness.
- OpenAPI/docs routes are disabled in production.
- Catalog CIL-governed product-intelligence metadata is withheld when the CIL gateway is not configured or its evidence cannot be validated.

This makes the requested public-network staging configuration materially safer than an unauthenticated public API, but it is not yet independently accepted. Required before exposing the URL to broader testers: deploy, verify TLS, test missing/wrong/read-vs-write tokens against every route, confirm no token is present in browser assets/logs, validate rate limits/abuse controls, and confirm CIL-sensitive fields remain withheld.

## Render Blueprint

A Render Blueprint was created in the user's selected workspace with:
- Blueprint ID: `exs-dc3s0k6i0phs738ctmj0`
- Candidate commit: `23cec18cedfb877a9b1ffcb1138b5e3f6d2cd182`
- Branch: `integration/private-identity-age-evidence-2026-11-25`
- Auto-sync: disabled
- Existing-resource behavior: create new
- Planned service: `cirvanna-catalog-staging-qmrw`
- Plan: free web service, Frankfurt
- Required manual environment value: `CATALOG_DATABASE_URL`

The Blueprint plan succeeded. It has **not** been approved or applied. The Neon runtime connection string was not written to GitHub. Deployment remains pending secure entry of the database URL through the Render Dashboard or an approved secret-entry path.

## Database and provider state

- Neon project `cirvanna-catalog-staging` is PostgreSQL 17 in Frankfurt. The catalog runtime database and least-privilege role exist.
- A staging restore branch was created from a manual snapshot and structural checks passed for the catalog/commerce databases and decision receipt store. This is not a production restore exercise.
- Neon snapshot schedule for the default branch is empty; instant-restore history is six hours. No RPO/RTO claim is made.
- Supabase `cirvanna-staging` is ACTIVE_HEALTHY. The security advisor returned zero lints. Identity, Twin and BFF private-schema migrations are present. Dedicated LOGIN service credentials and real application access tests remain outstanding.
- Stripe account is confirmed test mode (`livemode=false`). No product, Checkout Session, or webhook endpoint exists yet. No live-mode operation was performed.

## Remaining acceptance work

1. Apply the reviewed Render Blueprint after the database secret is entered securely.
2. Verify deployed service health, exact image digest and revision.
3. Run public-network negative/positive bearer tests for every Catalog route and abuse/rate-limit tests.
4. Connect the remaining private services and Decision Gateway using dedicated service credentials; do not expose internal service tokens to browsers.
5. Run deployed identity/session, PNELLY/Wardrobe, Twin, CAL cross-surface, Click It/Look It and commerce acceptance suites.
6. Complete Stripe test checkout, signed/invalid/duplicate webhook tests and reconciliation.
7. Configure scheduled backups, execute isolated restore and rollback drills, and measure RPO/RTO.
8. Obtain independent privacy/security and model/evidence assessments.
9. Re-evaluate every release gate against the exact deployed commit and immutable image digests.

No release-gate status or `verified_commit` is promoted by this evidence.
