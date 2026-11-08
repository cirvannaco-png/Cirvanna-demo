# PNELLY assistant service (compatibility source path: `services/xari`)

**Status:** consent-aware route planning plus an implemented, configuration-gated natural-language marketplace-search adapter.

PNELLY is the canonical product-facing assistant and orchestration identity. Xari, Tari and Xyra are legacy aliases/source generations; there is one assistant runtime. The `services/xari` source path and `/v1/*` route contract are retained temporarily for compatibility, not as a second assistant.

## Marketplace description search

POST /v1/marketplace/search accepts a natural-language product/garment description and optional category/limit. PNELLY forwards a typed request to the private Vision Intelligence service, which ranks current active, approved, in-stock Commerce offers enriched with active Catalog descriptions and attributes. This supports requests such as “a modest green linen dress for warm weather” or “a moisturizer with a light texture”.

The result is named candidates, with display_authorized=false and decision_status=PENDING_CAL. Similarity values are not probabilities. PNELLY does not authorize display, fit, or purchase: NPL, explicit cultural-identity requirements and CAL still have to run before any candidate is shown.

The historical Virtual Twin `/click-it` route remains a separately gated internal contract. The Marketplace BFF now closes Click It uploads without reading or forwarding the photo and returns `503 CLICK_IT_PRIVACY_PIPELINE_NOT_RELEASED`; Vision Intelligence independently refuses processing until the masking and asset-attestation pipeline is released. Do not advertise Click It as available.

## API and limits

- GET /health — process liveness.
- GET /ready — API token configuration.
- GET /capabilities — route and marketplace-adapter status.
- POST /v1/route — existing route-planning contract.
- POST /v1/marketplace/search — authenticated semantic candidate search.

## Environment

- PNELLY_API_TOKEN: preferred high-entropy internal bearer token (at least 32 UTF-8 bytes). XARI_API_TOKEN and TARI_API_TOKEN remain compatibility fallbacks.
- VISION_INTELLIGENCE_API_URL: trusted HTTPS base URL for the private Vision Intelligence service (local HTTP only for development).
- VISION_INTELLIGENCE_API_TOKEN: internal worker bearer token, at least 32 bytes.
- Existing optional trusted base URLs: XARI_CHAT_API_URL, DERMALSIGHT_API_URL, MARKETPLACE_BFF_URL, VIRTUAL_TRY_ON_API_URL, VIRTUAL_TWIN_API_URL, WARDROBE_API_URL.

For local verification:

    python -m pip install -r requirements.txt
    python -m pytest -q

Do not expose service tokens or these internal APIs directly to browser code. The current text-search adapter executes retrieval, but full PNELLY task execution, live user identity integration and CAL-approved result presentation are separate release gates.

## Optional collaborators and marketplace price integrity

PNELLY may invoke Complementer only when the user requests styling help or when an optional styling step is explicitly enabled. Complementer returns advisory look directions; it does not own product search, canonical product identity, current offers, prices, inventory, or display decisions. It must not be required for a basic PNELLY search.

For marketplace discovery, candidate retrieval is not display authorization. Before products are shown, the result must pass NPL and explicit cultural requirements and receive CAL SHOW. Merchant, stock, currency and price values must be fetched from current Catalog/Commerce records. Price comparisons must group offers by canonical product/variant and currency, include the merchant and observation time, and must not compare unlike currencies or imply landed cost when shipping/tax is unknown.

PNELLY is also an optional entry point from Virtual Twin and Virtual Try-On. Those services retain their own consent, identity, asset-ownership and model-readiness boundaries; PNELLY cannot bypass them.