# Cirvanna Marketplace BFF

**Owner:** Same-origin browser gateway and static presentation delivery.  
**Runtime:** FastAPI / Uvicorn.

The BFF serves the public marketplace and the authenticated merchant/admin portals. Service credentials remain server-side; browser sessions send the signed user access token to Commerce, which remains the authorization authority.

## Routes

- `/` and `/marketplace.html` — public marketplace.
- `/brand-portal` — Brand Partner Portal.
- `/founder-console` — Founder Console.
- `/assets/*` — version-controlled static portal assets.
- `/api/commerce/marketplace/offers` — public approved, active, in-stock offers.
- `/api/commerce/*` — constrained allowlist of customer, merchant and founder operations.

## Security boundary

The portal stores the signed access token in page memory only; it does not write it to local or session storage. Authenticated requests use `credentials: omit`, `cache: no-store`, and do not forward cookies. The BFF allowlists exact Commerce routes and the Commerce service verifies customer, merchant ownership/approval and administrator roles on every request. Internal cron, payment webhook and other service-internal paths remain unavailable through the BFF.

The BFF does not create roles, perform KYC, create canonical catalog products, fabricate analytics, perform virtual try-on, expose raw buyer identity to sellers, or override CAL/other domain policy. Approval requires an external verification reference and trusted administrator. A fresh merchant-role token must be issued by the identity provider before seller operations can proceed.

## Configuration

- `COMMERCE_API_URL` — trusted Commerce service URL (HTTPS outside localhost development).
- `CATALOG_API_URL` — catalog service URL used by BFF readiness checks.
- `MARKETPLACE_HTML_PATH`, `BRAND_PORTAL_HTML_PATH`, `FOUNDER_CONSOLE_HTML_PATH` — HTML paths.
- `MARKETPLACE_ASSETS_DIR` — static assets directory.

Use exact origin allowlists on upstream services; do not put privileged service tokens in browser pages. Remote API overrides in the UI must use HTTPS.

## Validation

The BFF workflow runs API contract tests, portal/static asset smoke tests, Python compilation and JavaScript syntax checks. Commerce has its own test workflow and Alembic migration gate.
