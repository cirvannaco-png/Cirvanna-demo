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

## Marketplace filters

The collapsed **Refine results** panel exposes brand/merchant, currency, minimum/maximum price, color, size, material, style, occasion, finish, shade, catalog skin-concern tags, and sorting (newest or price ascending/descending). Apply runs the current search; Clear all resets both basic and advanced filters.

The same query contract is passed to the appropriate server path:
- `services/catalog-service`: `/products`
- `services/marketplace-bff`: `/api/commerce/marketplace/offers`
- `services/commerce-service`: `/marketplace/offers`

Supported optional query parameters are `brand`, `currency`, `min_price_minor`, `max_price_minor`, `color`, `size`, `material`, `style`, `occasion`, `finish`, `shade`, `skin_concern`, `attribute_key`, `attribute_value`, and `sort_by` (`newest`, `price_low`, or `price_high`). Filtering occurs server-side before pagination in catalog/commerce services. The demo-only mode applies equivalent metadata matching in the browser against clearly labelled synthetic records.

The additional **More characteristics** selector and value field provide a compact extension point for ingredient tags, texture/hydration/pigmentation/redness tags, routine compatibility, undertone/foundation match, makeup intensity, hair color/hairstyle, silhouette/fit, color palette, climate, cultural context, accessibility, durability, delivery-region tags, ethical preferences, mood, desired impression, season, formality, and preparation-time tags. Dynamic filters require both a supported `attribute_key` and non-empty `attribute_value`. Backend services validate the key against a fixed allowlist before querying JSON metadata; arbitrary field names are rejected.

Prices are integer minor units. A currency must be selected whenever price bounds or price sorting are used; requests mixing currencies are rejected rather than comparing unlike monetary values. Browser inputs are converted to minor units using the selected currency's `Intl.NumberFormat` precision; values with unsupported fractional precision or beyond the API's supported price range are rejected instead of silently rounded. Price sort uses the selected currency's results only.

Attribute filters match catalog `attributes` or merchant variant `options` metadata, using case-insensitive substring matching. Unknown/missing metadata does not satisfy a requested attribute filter. These are discovery filters only: a `skin_concern` tag is not clinical evidence, ingredient-safety assessment, or a suitability verdict. Filters never authorize results to display; any personalized or sensitive recommendation must still pass the existing CAL/NPL/evidence and authorization path.

## Current behavior and boundaries

- Search, category and advanced metadata filters are sent to the live catalog/approved Commerce offers API when connected; demo data is shown only when no API connection is configured.
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
