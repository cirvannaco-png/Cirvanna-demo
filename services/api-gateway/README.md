# Cirvanna API Gateway

**Status:** the gateway now has a verified-Commerce-subject mode, USI profile hydration, consented TAL routes, live Catalog/Commerce discovery, deterministic preference ranking, signed independent safety/FCI provider adapters, and CAL-only product display. Production is still gated on real provider attestations, managed audit storage, and deployed operations verification.

## Responsibilities

- Authenticate internal API callers with the gateway service bearer token.
- Resolve end-user subjects through Commerce `GET /me` by default; never treat a request-body user ID as identity. Unverified mode is an explicit local/test-only opt-out.
- Hydrate positive style preferences from the canonical identity-learning service.
- Proxy profile, consent, TAL event, export, correction and deletion operations to their canonical owner.
- Retrieve canonical active Catalog products and currently purchasable Commerce offers.
- Rank candidates using weighted explicit USI preference matches. This score is an ordering heuristic, not a probability, model confidence, or display authorization.
- Retrieve and verify candidate-bound signed safety and FCI evidence from separately configured providers.
- Submit every candidate to CaTaCaCi/CAL. Product and offer details are returned to the marketplace only for CAL SHOW. The lower-level `/v1/decisions` response also redacts SKU, name, category, brand, price, currency and images for BLOCK/REVIEW.
- After CAL SHOW and before returning product/offer details, call CIL `POST /serving/assessment` with the exact Catalog product ID/version, claims and ingredient declarations. CIL checks commercial-use rights, permitted purpose, evidence grade/scope, attribution and human claim approval. Missing/mismatched assessments, stale versions, unlicensed sources, unsupported claims or CIL outages withhold the candidate. CAL remains the final display authority; CIL is an additional rights/evidence gate, not a replacement.
- When `CIL_CAL_REVIEW_ENFORCEMENT_REQUIRED=true`, query the latest final human CAL feedback decision for the same product and normalized climate/occasion context before releasing details. A matching `BLOCK` is an additional context-scoped veto; feedback `SHOW` cannot override the ordinary CAL/safety/legal/NPL/USI/FCI pipeline. If configured enforcement cannot obtain a valid review result, the Gateway fails closed.
- Keep Complementer styling guidance advisory-only.

## Human CAL feedback review enforcement

Set `CIL_CAL_REVIEW_ENFORCEMENT_REQUIRED=true` only after the Intelligence Service review store is deployed, migrated and staging-tested. The Gateway calls `POST /cal/feedback-decisions` with exact product IDs and the normalized coarse climate/occasion context using the dedicated `CIL_CAL_SERVICE_TOKEN`. Responses are validated for exact product/context, final verdict, review ID and decision reference. A matching `BLOCK` suppresses the candidate before audit and the CIL rights assessment; a feedback `SHOW` cannot change a normal `BLOCK` or `REVIEW`. Missing configuration, unavailable service, malformed or ambiguous decisions fail closed. Keep the flag false until live integration evidence exists.

## Authentication model

Every gateway route requires `Authorization: Bearer $CIRVANNA_API_TOKEN` for the calling internal service.

Routes that act on an end user additionally require:

`X-End-User-Authorization: Bearer <Commerce-issued-user-token>`

The gateway sends that user token to Commerce `GET /me` and uses only the verified `user_id` returned by Commerce. A body `user_id` must exactly match that verified subject. The internal gateway token is not an end-user credential.

`CIRVANNA_REQUIRE_VERIFIED_IDENTITY` defaults to `true`. Production must leave it enabled. Setting it to `false` is an explicit local/test-only opt-out for deterministic request-scoped contract tests; `/v1/discover` and all `/v1/me/*` personal-data routes require verified identity regardless.

## Routes

- `GET /health` — liveness only.
- `GET /ready` — checks gateway auth, Catalog, audit-store access, policy configuration, and identity service readiness when verified identity is required.
- `GET /capabilities` — reports enabled integrations and explicit unavailable capabilities.
- `POST /v1/decisions` — evaluate 1–25 canonical Catalog product IDs through the decision pipeline; merchandising fields are present only for CAL SHOW, otherwise only the candidate ID and decision evidence are returned.
- `POST /v1/discover` — live Catalog search + Commerce purchasable-offer retrieval, USI preference ranking, then CAL arbitration. Product and offer details are included only for SHOW candidates.
- `POST /v1/complementer/recommend` — styling advice only; no product candidates or display authority.
- `GET /v1/me/style-profile` and `PUT /v1/me/style-profile` — read/update the verified subject's USI profile.
- `POST /v1/me/consents` and `POST /v1/me/consents/{receipt_id}/revoke` — create and revoke versioned consent receipts.
- `POST /v1/me/tal/events` — append consented observations or append-only correction events.
- `GET /v1/me/tal/export` — export profile, consent receipts and temporal events.
- `DELETE /v1/me/tal/data` — delete the subject's profile, consent receipts and events; retain a one-way deletion receipt.

