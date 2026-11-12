# Cirvanna marketplace production release runbook

**Release status: BLOCKED — deployable code and CI coverage are not a substitute for live identity, database, payment and operating evidence.**  
Last in-repository validation is tracked by the GitHub Actions workflows on the marketplace feature branch. This document is the required promotion record, not a claim that staging or production checks have already been executed.

The machine-readable release ledger is [docs/release/release-gates.json](release/release-gates.json). All sixteen required gates currently initialize as `blocked`. Keep the ledger and this runbook aligned; a gate can be changed to `passed` only with reviewable evidence tied to the exact full release commit. Run `python scripts/validate_release_gates.py --require-all-passed` as the final release gate. Ordinary CI only validates code and registry structure; it does not close operational gates.

## 1. Deployment topology

Use the server-side Marketplace BFF as the only public browser origin:

- **Marketplace BFF** serves `apps/demo-web/marketplace.html`, injects a same-origin `/api/commerce` base, and proxies only public in-stock offers plus an allowlist of customer account routes. Its runtime image build context is the repository root.
- **Catalog service** is the canonical product identity and metadata API. The Catalog image build context is `services/catalog-service`.
- **Commerce service** owns merchant applications/offers, variants, inventory reservations, cart, orders, checkout and payment webhook state. Its image build context is `services/commerce-service`.
- **Decision Gateway** is the private policy authority for candidate-bound marketplace display and purchase-action decisions; do not expose its API publicly. Commerce must reach it over trusted HTTPS in deployed environments. The separate Decision service remains private as well.
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
- `DECISION_GATEWAY_URL` and `DECISION_GATEWAY_TOKEN` for the private Decision Gateway, plus `CAL_PURCHASE_RECEIPT_HMAC_SECRET` (at least 32 random bytes) shared only by Commerce and the Decision Gateway; never expose these values to the browser or merchants
- real Stripe test-mode credentials from the secret manager for staging: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, valid HTTPS `COMMERCE_CHECKOUT_SUCCESS_URL`, `COMMERCE_CHECKOUT_CANCEL_URL`, and permitted `COMMERCE_SHIPPING_COUNTRIES`; use production credentials only in the production secret manager after the release decision
- a random high-entropy `COMMERCE_CRON_TOKEN` for the restricted stock-reservation expiry endpoint
- exact allowed origins in `COMMERCE_CORS_ORIGINS` only where a supported browser directly calls Commerce. The production storefront should normally use the BFF same-origin routes.

**Identity remains a promotion gate:** this repository validates OIDC RS256/JWKS access tokens but does not implement the actual Cirvanna sign-in/session lifecycle. The chosen identity provider must issue tokens with the configured issuer/audience and trusted role claim, and a real browser login/refresh/logout flow must be integrated and tested. Do not ask shoppers to paste JWTs into a production storefront. Production HS256 mode is intentionally rejected.

### Marketplace BFF secrets

Configure `CATALOG_API_URL` and `COMMERCE_API_URL` using deployed HTTPS endpoints. Keep `COMMERCE_CAL_PURCHASE_PROXY_ENABLED=false` by default. The BFF `/ready` endpoint must report the Catalog and Commerce upstreams ready before the service receives live traffic. For protected cart reads/adds/updates and checkout, the BFF additionally requires the operator flag to be explicitly `true`, checks Commerce `/ready` for the CAL Gateway, receipt signer and current migrations, and checks `/capabilities` for `candidate_bound_purchase_authorization_configured=true` on every protected request. Missing or unhealthy evidence returns `503 CAL_CANDIDATE_PURCHASE_REAUTH_REQUIRED`; no request is forwarded. Enable the flag only in an isolated staging environment after the private Decision Gateway and signing secret are verified. Keep direct service admin, merchant-management, webhook and internal endpoints unreachable from public routing.

## 3. Apply migrations and prove recovery

