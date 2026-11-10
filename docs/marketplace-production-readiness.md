# Cirvanna marketplace production release runbook

**Release status: BLOCKED — deployable code and CI coverage are not a substitute for live identity, database, payment and operating evidence.**  
Last in-repository validation is tracked by the GitHub Actions workflows on the marketplace feature branch. This document is the required promotion record, not a claim that staging or production checks have already been executed.

The machine-readable release ledger is [docs/release/release-gates.json](release/release-gates.json). All sixteen required gates currently initialize as `blocked`. Keep the ledger and this runbook aligned; a gate can be changed to `passed` only with reviewable evidence tied to the exact full release commit. Run `python scripts/validate_release_gates.py --require-all-passed` as the final release gate. Ordinary CI only validates code and registry structure; it does not close operational gates.

## 1. Deployment topology

Use the server-side Marketplace BFF as the only public browser origin:

- **Marketplace BFF** serves `apps/demo-web/marketplace.html`, injects a same-origin `/api/commerce` base, and proxies only public in-stock offers plus an allowlist of customer account routes. Its runtime image build context is the repository root.
- **Catalog service** is the canonical product identity and metadata API. The Catalog image build context is `services/catalog-service`.
- **Commerce service** owns merchant applications/offers, variants, inventory reservations, cart, orders, checkout and payment webhook state. Its image build context is `services/commerce-service`.
- **Decision service** is a separately protected internal endpoint; do not expose its interactive API publicly. It is not yet an end-to-end marketplace display gate.
- Use managed PostgreSQL for Catalog and Commerce. Keep data domains separate; do not use SQLite or ephemeral service storage for shared/production data. Keep a separate restore-tested backup path for each database.

The connected Render workspace was inspected on 2026-10-19 and did not contain a Cirvanna service or a Cirvanna PostgreSQL instance. No Cirvanna production service has been deployed by this release branch. Do not reuse a database belonging to another project.

## 2. Provision and configure infrastructure

Provision production-grade managed PostgreSQL and non-free, non-ephemeral web-service instances in the approved region and budget. Before apply, record the service IDs, database IDs, plan/region, recovery owner, target RPO/RTO and alert recipient. This repository does not select a paid plan or incur infrastructure costs on behalf of the account owner.

### Catalog secrets

Configure in the secret manager, never in the frontend or Git:

- `CATALOG_ENVIRONMENT=production`
- `CATALOG_DATABASE_URL` pointing to the managed Catalog PostgreSQL instance
- `CATALOG_AUTO_CREATE_SCHEMA=false`
- distinct, high-entropy `CATALOG_READ_TOKEN` and `CATALOG_WRITE_TOKEN`

The Commerce service receives the Catalog **read token only**, configured in its own service environment as `CATALOG_API_TOKEN`. The Catalog production guard rejects missing or identical read/write credentials. Do not expose either token to browser JavaScript. The BFF needs the Catalog URL for its readiness cross-check, not a Catalog token.

### Commerce secrets

Configure in the Commerce secret manager:

- `COMMERCE_DATABASE_URL` pointing to managed Commerce PostgreSQL; `COMMERCE_AUTO_CREATE_SCHEMA=false`
- `COMMERCE_ENVIRONMENT=production` and `COMMERCE_AUTH_MODE=oidc_jwks`
- `COMMERCE_JWT_JWKS_URL`, exact `COMMERCE_JWT_ISSUER`, exact `COMMERCE_JWT_AUDIENCE`, and trusted `COMMERCE_JWT_ROLE_CLAIM`
- `CATALOG_API_URL` and `CATALOG_API_TOKEN` set to Catalog's HTTPS URL and **read-only** token
- real Stripe credentials from the secret manager: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, valid HTTPS `COMMERCE_CHECKOUT_SUCCESS_URL`, `COMMERCE_CHECKOUT_CANCEL_URL`, and permitted `COMMERCE_SHIPPING_COUNTRIES`
- a random high-entropy `COMMERCE_CRON_TOKEN` for the restricted stock-reservation expiry endpoint
- exact allowed origins in `COMMERCE_CORS_ORIGINS` only where a supported browser directly calls Commerce. The production storefront should normally use the BFF same-origin routes.

**Identity remains a promotion gate:** this repository validates OIDC RS256/JWKS access tokens but does not implement the actual Cirvanna sign-in/session lifecycle. The chosen identity provider must issue tokens with the configured issuer/audience and trusted role claim, and a real browser login/refresh/logout flow must be integrated and tested. Do not ask shoppers to paste JWTs into a production storefront. Production HS256 mode is intentionally rejected.

### Marketplace BFF secrets

Configure `CATALOG_API_URL` and `COMMERCE_API_URL` using deployed HTTPS endpoints. The BFF `/ready` endpoint must report both upstreams ready before the service receives live traffic. Keep direct service admin, merchant-management, webhook and internal endpoints unreachable from public routing.

## 3. Apply migrations and prove recovery

1. Take an initial encrypted backup / database snapshot before schema changes.
2. In the same release image and environment as the target service, run `alembic upgrade head` from `services/catalog-service` with `CATALOG_DATABASE_URL` set; then do the same in `services/commerce-service` with `COMMERCE_DATABASE_URL`.
3. Confirm `alembic_version.version_num` is `20261104_0002` for Catalog and `20261110_0009` for Commerce on this release branch. Do not enable automatic `create_all` in production. Commerce `20261109_0007` establishes the multi-market provider-evidence schema; `20261109_0008` adds zone-bound tax evidence, landed-cost order snapshots and charge persistence; `20261110_0009` adds the optional consent receipt binding for checkout learning. The ported APIs implement market declarations, quote ingestion contracts, localized offers, offer comparison and market-aware checkout, but do not connect or operationally verify the external FX, tax, fulfilment or payment providers.
4. Run and retain a backup restore drill to a clean, isolated database. Verify row counts, constraints, order/payment state and inventory invariants after restoration.
5. Verify database connections and `/ready` for Catalog and Commerce return HTTP 200 only after schema, migration and mandatory configuration are all valid. Confirm they return 503 when a migration or required secret is missing.

