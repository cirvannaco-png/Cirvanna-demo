# Cirvanna Marketplace BFF

**Status: deployable integration boundary; production remains gated on verified upstream services and identity-provider integration.**

This is the server-side browser boundary for marketplace browsing, visual discovery and the authenticated personal Wardrobe UI. It serves the marketplace UI, proxies public offers, forwards allowlisted account operations, routes natural-language search and consented Look It reference search to PNELLY, and exposes a request-scoped Complementer advisory through the verified Decision Gateway, and stops Click It at the BFF boundary until verified masking and publication attestation are released. It does not issue identities, hold user tokens in storage, bypass Commerce authorization, or invent fit/try-on results.

## Why this boundary exists

- No Catalog or Commerce service credential is embedded in the marketplace page. Catalog secrets remain in Catalog/Commerce service environments; the BFF uses only configured upstream URLs.
- The browser defaults to GET /api/commerce/marketplace/offers. Commerce returns only active offers from approved merchants with stock available.
- `POST /api/vision/marketplace-search` forwards a bounded written description/category/limit to PNELLY using its paired server-side credentials. XARI_* and TARI_* remain legacy fallback aliases; no assistant secret is exposed in browser JavaScript.
- `POST /api/vision/look-it` first derives the subject from the signed Commerce session before parsing multipart data. It then validates one bounded reference file, creates a short-lived Identity `image_processing` + `look_it` consent bundle bound to one request resource, verifies the exact subject/bundle/resource/scopes/expiry, reads and forwards the reference to PNELLY, then revokes the whole request bundle. The UploadFile is closed at request completion; no durable image asset is created. If cleanup fails, the BFF suppresses the search result. It returns only candidate counts and validated outfit-component descriptions; product/offer details remain withheld pending CAL.
- `POST /api/vision/click-it` validates the signed-user/consent assertions, closes the upload without reading its bytes, and returns a private no-store 503 until the masking and resource-bound privacy-attestation pipeline is released. No photo is forwarded to Virtual Twin or Vision Intelligence.
- `/api/wardrobe/outfits` lists and creates saved looks; piece-level add/replace/remove operations are proxied to the Wardrobe service. The BFF derives the owner from Commerce `/me`, generates outfit/slot identifiers, and rejects cross-subject responses.
- `/api/style/color-profile` reads and writes the user's structured liked/disliked/best-version colour preferences through USI/TAL. The BFF derives the subject from Commerce `/me`; profile-storage consent is enforced by Identity Learning. The route does not perform objective complexion or undertone analysis.\n- Account operations require the user's bearer token and are forwarded to Commerce. Commerce remains responsible for signature, issuer, audience, role, ownership, stock, checkout and payment validation.
- Only customer cart, saved-product, checkout and order routes are proxied. Admin, merchant-management, webhooks, cron, and internal endpoints are not exposed through this gateway.
- No CORS allowlist is added to this same-origin UI/API. Security headers include CSP, nosniff, no-referrer, frame denial, and disabled camera/microphone/geolocation.

## PNELLY Complementer feedback

- `POST /api/vision/complementer` derives the customer subject through Commerce `/me` and forwards the user token separately to the Decision Gateway. The result is advisory-only and contains no CAL display authorization or product offer.
- `POST /api/vision/complementer/feedback` requires a currently active, subject-owned Identity Learning `personalization` receipt. The BFF forwards an opaque request ID and the explicit `approved`/`rejected` reaction to `/v1/me/tal/events` using the same verified user session.
- The TAL value deliberately excludes the raw look description. It is retained as a private, idempotent learning observation with a 180-day event expiry.
- A durable TAL event is not automatically a changed USI/NPL preference or a CIL suitability outcome. A downstream, reviewed learning consumer must be implemented and validated before feedback changes recommendation ranking. CIL suitability ingestion still requires its own purpose-bound consent and candidate-bound CAL SHOW receipt.

## Partner portal boundary

- /brand-portal currently serves the merchant/seller onboarding and Commerce workspace. It is not a separate brand-owner tenant system.
- A dedicated distributor tenant, authorization graph and /distributor-portal are not implemented. Do not reuse a merchant role or grant distributor access from a brand-name field.
- The required organization/membership model, brand/distributor authorization relationships, tenant-scoped analytics and cross-tenant acceptance tests are specified in docs/architecture/brand-and-distributor-portals.md. Release gate REL-19 remains blocked until these APIs, portals and staging tests are delivered.

## Runtime configuration

Set through the deployment secret manager:

- CATALOG_API_URL: deployed canonical Catalog API base URL.
- COMMERCE_API_URL: deployed Commerce API base URL.
- MARKETPLACE_HTML_PATH: optional path override for a nonstandard container layout.
- PNELLY_API_URL and PNELLY_API_TOKEN: preferred paired assistant endpoint and bearer token. XARI_API_URL / XARI_API_TOKEN and TARI_API_URL / TARI_API_TOKEN remain compatibility fallbacks. A PNELLY URL never borrows an Xari/Tari token.

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

Click It stays unavailable until the verified face-masking processor, resource-bound consent verifier, independent asset-bound privacy attestation, publication gate, and pinned Vision Intelligence model assets are deployed/configured. The current BFF closes uploads before reading or forwarding bytes; an HTML checkbox is not proof of durable consent. Candidate products remain hidden unless the response is authorized for display by the real CAL decision gateway.

A working proxy does not create a production marketplace by itself. The actual Cirvanna identity provider and token/session flow must be integrated in place of manual test-token entry. Real PostgreSQL migrations, backups/restores and concurrency checks, Stripe test-mode checkout/webhook/reconciliation, shipping/tax policy, refunds/returns, seller payouts and fulfilment, rate limits/alerts, privacy deletion/retention, and live origin/credential smoke tests remain explicit release gates. The marketplace must keep showing account/checkout and AI/try-on features as unavailable until those integrations are verified.

PNELLY's description and Look It responses contain candidate matches, not display authorization. Look It image bytes are not persisted by the BFF/Xari/Vision code paths; an optional external outfit-decomposition provider remains disabled unless its model/report pins and separate privacy-approval digest are configured and provider operation/retention are independently reviewed. The marketplace must apply the canonical decision flow before showing candidate product details. Offer-price comparison belongs to the Catalog/Commerce offer layer: the assistant must never generate merchant names, prices, currencies, stock or shipping estimates.