### USI and TAL flow

The gateway resolves the end-user subject through Commerce `/me`, then calls the identity-learning service using its private service token. The identity service owns prefixed tables in the existing approved Postgres database; it does not create a second database. Profile reads and writes require an active `profile_storage` consent receipt. TAL writes require active `personalization` or `style_learning` consent. Event IDs and per-subject idempotency keys prevent duplicate writes; changed replays return 409. Corrections are append-only and identify the event they supersede. A denial receipt or revocation revokes every active grant for the same subject and consent scope, so parallel older receipts cannot keep authorizing writes. A later grant creates a new receipt; revoked receipts remain revoked. Retention purge, export and deletion are implemented by the canonical identity service.

Rejected Complementer suggestions remain soft observations. They do not automatically become NPL hard vetoes.

## Marketplace discovery and display control

`POST /v1/discover` accepts a search query, optional category/currency, context, and explicit constraints. The gateway:

1. Queries Catalog `GET /products` for active canonical product records.
2. Queries Commerce `GET /marketplace/offers` for active offers with available inventory.
3. Joins offers to Catalog by exact `catalog_product_id`; orphan offers are discarded.
4. Keeps the lowest-priced purchasable offer per canonical product.
5. Ranks by weighted explicit USI preference matches, then price and product ID.
6. Runs the candidate IDs through the same decision pipeline as `/v1/decisions`.
7. Returns full product and offer details only where the corresponding CAL result is `SHOW` and `may_display=true`. Other candidates are returned only as withheld IDs and decision states.

The rank score is not a probability and never overrides CAL. The CIL serving assessment is mandatory after CAL SHOW; configure `CIL_SERVICE_URL` and the distinct `CIL_CATALOG_SERVICE_TOKEN` before discovery can return details. In the current build the safety and FCI providers are not provisioned, so otherwise eligible candidates remain REVIEW and no product details are returned from discovery. This is intentional fail-closed behavior, not a marketplace ranking failure.

## Independent safety and calibrated FCI evidence

Provider adapters call a trusted HTTPS `POST /v1/evaluate` endpoint. Each response is bound to the request ID, Commerce-verified subject, candidate ID and SHA-256 of the canonical Catalog product snapshot. Provider evidence uses an HMAC key distinct from the validation-attestation key.

Each validation manifest must:
- Carry the pinned `*_VALIDATION_REPORT_SHA256` value.
- Match the required scope (`product_safety` or `fit_confidence`) and exact model version.
- Declare a distinct independent evaluator ID and `independent_validation=true`.
- Carry a valid HMAC attestation from the separately provisioned validation key.
- Have valid `validated_at` and future `valid_until` timestamps.

FCI additionally requires a calibrated estimate, confidence interval, calibration version, unique evidence IDs, and declared/observed evidence fields. Invalid, expired, mismatched, unsigned, or incomplete provider responses fail closed. Missing providers produce UNKNOWN signals; CAL returns REVIEW. Fixture-only tests do not establish real provider validity.

The adapter contract is not a substitute for independent scientific or safety evaluation. Operators must obtain and review the actual validation report, pin its SHA-256, provision keys from separate trust domains, and run staging verification before enabling a provider.

## Configuration