## 4. Multi-market integration boundary

PR #102's historical migration files are not used: their `20261105_0004` and `20261105_0005` identifiers conflict with the current migration lineage. The current integration adds `20261109_0008` after `20261109_0007`. It binds tax quotes to the exact destination_key and supports offer prices in different source currencies only when fresh provider FX exists for the item, fulfilment and tax components. It requires the same canonical Catalog product and canonical variant, same destination zone, compatible tax jurisdiction/category/basis, active destination-market capability and card payment capability.

The code and schema do not establish external provider readiness. Until operation-specific staging evidence exists, offers whose required FX, fulfilment, tax or payment evidence is missing, stale, mismatched or untrusted remain unavailable. Production activation still requires real provider integration and end-to-end staging verification.

## 5. Release and staging acceptance tests

Run these against staging with real provider/test-mode credentials before enabling a production domain:

- Anonymous browse returns only active offers from approved merchants with stock available; search, category filter and pagination return the expected records. Live API failures must stay visible and never fall back to demo/sample records.
- Test the OIDC authorization/login/session path with real provider-issued customer, merchant and admin tokens. Verify expiry, wrong issuer, wrong audience, unknown/rotated signing key, revoked/disabled session policy, and that customer tokens cannot call merchant/admin routes.
- Verify Catalog read token can read but cannot create/update/archive. Verify Catalog write token can mutate but cannot be used as a read token; verify production refuses a shared read/write secret.
- Create a cart and hosted Stripe test checkout. Check order amount/currency, Stripe metadata, idempotency, inventory reservation, failed checkout behavior, duplicate webhook replay, webhook signature rejection, confirmed-paid transition and expiry/reconciliation. A checkout redirect is not proof of payment.
- Run the reservation-expiry job on a schedule with its dedicated secret; verify it releases stock only for Stripe sessions confirmed expired and leaves ambiguous payment outcomes reserved for reconciliation.
- Verify merchant application and human KYC decision workflow with explicit approval reference; test suspended merchant listings are not visible and stock cannot be oversold under concurrent checkout.
- Verify HTTPS, CSP/security headers, no wildcard CORS, rate limits, secrets redaction, structured logs, error/latency alerts, privacy deletion/retention, support/refund procedures and an incident/rollback drill.

Retain the exact candidate commit, CI links, migration output, database restore evidence, redacted request IDs, Stripe test session/webhook logs and staging smoke-test report as the release artifact.

## 5. Cirvanna vision modules that must not be advertised as live

The current repository does not certify these end-to-end: **TARI**, **CRFP** marketplace and system-wide scopes (scope ownership is documented, but authoritative runtime contracts and implementations remain unverified), trained/calibrated **FCI** fit inference, personalized NPL/USI evaluation on real user data, **CaTaCaCi** arbitration wired into storefront display suppression, **Click It** reconstruction, **Virtual Twin** geometry or real virtual try-on rendering. The deterministic EEPL/NPL/USI/FCI-evidence/CAL contract tests are not proof those production integrations and underlying models exist. Keep each capability visibly unavailable until its own provider, evaluation corpus, policy, authorization, latency/failure and user-consent gates are evidenced.

## 6. Promotion decision

Do not merge/deploy to production until all of the following are recorded as passed in [the release evidence ledger](release/release-gates.json), with artifacts reviewed against the exact candidate commit:

- [ ] All required GitHub Actions workflows pass for the exact merge candidate commit.
- [ ] Paid production infrastructure budget/region and service ownership are approved and resources are provisioned.
- [ ] Catalog/Commerce migrations, backup/restore and database-backed readiness are verified against managed PostgreSQL.
- [ ] Real OIDC identity provider and browser sign-in/session flow are integrated; production HS256 is not used.
- [ ] Stripe test-mode checkout/webhook/reconciliation and stock-expiry job pass; production keys are configured through secret storage.
- [ ] Approved merchant applications, real catalog data and inventory are present and independently reviewed.
- [ ] Security, observability, rate limiting, privacy, refunds/returns, fulfilment, shipping/tax and seller payout operating procedures are approved.
- [ ] Product owners explicitly sign off on whether TARI, NPL, marketplace/system-wide CRFP, CaTaCaCi, Click It, Virtual Twin and try-on are launch blockers or clearly out-of-scope for the initial commerce launch.
- [ ] Staging end-to-end evidence is attached to the PR; rollback and on-call owners are identified.

Until then, the accurate status is **engineering candidate with passing automated CI—not production-ready**.


## PNELLY Look It and Click It separation

Look It is a user-supplied outfit-reference search. Its BFF route records and verifies a short-lived, exact-resource Identity consent bundle, PNELLY independently re-verifies the bundle, and Vision performs transient image-to-Catalog-text retrieval. The browser receives only aggregate candidate counts and optional validated outfit-component descriptions; no product/merchant/price/image data is returned until CAL SHOW. External outfit decomposition remains unavailable unless its model/report and separate privacy approval are pinned and the provider's retention and operational behavior are independently reviewed.

Click It is not a fallback route for Look It. Click It remains disabled before multipart parsing until verified masking, photographed-person rights, child safeguards and complete public publication-route coverage pass. The two routes have distinct consent scopes and release gates (REL-18 and REL-14).