1. Take an initial encrypted backup / database snapshot before schema changes.
2. In the same release image and environment as the target service, run `alembic upgrade head` from `services/catalog-service` with `CATALOG_DATABASE_URL` set; then do the same in `services/commerce-service` with `COMMERCE_DATABASE_URL`.
3. Confirm `alembic_version.version_num` is `20261104_0002` for Catalog and `20261110_0010` for Commerce on this release branch. Do not enable automatic `create_all` in production. Commerce `20261109_0007` establishes the multi-market provider-evidence schema; `20261109_0008` adds zone-bound tax evidence, landed-cost order snapshots and charge persistence; `20261110_0009` adds the optional consent receipt binding for checkout learning; `20261110_0010` adds append-only candidate-bound CAL purchase-authorization audits. The ported APIs implement market declarations, quote ingestion contracts, localized offers, offer comparison and market-aware checkout, but do not connect or operationally verify the external FX, tax, fulfilment or payment providers.
4. Run and retain a backup restore drill to a clean, isolated database. Verify row counts, constraints, order/payment state and inventory invariants after restoration.
5. Verify database connections and `/ready` for Catalog and Commerce return HTTP 200 only after schema, migration and mandatory configuration are all valid. Confirm they return 503 when a migration or required secret is missing.

## 4. Candidate-bound CAL purchase authorization (PRs #192 and #193)

Cart and checkout are separate authorization surfaces from marketplace display. A previous SHOW decision does not authorize adding an offer to a cart, viewing an existing cart line, changing its quantity, or creating a payable order.

### Staging enablement sequence

1. Deploy the exact candidate images for Commerce, Decision Gateway and Marketplace BFF to an isolated non-production environment. Record the Git commit and immutable image digests.
2. Apply Commerce migration `20261110_0010` after `20261110_0009`. Confirm the `commerce_cal_purchase_audits` table exists and is append-only under the Commerce database role. Back up and restore the staging database before using it for checkout tests.
3. Configure Commerce with private HTTPS `DECISION_GATEWAY_URL`, `DECISION_GATEWAY_TOKEN` (at least 32 bytes), and `CAL_PURCHASE_RECEIPT_HMAC_SECRET` (at least 32 random bytes). Configure the same dedicated HMAC secret in the Decision Gateway. It must not be reused for JWT signing or any other purpose. Configure the Decision Gateway's trusted Commerce identity resolution so it can independently resolve the end-user bearer.
4. Confirm Commerce `/ready` reports database/schema readiness, reachable Decision Gateway and receipt signer configuration. Confirm Commerce `/capabilities` reports `candidate_bound_purchase_authorization_configured=true`.
5. Leave `COMMERCE_CAL_PURCHASE_PROXY_ENABLED=false` first. Verify the BFF rejects authenticated `GET /api/commerce/cart`, `POST /api/commerce/cart/items`, `PATCH /api/commerce/cart/items/{variant_id}` and `POST /api/commerce/checkout` with `503 CAL_CANDIDATE_PURCHASE_REAUTH_REQUIRED`. Verify no upstream Commerce request is made. Also verify a missing/invalid user bearer is rejected with `401` before the BFF probes Commerce readiness.
6. Only after the previous checks pass, set `COMMERCE_CAL_PURCHASE_PROXY_ENABLED=true` in the staging BFF environment. Do not change the production value. The BFF rechecks readiness and capabilities for every protected request; this flag is an operator gate, not a substitute for Commerce receipt validation.
7. Use a real staging customer identity token issued by the configured OIDC provider. Do not use the marketplace page's manual test-token field as a production sign-in/session implementation. That UI field is a development/testing bridge; production still requires provider-backed browser login, refresh and logout.

### Positive and negative transaction checks

- Discover one approved, in-stock staging offer through the authenticated BFF. Confirm only candidates with CAL SHOW and `may_display=true` are returned.
- Add that exact variant to the cart. Verify Commerce obtains a fresh `cart_add` receipt bound to the authenticated subject, product, variant, listing, merchant, exact offer snapshot, quantity and price; confirm one successful audit row is persisted.
- Read the cart. Verify every existing line is reauthorized with `cart_view`; a denied or stale receipt must suppress the line response and fail the request closed.
- Change quantity. Verify a separate `cart_update` receipt is required and the exact offer/quantity snapshot is revalidated after the Decision Gateway round-trip.
- Attempt checkout with a fresh `checkout` receipt for every exact line snapshot. Verify purchase-audit rows are committed in the same database transaction as the order, immutable order lines and inventory reservations. Check idempotent retry requires a matching successful audit for every line.
- Mutate or invalidate the offer between authorization and commit (price, merchant/listing, variant state/version, quantity, stock, Catalog version or market quote). The mutation must fail and require new user-directed authorization; it must not silently reuse an earlier receipt.
- Return BLOCK, REVIEW, expired receipt, wrong subject, changed offer hash, wrong action, wrong Catalog version, invalid HMAC, missing signer, unreachable Decision Gateway and stale schema in controlled staging fixtures. Each must fail closed and must not leak candidate details or create an order/stock reservation.
- Cart-line deletion remains available as a cleanup path; test it separately and confirm it cannot create an order or payment session.

