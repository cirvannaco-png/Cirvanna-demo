# Cirvanna API Gateway

**Status:** the authenticated decision gateway and request-scoped Complementer advisory proxy are implemented on this feature branch. The gateway is not production-certified.

## Responsibilities

- Authenticate internal API requests using the gateway bearer token.
- Fetch canonical products from Catalog; never fabricate product records.
- Compose the existing EEPL, USI, NPL, FCI evidence contract, cultural-declaration evidence, and CaTaCaCi/CAL kernels.
- Load persistent NPL and cultural-declaration snapshots only when their trusted providers are configured and their candidate-bound HMAC signatures verify.
- Append minimal decision-audit events before returning a decision.
- Authorize product display only when the actual CAL verdict is SHOW.
- Optionally proxy request-scoped Complementer styling advice. This route never returns product candidates and never authorizes display.

## Routes

- GET /health — liveness only.
- GET /ready — checks gateway authentication, Catalog readiness, audit-store access, and policy configuration. Complementer is optional and does not gate decision readiness.
- GET /capabilities — reports configured integrations and unavailable capabilities.
- POST /v1/decisions — evaluates 1–25 active canonical Catalog product IDs.
- POST /v1/complementer/recommend — forwards explicit preferences and current-look context to the stateless Complementer service and returns styling guidance only.

Both POST routes require Authorization: Bearer $CIRVANNA_API_TOKEN. The gateway uses a separate server-side bearer token for Complementer and a separate Catalog credential. Never expose service credentials in browser code.

## Local setup

Use separate processes and virtual environments. Supply credentials through the shell or a local secret store; do not commit them.

1. Start Catalog from services/catalog-service. Install its requirements, configure a local Catalog token, and start it on port 8081. SQLite is for local development only.
2. Start Complementer from services/recommendation-service. Install its requirements, set COMPLEMENTER_SERVICE_TOKEN to a random value of at least 32 bytes, and start it on port 8090.
3. Start the gateway from services/api-gateway. Install its requirements and configure:
   - CIRVANNA_API_TOKEN — inbound internal gateway bearer token.
   - CATALOG_SERVICE_URL and CATALOG_API_TOKEN — Catalog base URL and read credential.
   - CIRVANNA_AUDIT_DB — durable local SQLite file path for decision audit events.
   - COMPLEMENTER_SERVICE_URL — trusted Complementer base URL; HTTPS is required except for localhost during development.
   - COMPLEMENTER_SERVICE_TOKEN — outbound Complementer bearer token, at least 32 bytes.
4. Start the gateway on port 8080 and verify /health, /ready, and /capabilities.

Example commands, run from each service directory:

    python -m pip install -r requirements.txt
    uvicorn app.main:app --host 127.0.0.1 --port 8090
    python -m pytest tests -q

The gateway and Complementer must run as separate processes for the HTTP proxy integration to be exercised.

## Complementer advisory contract

POST /v1/complementer/recommend accepts request_id, user_id, preferences, and look. The gateway forwards the complete validated JSON to Complementer's POST /v1/complementer/recommend endpoint with its private service token.

The request's user_id is currently an opaque request-scope identifier supplied by the caller. The gateway does **not** bind it to a verified end-user identity provider. Complementer is stateless and does not load or persist a user profile, so this route must remain internal/staging-only until trusted identity binding exists.

The gateway validates the upstream response schema, request/user scope, and stateless persistence declaration. It always wraps the response with:

- mode = advisory_only
- display_authorized = false
- durable_personal_memory = false

No product name, SKU, price, offer, stock value, or purchase link is sourced from Complementer. Product candidates must be retrieved from canonical Catalog/Commerce services and evaluated through the separate decision route.

Complementer feedback remains a consent-gated TAL handoff only. This gateway does not forward feedback into NPL and does not create hard exclusions from rejected recommendations.

## Product decision contract

POST /v1/decisions accepts:
- user_id: caller-supplied request identity; it is not authenticated identity.
- product_ids: 1–25 unique UUIDs from canonical Catalog.
- context: optional age, location, occasion, and climate.
- style_preferences: explicit positive attributes evaluated by USI.
- negative_preferences: explicit item/attribute hard exclusions.
- cultural_requirements: explicit user-declared requirements.
- hard_constraints: explicitly supplied required/forbidden attributes.

The gateway fetches product facts from Catalog. When configured, it loads NPL and cultural declarations from their separate persistent services and verifies the signed evidence for the exact request, user, candidate, and attributes. NPL is never silently treated as empty after a partial configuration or provider failure.

## CAL and safety behavior

Only CAL SHOW sets may_display=true. BLOCK is a hard veto. REVIEW is fail-closed when required evidence is missing, unknown, incomplete, or untrusted.

The independent product-safety provider and trained/calibrated FCI predictor are not configured in this repository build. The gateway therefore produces UNKNOWN safety evidence and an unavailable fit estimate; otherwise eligible candidates normally remain REVIEW. Tests may inject fixture-only providers to exercise SHOW, but such fixtures are not live provider results.

