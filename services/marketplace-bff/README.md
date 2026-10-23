# Cirvanna Marketplace BFF

**Status: deployable integration boundary; production remains gated on verified upstream services and identity-provider integration.**

This is the server-side browser boundary for marketplace browsing and visual discovery. It serves the marketplace UI, proxies public offers, forwards allowlisted account operations, routes natural-language search to Xari, and forwards Click It photos to the private Virtual Twin API after deriving the user subject from Commerce's verified `/me` endpoint. It does not issue identities, hold user tokens in storage, bypass Commerce authorization, or invent fit/try-on results.

## Why this boundary exists

- No Catalog or Commerce service credential is embedded in the marketplace page. Catalog secrets remain in Catalog/Commerce service environments; the BFF uses only configured upstream URLs.
- The browser defaults to GET /api/commerce/marketplace/offers. Commerce returns only active offers from approved merchants with stock available.
- `POST /api/vision/marketplace-search` forwards a bounded written description/category/limit to Xari using a server-side token. It does not expose the Xari secret in browser JavaScript.
- `POST /api/vision/click-it` requires a signed Commerce user JWT, checks the user through `GET /me`, and forwards a size-bounded product photo to Virtual Twin with a server-side token. It never trusts a browser-supplied subject/user ID.
- The BFF derives the user ID from Commerce `/me` before any candidate governance. Cart, saved-product, order and checkout routes currently return HTTP 503 until current CAL authorization can be revalidated atomically by Commerce.
- Only customer cart, saved-product, checkout and order routes are proxied. Admin, merchant-management, webhooks, cron, and internal endpoints are not exposed through this gateway.
- No CORS allowlist is added to this same-origin UI/API. Security headers include CSP, nosniff, no-referrer, frame denial, and disabled camera/microphone/geolocation.

## Runtime configuration

Set through the deployment secret manager:

- CATALOG_API_URL: deployed canonical Catalog API base URL.
- COMMERCE_API_URL: deployed Commerce API base URL.
- MARKETPLACE_HTML_PATH: optional path override for a nonstandard container layout.
- GOVERNANCE_EVIDENCE_API_URL and GOVERNANCE_EVIDENCE_API_TOKEN: private, authenticated per-candidate evidence provider implementing `POST /v1/decision-evidence`.
- DECISION_SERVICE_API_URL and DECISION_SERVICE_TOKEN: private canonical decision-service base URL and internal bearer token.

The BFF `/ready` endpoint requires Catalog, Commerce, evidence-provider and decision-service `/ready` checks to succeed. These variables are not proof that current NPL, explicit cultural requirements, or calibrated fit evidence exist; the evidence provider must source and sign each record from its authoritative provider. The decision service still validates all three evidence signatures independently.

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


## Candidate-bound CAL gateway

The BFF now contains a server-side per-candidate gateway used by Xari search, Click It and normal marketplace offers. It does not trust retrieval-provider `display_authorized`, verdict, score or confidence claims. Every candidate must have a stable offer/variant/product identifier and receive a fresh decision-service request. Only the canonical decision response with the exact candidate ID, exact request ID, `decision="SHOW"`, and `may_display=true` crosses the browser boundary. Conflicting upstream display fields are removed and replaced only after those checks pass.

### Evidence provider contract

The private provider must implement `POST /v1/decision-evidence`. The BFF sends:

```json
{
  "request_id": "<fresh UUID>",
  "subject_id": "<verified Commerce /me user_id>",
  "candidate_id": "<exact marketplace offer or variant ID>",
  "requested_at": "<UTC ISO-8601 timestamp>"
}
```

The provider must reload the user's current, active NPL preferences and explicitly declared cultural requirements for each candidate, combine them with the trusted product attribute envelope and an authorized fit-evidence provider, then return:

```json
{
  "request_id": "<same UUID>",
  "subject_id": "<same verified user ID>",
  "candidate_id": "<same candidate ID>",
  "issued_at": "<UTC ISO-8601 timestamp>",
  "expires_at": "<UTC ISO-8601 timestamp, at most 60 seconds after issued_at>",
  "decision_request": {
    "...": "complete services/decision-service EligibilityRequest"
  }
}
```

The embedded request must match the current `services/decision-service/app/main.py` `EligibilityRequest` schema, including `context.user_id`, `usi_profile.user_id`, `fit_estimate.user_id` and `fit_estimate.candidate_id`, every NPL/cultural record's `user_id`, candidate-bound signatures, and the request/candidate IDs. The BFF rejects envelopes older than 30 seconds, expired or overlong envelopes, foreign users/candidates, missing signatures and malformed payloads. The decision service independently verifies NPL, cultural and fit evidence HMAC signatures. The evidence token authenticates the provider; it does not replace those evidence signatures.

Each candidate is evaluated independently. BLOCK, REVIEW, mismatched IDs, missing/stale evidence, invalid signatures, timeouts, non-200 responses and malformed responses suppress that candidate. A failed candidate never inherits another candidate's authorization. Similarity scores are not probabilities and never authorize display.

## Remaining purchase-flow release gates

The candidate-display gateway is implemented, but it is not operationally complete until the evidence provider and decision service are securely deployed, configured and tested against live upstream data. When either service is absent, product display stays fail-closed. Current user-specific NPL persistence and explicit cultural-declaration freshness must be proven by the provider, not inferred by the BFF.

Cart, saved-product, order and checkout routes remain HTTP 503 with `CAL_GOVERNANCE_NOT_ENFORCED`. A listing-time SHOW decision alone is insufficient for purchase: the commerce transaction must atomically revalidate the current candidate, user constraints, stock and price at checkout, and record the decision/request IDs against the order. Do not enable purchase routes until that integration and tamper-resistant audit persistence are implemented and live-tested.

Production release still requires deployed identity/session integration, model and fit calibration evidence, PostgreSQL migrations/backups/restore drills, payment-provider test-mode reconciliation, shipping/tax/refund/return workflows, seller payouts and fulfilment, privacy deletion/retention, rate limits/alerts, and live origin/credential smoke tests.
