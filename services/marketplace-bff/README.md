# Cirvanna Marketplace BFF

**Status: deployable integration boundary; production remains gated on verified upstream services and identity-provider integration.**

This is the server-side browser boundary for marketplace browsing, visual discovery and the authenticated personal Wardrobe UI. It serves the marketplace UI, proxies public offers, forwards allowlisted account operations, routes natural-language search and consented Look It reference search to PNELLY, and exposes a request-scoped Complementer advisory through the verified Decision Gateway, and stops Click It at the BFF boundary until verified masking and publication attestation are released. It does not issue identities, hold user tokens in storage, bypass Commerce authorization, or invent fit/try-on results.

## Why this boundary exists

- No Catalog or Commerce service credential is embedded in the marketplace page. Catalog secrets remain in Catalog/Commerce service environments; the BFF uses only configured upstream URLs.
- The browser defaults to GET /api/commerce/marketplace/offers. Commerce returns only active offers from approved merchants with stock available. The BFF validates the canonical discovery envelope (`request_id`, exact `CaTaCaCi/CAL` authority, typed displayable/withheld collections and non-negative ranked count) before serializing any shopper response. Wardrobe recommendations apply the same envelope validation and additionally require candidate/product/offer/Catalog-version binding, CIL eligibility, CAL SHOW, and non-empty policy/arbitration/pipeline contract versions. Invalid or incomplete upstream evidence returns 502 without product details. The opaque request ID is returned for traceability; withheld candidate IDs and raw policy evidence remain private.
- `POST /api/vision/marketplace-search` remains a retrieval-only diagnostic: it returns only an aggregate candidate count with `PENDING_CAL`; no product details are released by this route.
- `POST /api/vision/conversational-discovery` is the product-facing PNELLY Describe It path. It resolves the signed Commerce user, delegates to the same wardrobe-aware `/v1/discover` flow as Wardrobe recommendations, uses active wardrobe items and only consented style feedback, and returns only verified CAL SHOW candidates after the current CIL rights/evidence gate. It never accepts a browser-supplied user ID.
- `POST /api/vision/complementer` resolves the Commerce subject and forwards a request-scoped advisory to the Decision Gateway with both internal and end-user credentials. The response is allowlisted to `advisory_only`; candidate, merchant, price and display-authority fields are not passed through. Complementer creates no durable personal memory and cannot authorize products.
- `POST /api/wardrobe/pnelly/daily-looks` creates three looks from the verified user's active wardrobe and current rotation state. The BFF stamps user-declared location/occasion/climate context at request time; the Decision Gateway evaluates EEPL before profile hydration or look composition. Missing/stale context returns REVIEW, policy violations return BLOCK, and neither result advances wardrobe rotation. PASS is not CAL display authorization.
- XARI_* and TARI_* remain legacy fallback aliases for the PNELLY retrieval adapter; no assistant secret is exposed in browser JavaScript.
- `POST /api/vision/look-it` first derives the subject from the signed Commerce session before parsing multipart data. It then validates one bounded reference file, creates a short-lived Identity `image_processing` + `look_it` consent bundle bound to one request resource, verifies the exact subject/bundle/resource/scopes/expiry, reads and forwards the reference to PNELLY, then revokes the whole request bundle. The UploadFile is closed at request completion; no durable image asset is created. If cleanup fails, the BFF suppresses the search result. It returns only candidate counts and validated outfit-component descriptions; product/offer details remain withheld pending CAL.
- `POST /api/vision/click-it` validates the signed-user/consent assertions, closes the upload without reading its bytes, and returns a private no-store 503 until the masking and resource-bound privacy-attestation pipeline is released. No photo is forwarded to Virtual Twin or Vision Intelligence.
- `/api/wardrobe/outfits` lists and creates saved looks; piece-level add/replace/remove operations are proxied to the Wardrobe service. The BFF derives the owner from Commerce `/me`, generates outfit/slot identifiers, and rejects cross-subject responses.
- `GET /sanctuary.html` serves the Primal Atelier × Living Couture entry experience; `GET /twin-onboarding.html` serves the capability-gated Twin journey. Both are no-store presentation pages and share repository-owned static assets.
- `GET /api/virtual-twin/me` derives the subject from the signed Commerce session, calls the internal Twin Registry owner-scoped list route, validates the returned schema, and exposes only Twin lifecycle/model metadata. It never returns source/mesh asset IDs, object keys or media URLs. The registry rechecks active consent and private-asset ownership before listing an active record. Configure `TWIN_REGISTRY_API_URL` and `TWIN_REGISTRY_API_TOKEN` as server-side secrets; do not put either in the browser.
- The Twin onboarding page uses the authenticated `GET /api/virtual-twin/capabilities` route only. It does not collect photos/video or create consent receipts. The current Twin API returns, at most, a single-still ephemeral pose skeleton; full-body reconstruction, persistent generation, independent validation, owner-scoped Twin status, private image persistence and a complete capture workflow remain unavailable. The page must keep capture locked until these dependencies are delivered and verified.
- The Wardrobe page exposes a per-look Complementer action. It sends only the user-invoked look summary and bounded garment descriptions; the response is rendered as request-scoped advice. Generic Helpful / Not for me reactions remain TAL observations. A separate user-selected value from the bounded aesthetic taxonomy can be saved to USI only with the exact active `profile_storage` receipt; it is tagged with request provenance and can influence later daily looks as a soft positive preference. Users can inspect, replace and deactivate PNELLY-owned preferences; each mutation is consent-bound and uses optimistic profile-version checks.
- `/api/style/color-profile` reads and writes the user's structured liked/disliked/best-version colour preferences through USI/TAL. The BFF derives the subject from Commerce `/me`; profile-storage consent is enforced by Identity Learning. The route does not perform objective complexion or undertone analysis.\n- Account operations require the user's bearer token and are forwarded to Commerce. Commerce remains responsible for signature, issuer, audience, role, ownership, stock, checkout and payment validation.
- Customer cart read/add/update and checkout are additionally blocked unless `COMMERCE_CAL_PURCHASE_PROXY_ENABLED=true` is explicitly set and live Commerce `/ready` plus `/capabilities` confirm CAL Gateway, receipt signer, applied migrations and candidate-bound purchase authorization. The flag defaults off; the BFF rechecks readiness after authenticating the customer on every protected request. The browser unlocks Add to bag and checkout only after an authorized cart read; cart-line deletion remains available for cleanup.
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
- WARDROBE_HTML_PATH: optional path override for the Wardrobe UI; the production image copies `apps/demo-web/wardrobe.html` to `/app/wardrobe.html` and sets this path explicitly.
- `CIRVANNA_REQUIRED_CONTEXT_FIELDS`, `CIRVANNA_EEPL_POLICY_ID`, `CIRVANNA_EEPL_POLICY_VERSION`, `CIRVANNA_ALLOWED_LOCATIONS`, `CIRVANNA_ALLOWED_OCCASIONS`, `CIRVANNA_ALLOWED_CLIMATES`, `CIRVANNA_MINIMUM_AGE`, `CIRVANNA_MAXIMUM_AGE`: configure the Decision Gateway's EEPL policy. Missing required or stale context routes the PNELLY daily-look request to REVIEW; do not treat EEPL PASS as CAL SHOW.
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
## CAL purchase-proxy kill switch

