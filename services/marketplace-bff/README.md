# Cirvanna Marketplace BFF

**Status: deployable integration boundary; production remains gated on verified upstream services and identity-provider integration.**

This is the server-side browser boundary for marketplace browsing, visual discovery and the authenticated personal Wardrobe UI. It serves the marketplace UI, proxies public offers, forwards allowlisted account operations, routes natural-language search to Xari, and forwards Click It photos to the private Virtual Twin API after deriving the user subject from Commerce's verified `/me` endpoint. It does not issue identities, hold user tokens in storage, bypass Commerce authorization, or invent fit/try-on results.

## Why this boundary exists

- No Catalog or Commerce service credential is embedded in the marketplace page. Catalog secrets remain in Catalog/Commerce service environments; the BFF uses only configured upstream URLs.
- The browser defaults to GET /api/commerce/marketplace/offers. Commerce returns only active offers from approved merchants with stock available.
- `POST /api/vision/marketplace-search` forwards a bounded written description/category/limit to Xari using a server-side token. It does not expose the Tari secret in browser JavaScript.
- `POST /api/vision/click-it` requires a signed Commerce user JWT, checks the user through `GET /me`, and forwards a size-bounded product photo to Virtual Twin with a server-side token. It never trusts a browser-supplied subject/user ID.
- `/api/wardrobe/outfits` lists and creates saved looks; piece-level add/replace/remove operations are proxied to the Wardrobe service. The BFF derives the owner from Commerce `/me`, generates outfit/slot identifiers, and rejects cross-subject responses.\n- Account operations require the user's bearer token and are forwarded to Commerce. Commerce remains responsible for signature, issuer, audience, role, ownership, stock, checkout and payment validation.
- Only customer cart, saved-product, checkout and order routes are proxied. Admin, merchant-management, webhooks, cron, and internal endpoints are not exposed through this gateway.
- No CORS allowlist is added to this same-origin UI/API. Security headers include CSP, nosniff, no-referrer, frame denial, and disabled camera/microphone/geolocation.

## Runtime configuration

Set through the deployment secret manager:

- CATALOG_API_URL: deployed canonical Catalog API base URL.
- COMMERCE_API_URL: deployed Commerce API base URL.
- MARKETPLACE_HTML_PATH: optional path override for a nonstandard container layout.
- XARI_API_URL and XARI_API_TOKEN: preferred private assistant endpoint and bearer token. Existing TARI_API_URL and TARI_API_TOKEN values remain supported as compatibility fallbacks during migration.

Non-local upstream URLs must use HTTPS without URL credentials, query strings or fragments. The /ready endpoint probes both upstream /ready endpoints and fails with HTTP 503 unless the catalog credential is configured and both services independently report ready. /health is liveness only.

## Run locally

From repository root:

    python -m pip install -r services/marketplace-bff/requirements.txt pytest
    cd services/marketplace-bff
    uvicorn app.main:app --host 127.0.0.1 --port 8083
    python -m pytest -q

Build the container from repository root:

    docker build -f services/marketplace-bff/Dockerfile -t cirvanna-marketplace-bff .

## Production release gates not solved by the BFF

Click It stays unavailable until the actual consent-verification service and pinned Vision Intelligence model assets are deployed/configured; an HTML checkbox is not accepted as proof of durable consent. Candidate products remain hidden unless the response is authorized for display by the real CAL decision gateway.

A working proxy does not create a production marketplace by itself. The actual Cirvanna identity provider and token/session flow must be integrated in place of manual test-token entry. Real PostgreSQL migrations, backups/restores and concurrency checks, Stripe test-mode checkout/webhook/reconciliation, shipping/tax policy, refunds/returns, seller payouts and fulfilment, rate limits/alerts, privacy deletion/retention, and live origin/credential smoke tests remain explicit release gates. The marketplace must keep showing account/checkout and AI/try-on features as unavailable until those integrations are verified.

Xari's search response contains candidate matches, not display authorization. The marketplace must apply the canonical decision flow before showing candidate product details. Offer-price comparison belongs to the Catalog/Commerce offer layer: the assistant must never generate merchant names, prices, currencies, stock or shipping estimates.