| Variable | Purpose |
|---|---|
| `CIRVANNA_API_TOKEN` | Inbound internal gateway bearer token |
| `CIRVANNA_REQUIRE_VERIFIED_IDENTITY` | Defaults to true; set false only for local/test-only request-scoped demo mode |
| `CIRVANNA_AUDIT_DB` | Local/staging SQLite audit path; not production managed audit |
| `CIRVANNA_POLICY_VERSION` | Decision policy version |
| `CIRVANNA_REQUIRED_CONTEXT_FIELDS` | EEPL context requirements |
| `CIRVANNA_REQUIRED_PRODUCT_ATTRIBUTES` | Required Catalog metadata |
| `COMMERCE_API_URL` | Trusted Commerce `/me` and offers API base URL |
| `CATALOG_SERVICE_URL` | Trusted Catalog API base URL |
| `CATALOG_API_TOKEN` | Catalog read credential |
| `IDENTITY_SERVICE_URL` | Private USI/TAL service URL |
| `IDENTITY_SERVICE_TOKEN` | Identity service bearer token, at least 32 bytes |
| `COMPLEMENTER_SERVICE_URL` | Trusted Complementer API base URL |
| `COMPLEMENTER_SERVICE_TOKEN` | Complementer service bearer token |
| `NPL_SERVICE_URL`, `NPL_SERVICE_TOKEN`, `NPL_EVIDENCE_HMAC_SECRET` | Persistent NPL provider and signed evidence |
| `CULTURAL_IDENTITY_SERVICE_URL`, `CULTURAL_IDENTITY_SERVICE_TOKEN`, `CULTURAL_IDENTITY_HMAC_SECRET` | Explicit cultural declaration provider and signed evidence |
| `SAFETY_SERVICE_URL`, `SAFETY_SERVICE_TOKEN` | Independent product-safety provider |
| `SAFETY_EVIDENCE_HMAC_SECRET` | Safety evidence signature key |
| `SAFETY_VALIDATION_HMAC_SECRET`, `SAFETY_VALIDATION_REPORT_SHA256` | Independent safety attestation key and pinned report hash |
| `FCI_SERVICE_URL`, `FCI_SERVICE_TOKEN` | Calibrated FCI provider |
| `FCI_EVIDENCE_HMAC_SECRET` | FCI evidence signature key |
| `FCI_VALIDATION_HMAC_SECRET`, `FCI_VALIDATION_REPORT_SHA256` | Independent FCI attestation key and pinned report hash |
| `CIL_SERVICE_URL` | Private Cirvanna Intelligence Service URL |
| `CIL_CATALOG_SERVICE_TOKEN` | Separate bearer credential for CIL Catalog-serving assessment (at least 32 bytes) |

All remote internal service URLs must use HTTPS, contain no embedded credentials/query/fragment, and be configured via secret storage. Use separate, independently rotated secrets for gateway auth, provider evidence signatures, and validation attestations.

## Local setup

Start Catalog on port 8081, Commerce on its configured local port, identity-learning on port 8092, Complementer on port 8090, and the gateway on port 8080. Use a local Commerce HS256 token only for development/tests; production must use provider-issued RS256/JWKS tokens.

From each service directory:

    python -m pip install -r requirements.txt
    python -m pytest tests -q

For identity-learning local development, use SQLite and `IDENTITY_AUTO_CREATE_SCHEMA=true`. For shared environments, point `IDENTITY_DATABASE_URL` at the existing approved managed Postgres instance and apply `migrations/0001_identity_tal.sql`; production schema auto-creation must remain false.

## Container build

Build the gateway from the repository root:

    docker build -f services/api-gateway/Dockerfile -t cirvanna-decision-gateway .

Build Complementer and identity-learning with their own service directories as contexts:

    cd services/recommendation-service && docker build -f Dockerfile -t cirvanna-complementer .
    cd ../identity-learning-service && docker build -f Dockerfile -t cirvanna-identity-learning .

## Validation

From the repository root:

    python scripts/validate_architecture.py
    python -m unittest discover -s tests/architecture -v
    python scripts/scan_source_secrets.py

The Decision Gateway workflow runs gateway HTTP/integration tests, container build, architecture checks and secret scanning. When human feedback enforcement is enabled, configure the private `CIL_SERVICE_URL` and dedicated `CIL_CAL_SERVICE_TOKEN`; the gateway fails closed when the review store is unavailable. The identity-learning workflow runs its persistence, review lifecycle and consent-revocation regression tests plus container build. Check the exact branch commit's CI before merge.

## Current production blockers

- Real Commerce OIDC/JWKS issuer, audience and production auth settings.
- Identity-learning deployment on the selected Render workspace, migration execution and PostgreSQL backup/restore verification.
- Independent safety provider, signed validation report, separate evaluator key and operational approval.
- Calibrated FCI provider, real calibration dataset/report, subgroup validation and drift monitoring.
- Managed audit storage, key rotation, monitoring/alerts, staging E2E, load/failure tests, incident response and rollback.
- Production marketplace offer API security and end-to-end display verification.

Do not claim production readiness from unit tests, signed test fixtures, a passing container build, or a configured URL alone.