Set `COMMERCE_CAL_PURCHASE_PROXY_ENABLED=false` by default. Enable only in a controlled non-production environment after candidate-bound purchase-receipt verification and audit persistence have passed. A missing flag, failed readiness probe, missing receipt signer, stale migration or disabled CAL Gateway keeps cart mutation and checkout fail-closed.


## Yoti age verification for shopper discovery

The same-origin BFF exposes `POST /api/age-evidence/sessions`, `POST /api/age-evidence/sessions/{session_id}/poll`, and `POST /api/age-evidence/sessions/{session_id}/revoke`. The BFF resolves the authenticated Commerce subject and proxies through the internal Decision Gateway; it never holds the Identity Learning orchestrator credential.

After a verified poll, the browser may attach the returned signed attestation to marketplace or Wardrobe discovery using headers `X-Cirvanna-Age-Attestation` (JSON), `X-Cirvanna-Age-Attestation-Signature`, and `X-Cirvanna-Age-Evidence-Request-ID`. The BFF checks subject, purpose and request binding before forwarding; the Gateway then verifies the signature and consumes the one-time JTI. Do not reuse an attestation for another request or shopper. The same three headers are forwarded by the BFF Commerce proxy only on cart/checkout purchase paths. One purchase authorization can cover up to 25 unique Catalog products; larger carts require separate requests and fresh attestations. If the attestation is absent, expired, revoked, replayed, or mismatched, age-restricted candidates remain withheld.