The gateway's local audit store is SQLite. It records request/product IDs, verdicts, reason codes, Catalog version, policy/contract versions, and timestamp; it omits user IDs, measurements, and images. This is not a managed production audit backend.

## Configuration

| Variable | Purpose |
|---|---|
| CIRVANNA_API_TOKEN | Inbound internal gateway bearer token |
| CIRVANNA_AUDIT_DB | Persistent local/staging SQLite audit path; not a production managed store |
| CIRVANNA_POLICY_VERSION | Version stamped onto decision outputs |
| CIRVANNA_REQUIRED_CONTEXT_FIELDS | Comma-separated EEPL required fields; default location,occasion,climate |
| CIRVANNA_REQUIRED_PRODUCT_ATTRIBUTES | Catalog fields required for complete candidate metadata; default style,material,color |
| CIRVANNA_MINIMUM_AGE / CIRVANNA_MAXIMUM_AGE | Optional age boundaries |
| CIRVANNA_ALLOWED_LOCATIONS / CIRVANNA_ALLOWED_OCCASIONS / CIRVANNA_ALLOWED_CLIMATES | Optional context allowlists |
| CATALOG_SERVICE_URL | Trusted Catalog API base URL |
| CATALOG_API_TOKEN | Catalog read credential |
| COMPLEMENTER_SERVICE_URL | Trusted Complementer API base URL |
| COMPLEMENTER_SERVICE_TOKEN | Internal Complementer bearer token, at least 32 bytes |
| NPL_SERVICE_URL | Optional trusted persistent NPL service URL |
| NPL_SERVICE_TOKEN | NPL bearer token |
| NPL_EVIDENCE_HMAC_SECRET | Shared HMAC key used to verify NPL evidence |
| CULTURAL_IDENTITY_SERVICE_URL | Optional trusted cultural declaration service URL |
| CULTURAL_IDENTITY_SERVICE_TOKEN | Cultural service bearer token |
| CULTURAL_IDENTITY_HMAC_SECRET | Shared HMAC key used to verify cultural evidence |

Non-local service URLs must use HTTPS and must not include embedded URL credentials, query strings, or fragments. NPL and cultural services are optional when completely unconfigured; partial configuration or an invalid provider response fails closed.

## Container build

Build from the repository root so the image includes the shared packages:

    docker build -f services/api-gateway/Dockerfile -t cirvanna-decision-gateway .
    docker build -f services/recommendation-service/Dockerfile -t cirvanna-complementer .

The gateway image uses the platform PORT when supplied and stores its local audit database under /data. Mount persistent storage for local/staging use; this is not a substitute for managed production audit storage, retention, backup, and recovery.

## Validation

From the repository root:

    python -m pip install -r services/api-gateway/requirements.txt
    cd services/api-gateway
    python -m pytest tests -q
    cd ../..
    python -m pip install -r services/recommendation-service/requirements.txt
    cd services/recommendation-service
    python -m pytest tests -q
    cd ../..
    python scripts/validate_architecture.py
    python -m unittest discover -s tests/architecture -v
    python scripts/scan_source_secrets.py

The Decision Gateway workflow runs API integration tests, the container build, architecture validation, the architecture regression suite, and source secret scanning. It also runs when the Complementer service contract changes.

## Security and privacy boundaries

- These bearer tokens are service credentials, not end-user identity.
- The gateway currently has no verified identity-provider binding for user_id. Do not expose the decision or Complementer endpoints as public user APIs until subject binding and scoped authorization are added.
- Keep Catalog write credentials out of the gateway; use only the read token.
- Keep NPL and cultural HMAC keys private and independently rotated.
- Complementer receives explicit preference/look JSON only and has no image upload route.
- Feedback requires explicit personalisation consent; a rejection remains a soft TAL observation.
- Never infer culture, religion, ethnicity, gender, modesty, skin tone, or facial geometry from appearance.
- No response from Complementer may authorize product display or checkout.
- Do not log tokens, images, sensitive preference values, or raw upstream error bodies.

## Remaining release blockers

- Bind user_id to a verified end-user principal and enforce tenant isolation across profile and preference providers.
- Build the canonical USI profile service/persistence and trusted hydration path.
- Implement durable TAL storage, consent receipts, replay/idempotency, retention, correction, export, deletion, and audit.
- Connect Complementer marketplace retrieval to canonical Catalog/Commerce records without bypassing CAL.
- Configure a real product-safety provider and a separately validated, calibrated FCI provider.
- Replace local SQLite audit with managed durable storage and tested recovery.
- Run deployed PostgreSQL migration/backup/restore tests, service key rotation, real staging E2E, load/failure tests, observability, and rollback drills.
- Keep skin-state forecasting disabled until DermalSight has a validated longitudinal dataset/model and calibrated independent validation.
