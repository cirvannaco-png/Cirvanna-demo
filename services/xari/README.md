# Xari service

**Status:** consent-aware route planning plus an implemented, configuration-gated natural-language marketplace-search adapter.

Xari is the canonical assistant/orchestration name. Tari and Xyra are legacy source generations and must not be deployed as duplicate orchestrators.

## Marketplace description search

POST /v1/marketplace/search accepts a natural-language product/garment description and optional category/limit. Xari forwards a typed request to the private Vision Intelligence service, which ranks current active, approved, in-stock Commerce offers enriched with active Catalog descriptions and attributes. This supports requests such as “a modest green linen dress for warm weather” or “a moisturizer with a light texture”.

The result is named candidates, with display_authorized=false and decision_status=PENDING_CAL. Similarity values are not probabilities. Xari does not authorize display, fit, or purchase: NPL, explicit cultural-identity requirements and CAL still have to run before any candidate is shown.

The initial Click It path is POST /click-it on the authenticated Virtual Twin API, which verifies stored consent and Twin ownership before passing a photo to the same private Vision Intelligence service. This path compares image embeddings with text/metadata about active marketplace offers; exact product-photo comparison is not yet implemented.

## API and limits

- GET /health — process liveness.
- GET /ready — API token configuration.
- GET /capabilities — route and marketplace-adapter status.
- POST /v1/route — existing route-planning contract.
- POST /v1/marketplace/search — authenticated semantic candidate search.

## Environment

- XARI_API_TOKEN: high-entropy internal bearer token (at least 32 UTF-8 bytes).
- VISION_INTELLIGENCE_API_URL: trusted HTTPS base URL for the private Vision Intelligence service (local HTTP only for development).
- VISION_INTELLIGENCE_API_TOKEN: internal worker bearer token, at least 32 bytes.
- Existing optional trusted base URLs: XARI_CHAT_API_URL, DERMALSIGHT_API_URL, MARKETPLACE_BFF_URL, VIRTUAL_TRY_ON_API_URL, VIRTUAL_TWIN_API_URL, WARDROBE_API_URL.

For local verification:

    python -m pip install -r requirements.txt
    python -m pytest -q

Do not expose service tokens or these internal APIs directly to browser code. The current text-search adapter executes retrieval, but full Xari task execution, live user identity integration and CAL-approved result presentation are separate release gates.
