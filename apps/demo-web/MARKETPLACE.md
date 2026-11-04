# Marketplace vertical slice

**Status: implementation candidate; not production-ready.**

This is a small, dependency-free browser surface built from the uploaded `Marketplace .txt` patterns: searchable product cards, category filtering, saved items, bag interactions, and honest capability boundaries. It reuses Cirvanna's dark/cream/gold visual direction.

## Open the interface

Open `marketplace.html` in a browser for a clearly labeled demo-data experience. Demo records are synthetic and must not be treated as actual merchant inventory or offers.

## Connect the canonical catalog API

Use **Connect catalog** and provide:

- The deployed catalog service base URL (the root URL, not `/products`).
- A bearer token accepted by that service.

The page calls `GET /products?q=&category=&status=active&limit=20&offset=0` using the catalog API's existing response shape (`items`, `total`, `offset`, `limit`). The current service does not support `status=active` as a necessary parameter because active is its default. The token remains in page memory only; it is not written to browser storage. Do not use production credentials on a public/shared device.

Configure `CATALOG_CORS_ORIGINS` on the API as a comma-separated list of exact trusted frontend origins (for example `https://shop.example.com`). The service does not enable cross-origin access unless this is configured; do not use `*`. The page blocks bearer-token transmission to non-HTTPS URLs, except localhost HTTP for development. Never put a privileged catalog token into a public static deployment. For a public release, add a same-origin backend-for-frontend that authenticates users and keeps service credentials server-side.

## Current behavior and boundaries

- Search and category filtering use the catalog API when connected; demo data is shown only when no API connection is configured.
- A live API failure is shown as an error; it does not silently replace live results with sample records.
- Saved items and bag contents are stored in this browser's local storage. They are not synced across devices and are not a durable account/cart implementation.
- The bag does not reserve stock, create an order, calculate shipping/tax, or initiate payment.
- Checkout and virtual try-on are intentionally unavailable. No fit analysis, CaTaCaCi decision, AI ranking, Click It reconstruction, or Virtual Twin output is fabricated.
- Images are rendered only from catalog-provided HTTP(S) URLs; the catalog API validates these as metadata but does not proxy or verify remote image content.

## Validation still required

A GitHub Actions workflow runs static contract checks, headless Chromium browser smoke tests, JavaScript syntax validation, and Python syntax compilation. The browser suite covers demo search, saving, bag interactions, disabled checkout/try-on boundaries, and rejection of insecure remote API URLs. Before merge/release, still run a live authenticated catalog/CORS smoke test against a non-production deployment, plus the catalog service test suite from `services/catalog-service`:

```bash
python -m pip install -r requirements.txt
pytest -q
```

Also verify the API's `/ready` endpoint, CORS behavior, authentication failures, product pagination, image failures, mobile layout, keyboard navigation, and the configured currency/price-unit convention. The UI formats prices using `Intl.NumberFormat` currency fraction-digit rules, so currencies with zero or three decimal places are not forced into a two-decimal display. The API currently validates a three-letter currency code, not a full currency metadata registry; merchant feeds still need a canonical ISO 4217 validation policy.

Do not merge or deploy until the HTML/JavaScript has been checked in a browser and the catalog integration is tested against a non-production environment.


## Authenticated service-owned portals

The Brand Partner Portal and Founder Console are served by the Marketplace BFF:

- `/brand-portal` — merchant application, catalog product linking, variants, stock adjustments and seller-scoped orders.
- `/founder-console` — administrator merchant review, verification-reference capture, decision history and inventory integrity audit.

They use Commerce's existing merchant and admin APIs. The browser holds the signed access token in memory only. Commerce authenticates and authorizes every operation; UI visibility is not an authorization control.

The portal intentionally omits product creation (Catalog owns product identity), image ingestion, analytics not provided by the API, automated KYC, payment execution, virtual try-on and AI/model operations. Commission values are basis points. Variant prices are converted to ISO currency minor units using `Intl.NumberFormat` currency precision.