### Stripe test-mode completion

Use an approved staging merchant with Stripe test-mode credentials only. Verify checkout creates a hosted Stripe Checkout Session with the expected order ID, integer minor-unit amount and currency. Complete the payment using Stripe's documented test payment method in the hosted test session. Then verify:

- webhook signature validation rejects a modified/unsigned payload;
- duplicate delivery of the same Stripe event is idempotent and does not double-settle or double-reserve;
- the paid state is created only after verified webhook processing, not after the browser redirect;
- the webhook amount/currency match the immutable Commerce order and line/charge snapshots;
- the authorization audit rows remain linked to the exact order/cart version/line snapshots;
- the Commerce outbox event is delivered or safely retried, and the Sync/Wardrobe consumer deduplicates by event ID;
- expired sessions release reservations only after Stripe confirms expiry; ambiguous provider outcomes remain reserved for reconciliation.

For the initial card-only smoke test, do not pass a personalization consent receipt unless the Identity Learning consent path is deliberately under test. With no consent receipt, checkout may proceed but no preference-learning observation may be emitted. PayPal and bank rails are not part of this implementation.

Record redacted request IDs, order ID, cart version, CAL decision reference and policy version, audit row IDs, Stripe test session/event IDs, webhook delivery/replay results, final order totals and reservation state. Never copy bearer tokens, HMAC receipts/secrets, card details, customer PII or raw delivery addresses into the evidence artifact.

## 5. Multi-market integration boundary

PR #102's historical migration files are not used: their `20261105_0004` and `20261105_0005` identifiers conflict with the current migration lineage. The current integration adds `20261109_0008` after `20261109_0007`. It binds tax quotes to the exact destination_key and supports offer prices in different source currencies only when fresh provider FX exists for the item, fulfilment and tax components. It requires the same canonical Catalog product and canonical variant, same destination zone, compatible tax jurisdiction/category/basis, active destination-market capability and card payment capability.

The code and schema do not establish external provider readiness. Until operation-specific staging evidence exists, offers whose required FX, fulfilment, tax or payment evidence is missing, stale, mismatched or untrusted remain unavailable. Production activation still requires real provider integration and end-to-end staging verification.

## 6. Release and staging acceptance tests

Run these against staging with real provider/test-mode credentials before enabling a production domain:

- Anonymous browse returns only active offers from approved merchants with stock available; search, category filter and pagination return the expected records. Live API failures must stay visible and never fall back to demo/sample records.
- Test the OIDC authorization/login/session path with real provider-issued customer, merchant and admin tokens. Verify expiry, wrong issuer, wrong audience, unknown/rotated signing key, revoked/disabled session policy, and that customer tokens cannot call merchant/admin routes.
- Verify Catalog read token can read but cannot create/update/archive. Verify Catalog write token can mutate but cannot be used as a read token; verify production refuses a shared read/write secret.
- Confirm the BFF purchase gate is initially off and all four protected cart/checkout routes fail closed without forwarding. Enable it only in staging after Commerce `/ready`, `/capabilities`, migration `20261110_0010` and the shared dedicated HMAC secret are verified.
- Exercise candidate-bound `cart_add`, `cart_view`, `cart_update` and `checkout` receipts through the actual BFF and Commerce services. Check subject/action/offer/quantity/price/Catalog-version binding, durable `commerce_cal_purchase_audits`, changed-offer rejection and no order or reservation on BLOCK/REVIEW/invalid/expired receipts.
- Create a hosted Stripe test checkout. Check order amount/currency, Stripe metadata, idempotency, inventory reservation, failed checkout behavior, duplicate webhook replay, webhook signature rejection, confirmed-paid transition and expiry/reconciliation. A checkout redirect is not proof of payment.
- Run the reservation-expiry job on a schedule with its dedicated secret; verify it releases stock only for Stripe sessions confirmed expired and leaves ambiguous payment outcomes reserved for reconciliation.
- Verify merchant application and human KYC decision workflow with explicit approval reference; test suspended merchant listings are not visible and stock cannot be oversold under concurrent checkout.
- Verify HTTPS, CSP/security headers, no wildcard CORS, rate limits, secrets redaction, structured logs, error/latency alerts, privacy deletion/retention, support/refund procedures and an incident/rollback drill.

