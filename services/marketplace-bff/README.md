# Cirvanna Marketplace BFF

**Status: deployable integration boundary; production remains gated on verified upstream services and identity-provider integration.**

This is the server-side browser boundary for marketplace browsing and visual discovery. It serves the marketplace UI, proxies public offers, forwards allowlisted account operations, routes natural-language search to Xari, and forwards Click It photos to the private Virtual Twin API after deriving the user subject from Commerce's verified `/me` endpoint. It does not issue identities, hold user tokens in storage, bypass Commerce authorization, or invent fit/try-on results.

## Why this boundary exists

- No Catalog or Commerce service credential is embedded in the marketplace page. Catalog secrets remain in Catalog/Commerce service environments; the BFF uses only configured upstream URLs.
- The browser defaults to GET /api/commerce/marketplace/offers. Commerce returns only active offers from approved merchants with stock available.
- `POST /api/vision/marketplace-search` forwards a bounded written description/category/limit to Xari using a server-side token. It does not expose the Xari secret in browser JavaScript.
- `POST /api/vision/click-it` requires a signed Commerce user JWT, checks the user through `GET /me`, and forwards a size-bounded product photo to Virtual Twin with a server-side token. It never trusts a browser-supplied subject/user ID.
- Account operations require the user's bearer token and are forwarded to Commerce. Commerce remains responsible for signature, issuer, audience, role, ownership, stock, checkout and payment validation.
- Only customer cart, saved-product, checkout and order routes are proxied. Admin, merchant-management, webhooks, cron, and internal endpoints are not exposed through this gateway.
- No CORS allowlist is added to this same-origin UI/API. Security headers include CSP, nosniff, no-referrer, frame denial, and disabled camera/microphone/geolocation.

## Runtime configuration

Set through the deployment secret manager:

- CATALOG_API_URL: deployed canonical Catalog API base URL.
- COMMERCE_API_URL: deployed Commerce API base URL.
- MARKETPLACE_HTML_PATH: optional path override for a nonstandard container layout.

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


## CAL display enforcement — current fail-closed behavior

The BFF currently does **not** have a verified candidate-bound CAL gateway contract that it can call for every product. Accordingly, the public offer endpoint returns `503 CAL_GOVERNANCE_NOT_ENFORCED`, and Xari/Click It responses are stripped of candidate details at the browser boundary and remain `PENDING_CAL`. This intentionally disables product display rather than trusting a retrieval service's `display_authorized` field. It is a containment step, not completion of purchase governance.

To restore display, implement and deploy a trusted server-side gateway that derives the authenticated user, loads current NPL and explicit cultural evidence, validates signed/calibrated fit evidence where required, invokes the decision service for each candidate, and returns only candidate-bound CAL `SHOW` results. BLOCK, REVIEW, missing/stale evidence, timeouts, malformed responses and gateway errors must remain non-displayable. Add live end-to-end tests before removing this guard.
