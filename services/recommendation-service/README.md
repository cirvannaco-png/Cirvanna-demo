# Cirvanna Complementer Agent

**Status:** deterministic advisory v1. API contract and rule composer are implemented; no LLM provider, user-profile store, live catalogue integration or production deployment is configured.

Complementer helps a user finish a look by composing four connected directions:

- **Colour coordination:** current outfit colours, favourite colours and explicit exclusions; curated colour-harmony options are a fallback, not a rule.
- **Fragrance direction:** selected scent families and intensity preferences. Fragrance-free or sensitivity settings override every scent suggestion.
- **Earrings:** selected earring styles and metals take priority; neckline and hairstyle are secondary context. A no-earrings choice is respected.
- **Aesthetic composition:** a concise finish direction based on the user's chosen aesthetic.

## API

POST /v1/complementer/recommend

Requires Authorization: Bearer $COMPLEMENTER_SERVICE_TOKEN. The secret must contain at least 32 UTF-8 bytes. GET /health reports liveness; GET /ready reports whether authentication is configured.

Example request:

    {
      "request_id": "req-001",
      "user_id": "opaque-user-id",
      "preferences": {
        "aesthetics": ["minimalist", "classic"],
        "favorite_colors": ["teal", "cream"],
        "avoid_colors": ["neon pink"],
        "favorite_fragrance_families": ["citrus", "woody"],
        "fragrance_sensitive": false,
        "fragrance_free": false,
        "fragrance_intensity": "light",
        "earrings_preference": "yes",
        "preferred_earring_shapes": ["huggie"],
        "preferred_metals": ["gold"]
      },
      "look": {
        "outfit_colors": ["navy"],
        "neckline": "off_shoulder",
        "hairstyle": "up",
        "climate": "hot_humid",
        "occasion": "evening"
      }
    }

The response is deterministic and explainable. Missing preferences produce needs_input rather than invented personal preferences. The first implementation is stateless: it does not persist profile data, request bodies, face media or model outputs.

## Guardrails and ownership

- Use only explicit user preferences and current-look context. Never infer gender, ethnicity, religion, culture, modesty, skin tone or fragrance preference from a face, name or location.
- Aesthetic guidance is not a judgement about the user's appearance. Users can override every suggestion.
- Fragrance sensitivity means the service abstains from scent suggestions. It makes no medical or allergy-safety claims.
- V1 returns style directions only. It does not invent brands, SKUs, prices, stock, product benefits or purchase links.
- This service is not the product catalogue, recommender-ranking authority, fit predictor, medical module, checkout authority or final display gate. Specific catalog items must be fetched from Catalog and pass the existing CaTaCaCi/CAL display controls before being shown.
- The trusted application layer must hydrate preferences from the canonical user profile/USI/NPL and explicit cultural-declaration services. Do not trust arbitrary browser-supplied user IDs or exclusions at public ingress.
- No face image or video is accepted by this endpoint.

## Local development

    python -m pip install -r requirements.txt
    export COMPLEMENTER_SERVICE_TOKEN='replace-with-a-long-random-secret-of-at-least-32-bytes'
    uvicorn app.main:app --host 127.0.0.1 --port 8080

Run checks:

    python -m pip check
    python -m compileall -q app tests
    python -m pytest -q

The service can be built from this directory with docker build -t cirvanna-complementer ..

## Not yet implemented

- User-facing preference editor and Cirvanna UI integration.
- Trusted server-side profile/USI/NPL/cultural-declaration hydration and authenticated service-to-service wiring.
- Product retrieval from Catalog, inventory/price provenance, and CAL-gated product cards.
- Personalization experiments, feedback learning and model-provider integration. None should be represented as live until separately implemented and evaluated.