Retain the exact candidate commit, CI links, migration output, database restore evidence, redacted request IDs, Stripe test session/webhook logs and staging smoke-test report as the release artifact.

## 7. Cirvanna vision modules that must not be advertised as live

The current repository does not certify these end-to-end: **TARI**, **CRFP** marketplace and system-wide scopes (scope ownership is documented, but authoritative runtime contracts and implementations remain unverified), trained/calibrated **FCI** fit inference, personalized NPL/USI evaluation on real user data, **CaTaCaCi** arbitration wired into storefront display suppression, **Click It** reconstruction, **Virtual Twin** geometry or real virtual try-on rendering. The deterministic EEPL/NPL/USI/FCI-evidence/CAL contract tests are not proof those production integrations and underlying models exist. Keep each capability visibly unavailable until its own provider, evaluation corpus, policy, authorization, latency/failure and user-consent gates are evidenced.

## 8. Promotion decision

Do not merge/deploy to production until all of the following are recorded as passed in [the release evidence ledger](release/release-gates.json), with artifacts reviewed against the exact candidate commit:

- [ ] All required GitHub Actions workflows pass for the exact merge candidate commit.
- [ ] Paid production infrastructure budget/region and service ownership are approved and resources are provisioned.
- [ ] Catalog/Commerce migrations, backup/restore and database-backed readiness are verified against managed PostgreSQL.
- [ ] Real OIDC identity provider and browser sign-in/session flow are integrated; production HS256 is not used.
- [ ] Commerce migration `20261110_0010` and append-only CAL purchase audits are verified on managed PostgreSQL; the staging BFF gate is proven fail-closed by default and only enabled after Decision Gateway readiness/signature checks.
- [ ] Candidate-bound cart read/add/update/checkout receipts and durable audits pass against real staging Commerce + Decision Gateway; offer mutation and gateway failure cases reject without order or reservation.
- [ ] Stripe test-mode checkout/webhook/reconciliation and stock-expiry job pass; production keys are configured through secret storage.
- [ ] Approved merchant applications, real catalog data and inventory are present and independently reviewed.
- [ ] Security, observability, rate limiting, privacy, refunds/returns, fulfilment, shipping/tax and seller payout operating procedures are approved.
- [ ] Product owners explicitly sign off on whether TARI, NPL, marketplace/system-wide CRFP, CaTaCaCi, Click It, Virtual Twin and try-on are launch blockers or clearly out-of-scope for the initial commerce launch.
- [ ] Staging end-to-end evidence is attached to the PR; rollback and on-call owners are identified.

Until then, the accurate status is **engineering candidate with passing automated CI—not production-ready**.


## PNELLY Look It and Click It separation

Look It is a user-supplied outfit-reference search. Its BFF route records and verifies a short-lived, exact-resource Identity consent bundle, PNELLY independently re-verifies the bundle, and Vision performs transient image-to-Catalog-text retrieval. The browser receives only aggregate candidate counts and optional validated outfit-component descriptions; no product/merchant/price/image data is returned until CAL SHOW. External outfit decomposition remains unavailable unless its model/report and separate privacy approval are pinned and the provider's retention and operational behavior are independently reviewed.

Click It is not a fallback route for Look It. Click It remains disabled before multipart parsing until verified masking, photographed-person rights, child safeguards and complete public publication-route coverage pass. The two routes have distinct consent scopes and release gates (REL-18 and REL-14).
