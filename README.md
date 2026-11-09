# Cirvanna

**Computing purchase certainty before checkout.**

Cirvanna is an identity-first beauty, fashion, fit, and commerce-intelligence platform. It is designed to help people evaluate whether products and complete looks fit their declared preferences, context, and available evidence before purchase. For merchants, the objective is to improve relevance and measure avoidable returns through controlled pilots—not to promise unverified conversion or return-reduction gains.

> **Engineering status — 9 November 2026:** Cirvanna is an active multi-service engineering candidate, not a production-ready system. PR #180 is merged. PR #181 is merged on current `main` (merge commit `706fa2b3bed8ee14e35ae4fe703a11c3414bc804`) and adds the first multi-market Commerce schema foundation at revision `20261109_0007`; it does not activate markets or connect live FX, tax, fulfilment, or payment-capability providers. PR #102's substantial multi-market offer/comparison implementation is on a historical branch with conflicting migration history and must be ported after `20261109_0007`. PR #84 and #62 require current-main reconciliation; historical workflow results are not current integration evidence. PR #182 adds BFF consent/revocation and photographed-person rights routes, but does not enable Click It photo processing. No independent production safety provider, trained/calibrated FCI predictor, verified production identity lifecycle, operationally complete infrastructure, managed backup/restore evidence, or end-to-end deployed release is established. **Cirvanna is not production-ready.**

## Contents

- [Product vision](#product-vision)
- [Experience and capability map](#experience-and-capability-map)
- [Architecture and domain ownership](#architecture-and-domain-ownership)
- [Decision and display flow](#decision-and-display-flow)
- [Complementer: Personal Aesthetic Intelligence](#complementer-personal-aesthetic-intelligence)
- [Catalog product intelligence](#catalog-product-intelligence)
- [Modules and services](#modules-and-services)
- [Data ownership and privacy](#data-ownership-and-privacy)
- [Local development](#local-development)
- [Configuration](#configuration)
- [Testing and CI](#testing-and-ci)
- [Deployment](#deployment)
- [System readiness and integration requirements](#system-readiness-and-integration-requirements)
- [Security and responsible AI](#security-and-responsible-ai)
- [Implementation status](#implementation-status)
- [Release roadmap](#release-roadmap)
- [Contribution rules](#contribution-rules)
- [Architecture references](#architecture-references)

## Product vision

Most commerce systems optimize discovery and conversion. Cirvanna aims to evaluate suitability before checkout.

The intended decision combines user-declared preferences, explicit exclusions, occasion and climate context, product facts, fit evidence, and uncertainty. A recommendation score is not permission to show a product. The candidate must pass the canonical decision process, and the user remains the final decision-maker.

### User value

- Build and revise a personal style representation from information the user chooses to provide.
- Coordinate clothing, makeup, fragrance, jewellery, hairstyles, and accessories without treating identity as a defect to correct.
- Discover products through personal preferences, context, and evidence-backed product metadata.
- Understand why a suggestion was made and which information is missing.
- Preview looks only when the relevant visualization capability is actually available.
- Control consent, saved preferences, images, and personal history.

### Merchant value

- Improve product-data quality and relevance.
- Understand suitability signals and customer feedback with appropriate aggregation and privacy safeguards.
- Measure purchase confidence and return outcomes against a documented baseline.
- Run controlled pilots before making commercial performance claims.

Revenue, conversion lift, purchase certainty, and return reduction are hypotheses until measured in a real pilot with a reproducible methodology.

## Experience and capability map

This is the intended product map. A named capability is not automatically a shipped, integrated, or production-enabled feature.

### Identity and personalisation

- **USI — User Style Index:** canonical owner of positive, user-declared style preferences and approved profile updates.
- **NPL — Negative Preference Layer:** canonical owner of explicit hard exclusions and governed negative-preference state. A single rejected suggestion is not automatically a permanent veto.
- **Cultural Identity:** stores user-declared cultural requirements. Culture, ethnicity, religion, and modesty are never inferred from appearance, name, location, or behavioural proxies.
- **TAL — Temporal Learning:** intended owner of consented, versioned preference observations and temporal profile learning.
- **Preference continuity:** intended cross-session continuity, subject to consent, retention, correction, export, and deletion controls.

### Personal Aesthetic Intelligence

Complementer coordinates a complete look from declared preferences and current-look context:

- Fragrance families and scent profiles, occasion, target longevity, intensity, and currency-scoped budget.
- Colour coordination across clothing, makeup, jewellery, and accessories.
- Jewellery and accessories including earrings, necklaces, glasses, and selected accessory categories.
- Aesthetic directions such as minimalist, elegant, classic, romantic, bold, bohemian, streetwear, editorial, and natural.
- Conservative look completion that preserves the user's selected silhouette and statement pieces.
- Explanations grounded in a declared preference, supplied look attribute, or clearly identified styling rule.
- Consent-gated feedback events intended for future learning.

Complementer is advisory. It is not a second profile database, product database, NPL implementation, or final display authority.

### Fit and purchase confidence

- **FCI — Fit Confidence Intelligence:** intended to estimate suitability from actual product and user evidence.
- **CRFP:** one canonical concept with two distinct scopes: marketplace CRFP and system-wide CRFP. The former CFRP spelling was a typo; preserve historical archive filenames for provenance. See the [CRFP scope index](packages/fit-intelligence/crfp/README.md) and [ADR-0003](docs/architecture/adr/ADR-0003-crfp-marketplace-and-system-scopes.md).
- **Purchase-decision support:** communicates evidence and uncertainty; it must not imply certainty where only an estimate exists.
- **Merchant insights:** aggregate reporting subject to data minimisation, privacy controls, and validated metrics.

### Beauty, visualization, and personal experiences

- **DermalSight:** non-diagnostic cosmetic skin-attribute inference. It requires an approved model, signed validation evidence, explicit consent, and privacy controls.
- **Virtual Twin and Virtual Try-On:** guarded API/orchestration foundations exist; actual generation/rendering depends on validated models, consent, asset authorization, and runtime deployment.
- **Living Filters:** face-tracked makeup, hairstyle, and accessory visualization requires licensed runtime/model assets, segmentation/tracking validation, device QA, and offline/CSP/security review.
- **Wardrobe:** intended digitisation and outfit-combination experiences.
- **Experience Lab and moodboards:** intended spaces to explore, save, and compare looks.
- **RadianceScore:** requires a defined construct, validation, calibration, and safe user-facing interpretation before it is treated as a reliable score.
- **PNELLY:** canonical, optional conversational beauty and product-discovery assistant across Marketplace, Virtual Twin and Virtual Try-On. Xari, Tari and Xyra are legacy names during the compatibility migration; `services/xari` is the preserved source path, not a second assistant. Complementer is an optional styling collaborator invoked through PNELLY; neither assistant can override Catalog/Commerce product truth, NPL, FCI or CAL.

### Marketplace and commerce

The target includes canonical product ingestion, product search, merchant offers and variants, product detail, saved products, cart and checkout, payment handoff, inventory invariants, and outcome measurement. API and browser foundations do not prove a live marketplace, account system, payment integration, or durable cart is operational.

## Architecture and domain ownership

Cirvanna uses bounded domains and canonical owners. Cross-service integrations must use authenticated, versioned contracts rather than duplicate business logic.

| Domain | Canonical owner | Responsibility |
|---|---|---|
| Positive style preferences | USI | User-declared and approved positive preferences |
| Hard negative preferences | NPL | Explicit exclusions and governed negative-preference state |
| Temporal learning | CaTaCaCi / TAL | Consented, versioned observations and temporal state |
| Decision arbitration | CaTaCaCi / CAL | Final SHOW, BLOCK, or REVIEW decision for candidates |
| Product identity and product facts | Catalog | Canonical products, attributes, provenance, and version history |
| Personal aesthetic coordination | Recommendation service / Complementer | Advisory styling and look coordination |
| Cosmetic skin attributes | DermalSight | Non-diagnostic skin-attribute inference |
| Commerce transactions | Commerce service | Merchant offers, variants, inventory, orders, and payment invariants |
| Marketplace web boundary | Marketplace BFF | Same-origin UI and tightly allowlisted server-side proxies |

Do not create parallel user-style or product-truth stores inside Complementer. Do not let a recommender, similarity score, merchant assertion, or AI-generated explanation bypass CAL.

### Application and service layers

- The demo web application and Marketplace BFF own presentation and browser-facing boundaries.
- API Gateway coordinates Catalog retrieval and deterministic eligibility/decision contracts.
- Catalog owns canonical product identity and product-version history.
- Recommendation service owns Complementer advisory composition.
- NPL and Cultural Identity services own their respective persistent declarations and signed decision evidence.
- The decision service and gateway use shared domain packages for policy and arbitration.
- Model-backed services run behind bounded APIs with explicit readiness, provenance, timeouts, and failure behavior.

The repository also contains preserved source-intake and candidate implementations. Their presence does not make them canonical runtime dependencies. See the source-lineage and architecture documentation before promoting staged code.

## Decision and display flow

The intended product path is:

1. A trusted application collects explicit user preferences and context.
2. Catalog returns canonical product records and versioned metadata.
3. USI evaluates positive style alignment; NPL evaluates explicit hard exclusions; EEPL checks configured context/eligibility policy; explicit cultural requirements are evaluated by their canonical service.
4. Fit and independent safety evidence are supplied by trusted providers. Missing or untrusted evidence remains UNKNOWN.
5. CaTaCaCi/CAL arbitrates the required evidence and returns SHOW, BLOCK, or REVIEW.
6. A product can be shown only when the decision is SHOW. REVIEW and BLOCK are not displayable; the decision endpoint redacts merchandising fields for non-SHOW results, and discovery omits the complete product/offer objects.
7. Audit records preserve minimal decision metadata without unnecessary user measurements or image content.

The API Gateway resolves end-user subjects through Commerce `GET /me` when `CIRVANNA_REQUIRE_VERIFIED_IDENTITY` is enabled (the default), and rejects a request-body subject that does not match. The setting can be disabled only as an explicit local/test-only opt-out for request-scoped contract tests. Verified profile reads/writes and TAL operations use the gateway's private machine credential to reach the identity-learning service; the service itself is not exposed as a public identity API.

Safety policy and calibrated FCI providers are not configured in this build. Consequently, otherwise eligible products normally remain REVIEW. Fixture-only tests can exercise SHOW, but test fixtures are not live provider evidence.

## Complementer: Personal Aesthetic Intelligence

Complementer is a deterministic advisory composer exposed by the recommendation service.

### Implemented advisory domains

- Fragrance direction: scent families/profiles, occasion, target longevity, intensity, fragrance-free preference, and currency-scoped budget.
- Colour coordination: clothing, makeup, jewellery, and accessory colours, respecting explicit favourites and exclusions.
- Jewellery/accessories: earrings, necklaces, glasses, metals, and selected categories.
- Aesthetic direction: multiple style families, including user-selected cultural styling context.
- Look completion: at most two optional changes while preserving the chosen silhouette and statement pieces.
- Explanations: recommendations reference user-entered preferences or current-look attributes; missing data produces needs_input.
- Feedback event contract: approval/rejection requires explicit personalisation consent and yields a versioned TAL handoff.

### Gateway integration

The API Gateway exposes POST /v1/complementer/recommend as an optional server-to-server proxy to the Complementer service. It uses COMPLEMENTER_SERVICE_URL and COMPLEMENTER_SERVICE_TOKEN, validates the upstream schema and request scope, and wraps results as advisory_only.

The route always sets display_authorized=false and durable_personal_memory=false. It does not return Catalog/Commerce candidates or purchase details. Product discovery and display authorization remain separate through the Catalog and CAL decision path.

The user_id in this request is an opaque caller-supplied request-scope identifier, not a verified end-user identity. It is not used to hydrate a stored profile. Keep the route internal until the gateway is bound to a trusted identity provider.

### Feedback and TAL boundary

The feedback endpoint accepts approval or rejection only when explicit personalisation consent is true. Rejections are soft observations; they do not create NPL hard vetoes. An explicit preference save requires a user-selected value.

Complementer still produces a versioned feedback handoff contract; it does not write directly to a second profile store or automatically train a model. Durable persistence is owned by the identity-learning service and reached through authenticated gateway `/v1/me/*` routes. USI profiles require active `profile_storage` consent. TAL writes require active `personalization` or `style_learning` consent and support idempotent append, append-only same-feature corrections, export, deletion, and expiry purge. A denial or revocation withdraws all active grants for that subject and scope; an older receipt cannot remain active behind a newer withdrawal. These APIs provide durable storage foundations, not proof of a deployed cross-session learning loop or automated personalization improvement.

## Catalog product intelligence

Catalog accepts an optional typed attributes.product_intelligence namespace and validates it before product create/update. The existing canonical product JSON attributes and product-version snapshots own the metadata; no second product database is created.

Supported categories include:

- **Climate compatibility:** hot-humid, hot-dry, temperate, and cool conditions with evidence provenance.
- **Context usage:** intended contexts such as daily, work, evening, formal, date, travel, sport, and special occasion.
- **Cultural usage:** explicitly reviewed product/context tags. These describe the product context, not the buyer's identity.
- **Skin response:** ingredient-label and non-clinical cosmetic-intent/caution metadata with source evidence. This is not a diagnosis or compatibility guarantee.
- **Appearance complement:** shade families, declared undertone matches, finishes, pairing colours, and feature-complement tags.
- **Observed outcomes:** consented aggregate metrics with a minimum sample size of 30, observation window, evidence reference, and limitations.

The 30-observation floor is a disclosure safeguard. It is not differential privacy, proof of representativeness, causal evidence, or a guarantee of future results. Product metadata is not a personalized ranking model. The current API Gateway does not claim that Complementer performs live product ranking from this metadata, and every candidate still needs CAL authorization.

## Modules and services

The actual repository is a multi-service monorepo. Important areas are:

| Path | Role |
|---|---|
| apps/demo-web | Demo and marketplace browser application |
| services/api-gateway | Catalog and Commerce discovery, verified Commerce subject resolution, USI/TAL proxy, signed safety/FCI adapters, CAL arbitration, Complementer advisory proxy |
| services/recommendation-service | Complementer advisory API and domain modules |
| services/catalog-service | Canonical product CRUD, metadata validation, product versions |
| services/identity-learning-service | Durable USI profiles, consent receipts, TAL event persistence, replay/idempotency, correction, export, deletion and retention |
| services/npl-service | Persistent NPL preference ledger and signed evidence API |
| services/cultural-identity-service | Persistent explicit cultural declaration lifecycle and signed evidence |
| services/decision-service | Authenticated eligibility/decision API adapter over canonical domain packages |
| services/dermalsight | Consent- and model-gated non-diagnostic skin analysis |
| services/commerce-service | Merchant offers, inventory, carts, orders, payments, and webhook boundaries |
| services/marketplace-bff | Same-origin marketplace UI and server-side proxy boundary |
| services/vision-intelligence | Vision model runtime and worker-facing APIs |
| services/virtual-twin | Guarded Twin and Click It APIs |
| services/virtual-try-on | Consent-gated try-on orchestration; renderer is not enabled |
| services/wardrobe-service | Wardrobe API foundation |
| services/xari | PNELLY conversational discovery/orchestration (preserved Xari compatibility source path) |
| services/graph-service, perception-service, sync-service | Supporting service foundations; inspect their READMEs before use |
| packages/identity-intelligence | CaTaCaCi, USI, EEPL, TAL event contracts, and cultural identity domain contracts |
| packages/preferences/npl | Canonical NPL policy and evidence contract |
| packages/fit-intelligence | Fit-confidence evidence contracts; no calibrated predictor is registered |
| packages/shared-contracts | Shared contract package |
| packages/wardrobe | Wardrobe domain package |
| integration-staging | Preserved source bundles and candidate implementations; not automatically runtime code |
| tests/architecture | Domain and architecture regression tests |
| docs/architecture | Architecture decisions, boundaries, readiness, and release gates |
| .github/workflows | Service, architecture, container, and contract CI workflows |

## Data ownership and privacy

| Data | Owner | Current persistence status |
|---|---|---|
| Catalog product records and product metadata | Catalog | SQLAlchemy store and product-version snapshots; production DB operation must be verified per environment |
| Negative preferences and corrections | NPL service | PostgreSQL-targeted SQLAlchemy ledger and schema; deploy/restore and trusted identity binding remain gates |
| Cultural declarations and corrections | Cultural Identity service | PostgreSQL-targeted declaration store and schema; deploy/restore and trusted identity binding remain gates |
| Positive style profile | USI / identity-learning-service | Versioned persistent profile API; reads/writes require an active profile_storage consent receipt. Gateway hydration is enabled only when Commerce identity verification is required and configured. |
| Feedback and temporal learning | TAL / identity-learning-service | Durable append-only event store, versioned consent receipts with scope-wide withdrawal, idempotent append, same-feature correction events, export, deletion and expiry purge; production deployment and database restore remain unverified |
| Decision audit | API Gateway | Minimal local SQLite audit file; not a managed production audit backend |
| Skin-analysis images | DermalSight | Read and decoded in memory; not persisted by the service |
| Commerce records | Commerce service | Database-backed code and migration foundations; production DB, identity, payment and restore tests remain gates |

Retention, correction, export, and deletion are implemented at the canonical identity-learning data owner and must remain there. Never persist user profiles or feedback inside Complementer as a shortcut. Deployment, backup/restore, retention scheduling, and operational deletion verification remain release gates.

## Local development

Use Python 3.12 for the current service workflows. This repository does not have a single root requirements file or a one-command local deployment for every microservice. Install dependencies from the service or package being tested.

### Complementer service

From services/recommendation-service:

    python -m pip install -r requirements.txt
    python -m pip check
    python -m compileall -q app tests
    python -m pytest -q

Run the API locally with a random test token of at least 32 bytes:

    COMPLEMENTER_SERVICE_TOKEN='local-random-token-of-at-least-32-bytes' uvicorn app.main:app --host 127.0.0.1 --port 8090

### Catalog service

From services/catalog-service:

    python -m pip install -r requirements.txt
    uvicorn app.main:app --host 127.0.0.1 --port 8081
    python -m pytest -q

For shared environments, set CATALOG_DATABASE_URL to managed PostgreSQL and apply the provided Alembic migration using the documented deployment process. SQLite is for local development and tests.

### USI and TAL persistence service

From services/identity-learning-service:

    python -m pip install -r requirements.txt
    IDENTITY_DATABASE_URL=sqlite:///./identity-local.db IDENTITY_SERVICE_TOKEN='local-random-token-at-least-32-bytes' IDENTITY_AUTO_CREATE_SCHEMA=true uvicorn app.main:app --host 127.0.0.1 --port 8092
    python -m pytest -q

In shared environments, point IDENTITY_DATABASE_URL at the existing approved managed Postgres instance (for example the existing Commerce Postgres database). This service owns only the identity_usi_* and identity_tal_* tables; it does not create a second database. Apply migrations/0001_identity_tal.sql before setting IDENTITY_AUTO_CREATE_SCHEMA=false. Never expose this internal service directly to browsers.

### API Gateway

From services/api-gateway:

    python -m pip install -r requirements.txt
    uvicorn app.main:app --host 127.0.0.1 --port 8080
    python -m pytest tests -q

For verified USI/TAL access, configure COMMERCE_API_URL, IDENTITY_SERVICE_URL, IDENTITY_SERVICE_TOKEN, and CIRVANNA_REQUIRE_VERIFIED_IDENTITY=true. Pass the user's signed Commerce bearer in X-End-User-Authorization; the gateway resolves the subject through Commerce /me and never trusts a request body subject alone. The identity service requires explicit profile_storage consent for USI profile reads/writes and style_learning or personalization consent for TAL event writes.

For marketplace discovery, configure CATALOG_SERVICE_URL, CATALOG_API_TOKEN, and COMMERCE_API_URL. POST /v1/discover joins active Catalog products to purchasable Commerce offers, ranks by weighted explicit USI preferences (not a probability), then sends every candidate through CAL. It returns product/offer details only for CAL SHOW candidates; REVIEW/BLOCK candidates are withheld.

For the Complementer proxy, configure COMPLEMENTER_SERVICE_URL=http://127.0.0.1:8090 and the same COMPLEMENTER_SERVICE_TOKEN in the gateway and Complementer processes. Local HTTP is permitted only for loopback hosts; remote internal service URLs must use HTTPS.

### Other service checks

- NPL: from services/npl-service install requirements.txt and run python -m pytest -q. Set NPL_DATABASE_URL to PostgreSQL outside test mode.
- Cultural Identity: from services/cultural-identity-service install requirements.txt and run python -m pytest -q. Set CULTURAL_IDENTITY_DATABASE_URL to PostgreSQL outside test mode.
- Decision service: from services/decision-service install requirements.txt and run python -m pytest -q. Its signed evidence keys must be independently provisioned.
- DermalSight: from services/dermalsight install requirements-dev.txt and run pytest -q. Actual inference is unavailable until a verified ONNX model and signed validation report are provided.
- Commerce, marketplace BFF, Vision Intelligence, Twin, Try-On, Wardrobe, and PNELLY (source path `services/xari`): follow the service-specific README and workflow. Do not assume a model/adapter is available because the API code exists.

## Configuration

The root .env.example is a development template for common platform and Commerce settings. It is not a complete secret manifest for every service. Use service-specific configuration documentation and supply secrets through environment variables or a secret manager. Never commit a populated .env file.

### Complementer and gateway

| Variable | Purpose |
|---|---|
| CIRVANNA_API_TOKEN | Inbound internal API Gateway bearer token |
| CIRVANNA_AUDIT_DB | Local/staging SQLite decision-audit path |
| COMPLEMENTER_SERVICE_URL | Trusted internal Complementer API base URL |
| COMPLEMENTER_SERVICE_TOKEN | Complementer internal bearer token, at least 32 bytes |
| CIRVANNA_POLICY_VERSION | Decision policy version |
| CIRVANNA_REQUIRED_CONTEXT_FIELDS | EEPL fields required before context can pass |
| CIRVANNA_REQUIRED_PRODUCT_ATTRIBUTES | Catalog attributes required for metadata completeness |

### Catalog and NPL

| Variable | Purpose |
|---|---|
| CATALOG_DATABASE_URL | Catalog database URL; PostgreSQL for shared/production use |
| CATALOG_READ_TOKEN / CATALOG_WRITE_TOKEN | Separate production read/write credentials |
| CATALOG_API_TOKEN | Gateway/Commerce Catalog read credential |
| NPL_DATABASE_URL | NPL database URL; PostgreSQL for shared/production use |
| NPL_SERVICE_TOKEN | Internal NPL API bearer token, at least 32 bytes |
| NPL_SERVICE_URL | Trusted internal NPL service URL |
| NPL_EVIDENCE_HMAC_SECRET | HMAC key shared only by the trusted NPL provider and consumer |

### Cultural Identity

| Variable | Purpose |
|---|---|
| CULTURAL_IDENTITY_DATABASE_URL | Cultural declaration database URL |
| CULTURAL_IDENTITY_SERVICE_URL | Trusted internal declaration service URL |
| CULTURAL_IDENTITY_SERVICE_TOKEN | Internal bearer token, at least 32 bytes |
| CULTURAL_IDENTITY_HMAC_SECRET | Candidate-bound evidence HMAC key |

### DermalSight

| Variable | Purpose |
|---|---|
| DERMALSIGHT_API_TOKEN | Internal bearer token |
| DERMALSIGHT_MODEL_PATH | Approved ONNX model artifact path |
| DERMALSIGHT_MODEL_MANIFEST_PATH | Model preprocessing/output manifest |
| DERMALSIGHT_VALIDATION_REPORT_PATH | Signed release-evidence report |
| DERMALSIGHT_VALIDATION_SIGNING_KEY | Private report HMAC key, at least 32 bytes |

DermalSight remains not-ready when model assets, manifest, report, signing key, or API token are absent or invalid.

### USI and TAL

| Variable | Purpose |
|---|---|
| IDENTITY_DATABASE_URL | Existing approved shared managed Postgres URL; use the same database instance already provisioned for Commerce rather than creating a duplicate |
| IDENTITY_AUTO_CREATE_SCHEMA | Local/test only; false in deployed environments after reviewed SQL migration |
| IDENTITY_SERVICE_URL | Private USI/TAL service URL |
| IDENTITY_SERVICE_TOKEN | Gateway-to-identity service bearer token, at least 32 bytes |
| IDENTITY_CRON_TOKEN | Separate retention-job token, at least 32 bytes |
| CIRVANNA_REQUIRE_VERIFIED_IDENTITY | Set true to require Commerce /me subject verification before decision/discovery and profile/TAL operations |
| COMMERCE_API_URL | Trusted Commerce URL used for /me identity verification and live offers |

USI profile writes and reads require an active profile_storage consent receipt. TAL event writes require active personalization or style_learning consent. Consent receipts are versioned; revocation blocks subsequent writes. Corrections are append-only and refer to the superseded event. Export and deletion are available through authenticated /v1/me routes. The deletion receipt stores only a one-way subject digest and deletion counts.

### Safety and FCI evidence providers

| Variable | Purpose |
|---|---|
| SAFETY_SERVICE_URL / SAFETY_SERVICE_TOKEN | Independent product-safety provider endpoint and service credential |
| SAFETY_EVIDENCE_HMAC_SECRET | Candidate-bound provider response signature key |
| SAFETY_VALIDATION_HMAC_SECRET | Separate independent-validation attestation signature key |
| SAFETY_VALIDATION_REPORT_SHA256 | Pinned SHA-256 of the approved safety validation report |
| FCI_SERVICE_URL / FCI_SERVICE_TOKEN | Calibrated fit-confidence provider endpoint and service credential |
| FCI_EVIDENCE_HMAC_SECRET | Candidate-bound FCI response signature key |
| FCI_VALIDATION_HMAC_SECRET | Separate independent-validation attestation signature key |
| FCI_VALIDATION_REPORT_SHA256 | Pinned SHA-256 of the approved FCI validation report |

Each provider response must be bound to request, verified subject, candidate, and canonical product snapshot. Its validation manifest must be signed by a distinct evaluator, match the pinned report hash/model/scope, and remain within its validity window. Provider adapters and tests are implemented; no real provider, validation report, or signing keys are configured in this repository. Until provisioned and verified, the gateway returns UNKNOWN evidence and CAL must return REVIEW.

### Commerce and marketplace

Commerce requires its own database, identity, and payment configuration. See services/commerce-service/README.md and the root .env.example for COMMERCE_DATABASE_URL, COMMERCE_AUTH_MODE, COMMERCE_JWT_JWKS_URL, COMMERCE_JWT_ISSUER, COMMERCE_JWT_AUDIENCE, Stripe secrets, and checkout settings. Production authentication must use provider-issued RS256/JWKS tokens; local HS256 is development/test-only. Marketplace BFF requires trusted Catalog and Commerce URLs and does not issue user identity.

## Testing and CI

Run the relevant service tests plus architecture and security checks:

    python scripts/validate_architecture.py
    python -m unittest discover -s tests/architecture -v
    python scripts/scan_source_secrets.py

Service workflows are path-scoped. The Decision Gateway workflow runs API/contract tests, container build, architecture checks, and source secret scanning. It also triggers when the Complementer service changes because the gateway proxy depends on its response contract. The Complementer workflow runs dependency checks, compileall, and its API/domain tests. Catalog, NPL, Cultural Identity, DermalSight, marketplace, Commerce, Vision Intelligence, Twin, Try-On, Wardrobe, and the PNELLY assistant each have a separate workflow. The PNELLY workflow file is still named `xari-tests.yml` to preserve current path filters; renaming it is a separate migration.

For every CI report, record the branch, commit SHA, workflow/job, exact test result, warnings, skips, and limitations. A passing unit suite or container build does not prove production readiness, model quality, live database health, cross-service identity, backup recovery, or commercial outcomes.

## Deployment

The canonical provider-neutral service and dependency inventory is [infrastructure/deployment/canonical-stack.json](infrastructure/deployment/canonical-stack.json). It identifies the intended public BFF boundary, service owners, container build contexts, data-store owners, provider dependencies and release gates. It is an inventory and validation artifact only—not an executable deployment, a configured cloud environment, or evidence that a single canonical release is running. See [the system readiness register](docs/architecture/system-readiness-and-quality-2026-11-09.md).


Deploy bounded services independently. Use the build context expected by each Dockerfile:

- API Gateway — build from the repository root because the image copies shared domain packages:

      docker build -f services/api-gateway/Dockerfile -t cirvanna-decision-gateway .

- Complementer — build with the recommendation-service directory as context:

      cd services/recommendation-service
      docker build -f Dockerfile -t cirvanna-complementer .

- Catalog — build with the catalog-service directory as context:

      cd services/catalog-service
      docker build -f Dockerfile -t cirvanna-catalog .


Before a shared or production deployment:

1. Provision managed databases according to service ownership. The identity-learning service uses its own `identity_usi_*` and `identity_tal_*` table namespace in the already approved PostgreSQL instance; do not create a duplicate database for it. Provision secrets in a secret manager.
2. Apply reviewed migrations, including `services/identity-learning-service/migrations/0001_identity_tal.sql`; do not rely on automatic schema creation in production.
3. Configure private service networking, HTTPS, least-privilege service tokens, and independently rotated signing keys.
4. Verify /health, /ready, and /capabilities for each service. Liveness is not readiness.
5. Run authenticated staging smoke tests across Commerce `/me`, gateway, identity-learning, Catalog, Commerce offers, NPL, Cultural Identity, evidence providers, and CAL. Confirm non-SHOW candidates never leak product or offer details.
6. Verify audit persistence, PostgreSQL backup/restore, deletion/retention, and concurrency behavior.
7. Run load, timeout, dependency-failure, alerting, rollback, and security exercises.
8. Promote features only after evidence from the actual deployed environment is recorded.

There is no verified production deployment or full release certification represented by this repository status.

## Security and responsible AI

- Service bearer tokens are machine credentials, not end-user identity.
- Bind subjects to verified identity-provider principals before reading or mutating user-owned data. Never trust arbitrary user IDs from public clients.
- Enforce tenant isolation and least privilege at every service boundary.
- Use separate secrets for API authentication and evidence signing; rotate exposed credentials.
- Keep Catalog write credentials out of the gateway and browser.
- Keep images and sensitive preference values out of logs and traces.
- Use explicit, revocable consent for image processing and personalisation.
- Do not infer culture, religion, ethnicity, gender, modesty, skin tone, undertone, or face geometry from appearance, names, or location.
- Treat DermalSight outputs as cosmetic attributes, not diagnosis or treatment advice.
- Do not infer menstrual or hormonal context. Any future use must be optional, user-reported, separately consented, and privacy-reviewed.
- A merchant assertion or aggregate outcome is not laboratory evidence or a causal claim.
- Unknown, incomplete, invalid, or untrusted evidence must fail closed to REVIEW or an unavailable response.
- Never present a model narrative, heuristic, or visual score as a validated forecast.

## System readiness and integration requirements

The detailed, versioned gap register is [docs/architecture/system-readiness-and-quality-2026-11-09.md](docs/architecture/system-readiness-and-quality-2026-11-09.md). It governs the current integration order and release boundaries.

- **FCI predictive validity:** the current package has an evidence contract and offline calibration metrics, not a trained predictor. A proposed subject-disjoint, out-of-time validator evaluates real fit outcomes; its synthetic CI fixtures are not model evidence and a candidate pass is not production approval.
- **Infrastructure:** container builds and readiness contracts do not prove provider operation, provisioned databases, backup/restore, monitoring, alerting, on-call, rollback or a completed staging journey.
- **Decision quality:** CAL must remain the sole SHOW/BLOCK/REVIEW authority. Decision receipts need complete gate/version provenance and must be durably committed before product details are released. Offline metrics are not live monitoring.
- **Canonical deployment:** the service inventory is provider-neutral. One exact-commit deployment with immutable image digests, private service topology, database revisions, provider versions, monitoring and recovery ownership remains unverified.
- **Inter-model calibration:** PNELLY, Complementer and baseline scores are not directly comparable probabilities. Each model requires independent calibration on a separate calibration split and comparison on the same untouched candidate pools, human-reviewed outcomes and market/category slices.
- **Privacy and Click It:** purpose consent, revocation, deletion/retention, rights intake, child-specific safeguards and public-media route coverage are separate release gates. Click It remains disabled until real provider operations and every publication/delivery path are verified.
- **Multi-market marketplace:** #181 supplies schema foundations only. #102 must be rebuilt on current main with a single migration lineage and real integration across Catalog, Commerce, Marketplace BFF, provider evidence, comparison and checkout.

## Implementation status

Status below reflects repository contracts and code, not production deployment.

| Area | Implemented evidence | Still required |
|---|---|---|
| Complementer | Modular stateless advisory API; fragrance, colour, accessories, aesthetic/look completion; consent-gated feedback handoff; gateway advisory proxy | Automatic feedback-to-TAL delivery and validated cross-session recommendation improvement; complete user-facing end-to-end journey |
| USI | Versioned persistent profile API, explicit positive-preference alignment, profile_storage-consented reads/writes, Commerce /me subject binding and gateway hydration; verified identity required by default | Production PostgreSQL migration/restore, real Commerce OIDC/JWKS configuration and deployed E2E |
| NPL | Domain rules plus database-backed PostgreSQL-targeted service; candidate-bound signed evidence; optional API Gateway provider integration | Deployed PostgreSQL, backup/restore, trusted identity binding, production key rotation and E2E |
| TAL | Durable API/schema for scoped consent receipts, idempotent event append, append-only same-feature corrections, expiry purge, export and deletion; scope-wide withdrawal revokes all active grants; gateway routes bind requests to verified Commerce subjects | Production PostgreSQL provisioning, migration execution, backup/restore evidence, scheduled retention, security review and deployed E2E |
| Catalog | Canonical product API, version snapshots, optional typed product-intelligence metadata validation | Production DB and restore evidence, editorial/provenance operations, live personalised ranking |
| FCI | Typed fit estimate, evidence-coverage contract and offline calibration metrics; an offline predictive release validator is proposed in the current architecture work | Trained and independently validated predictor, consented fit outcomes, temporal and subject-disjoint holdouts, subgroup/market calibration, signed model/report release and live provider operations |
| CAL / decision gateway | Deterministic arbitration; verified-subject Catalog/Commerce discovery and weighted explicit-preference ranking; signed candidate-bound evidence adapters; only CAL SHOW candidates return product/offer details | Real independently validated safety and calibrated FCI providers/report attestations, managed audit, deployed end-to-end display enforcement |
| Decision service | Authenticated API adapter and signed evidence verification | Trusted live evidence providers, managed audit/replay, identity binding |
| Cultural Identity | Persistent explicit declaration service and signed candidate-bound evidence contract | Deployed DB, identity binding, key rotation, end-to-end operation |
| DermalSight | Consent/image validation, ONNX adapter, signed model release gate | Approved model artifact, representative evaluation, validated inference, deployment readiness |
| Longitudinal skin forecast | Explicitly disabled in capability contract | Licensed repeated-measures dataset, separate temporal model, calibrated ranges, subgroup validation, privacy review |
| Commerce / marketplace | Backend APIs and BFF; PR #181 merged the multi-market provider-evidence schema at `20261109_0007` | Port #102 after the current schema with a new migration; wire provider ingestion, market activation, localized prices, like-for-like offers, fulfilment/tax and checkout revalidation; prove live staging integration |
| Twin / Try-On / Living Filters | Guarded service and orchestration foundations | Consent/asset authorization, validated renderer/tracking models, licensed assets, device/quality QA |
| Production operations | CI workflows, container builds, readiness contracts and a provider-neutral canonical service inventory | Select and provision one deployment environment; real provider operations; managed DB/migration/restore; durable decision audit; central monitoring/alerts; key rotation; staging smoke/load/failure tests; rollback and on-call sign-off |

### PR #72

The Complementer and Catalog product-intelligence work was merged through [PR #72](https://github.com/cirvannaco-png/Cirvanna-demo/pull/72). Its merge does not certify production readiness or imply a deployment. Subsequent identity/TAL, marketplace-discovery, and provider-adapter work is being developed on a separate reviewable branch.

## Release roadmap

1. **Identity and trusted profile hydration:** configure and verify Commerce's production OIDC/JWKS issuer, deploy the identity-learning service on the existing approved Postgres instance, run the SQL migration, and complete tenant-isolation tests.
2. **Canonical temporal learning:** verify consent receipt provenance, retention operations, backup/restore, correction/export/deletion behavior and operational audit in staging. Keep rejected suggestions soft unless the user explicitly creates a hard exclusion.
3. **Marketplace decision path:** deploy and exercise Catalog/Commerce retrieval, ranking and CAL-gated product/offer release with real service credentials and verified user sessions.
4. **Fit and safety evidence:** provision independent providers, validate evaluator signatures/report hashes and model scope, then run calibration, subgroup, drift, and temporal holdout review before any SHOW decisions.
5. **DermalSight longitudinal research:** acquire licensed repeated-measures data, build a distinct model, validate temporal holdouts and subgroup calibration, and keep sensitive context optional and separately consented.
6. **Production hardening:** select the correct Render workspace, provision/reuse the approved database, apply migrations, verify backup/restore, rotate secrets, configure managed audit and monitoring, run staging smoke/load/failure tests, and prove rollback.

## Contribution rules

Start with the [Source of truth and contributor guide](docs/architecture/source-of-truth-and-contributor-guide.md), the [runtime source registry](docs/architecture/runtime-source-registry.json), and the [CRFP scope ADR](docs/architecture/adr/ADR-0003-crfp-marketplace-and-system-scopes.md). Canonical source, candidate, experimental, archived, and scaffold paths are deliberately distinct; never promote by copying or renaming alone.

1. Inspect the current branch, code, architecture owner, service contract, and tests before editing.
2. Prefer one small, complete, testable integration over disconnected feature stubs.
3. Do not add a duplicate user, product, preference, or audit database when a canonical owner exists.
4. Preserve API compatibility unless a reviewed breaking change is intended.
5. Add regression tests for normal, boundary, conflict, identity, consent, and dependency-failure cases.
6. Do not fabricate model results, metrics, evidence, test results, or deployment status.
7. Keep secrets and customer data out of Git.
8. Document configuration, limitations, migration impact, and rollback.
9. Run actual CI and report its commit SHA and limitations.
10. Update this README when verified implementation status changes.
11. Run the source-boundary and release-ledger validators; state their limits and do not mark a release gate passed without evidence for the exact commit.

## Architecture references

- [Complementer, Marketplace Product Intelligence and Skin-State Forecasting](docs/architecture/complementer-product-intelligence-skin-forecast.md)
- [PNELLY canonical assistant identity and Xari compatibility migration](docs/architecture/adr/ADR-0010-pnelly-canonical-assistant-identity.md)
- [Historical Xari-assisted discovery and marketplace Try-On ownership](docs/architecture/adr/ADR-0005-xari-assisted-discovery-marketplace-try-on.md)
- [Decision flow](docs/architecture/decision-flow.md)
- [CaTaCaCi decision contract ADR](docs/architecture/adr/ADR-0001-catacaci-decision-contract.md)
- [Feature spine readiness](docs/architecture/feature-spine-readiness-2026-10-23.md)
- [Monorepo governance](docs/architecture/monorepo-governance.md)
- [Source of truth and contributor guide](docs/architecture/source-of-truth-and-contributor-guide.md)
- [Runtime source registry](docs/architecture/runtime-source-registry.json)
- [CRFP marketplace/system-wide scope ADR](docs/architecture/adr/ADR-0003-crfp-marketplace-and-system-scopes.md)
- [Production release evidence gates](docs/release/README.md)
- [System readiness, FCI validity, decision monitoring and deployment gaps](docs/architecture/system-readiness-and-quality-2026-11-09.md)
- [Inter-model recommendation calibration protocol](docs/evaluation/inter-model-recommendation-calibration.md)
- [Canonical provider-neutral deployment inventory](infrastructure/deployment/canonical-stack.json)
- [Catalog](services/catalog-service/README.md)
- [Complementer](services/recommendation-service/README.md)
- [NPL](services/npl-service/README.md)
- [Cultural Identity](services/cultural-identity-service/README.md)
- [DermalSight](services/dermalsight/README.md)
- [API Gateway](services/api-gateway/README.md)
- [Commerce](services/commerce-service/README.md)
- [Marketplace BFF](services/marketplace-bff/README.md)

---

**Final principle:** the README describes the system honestly; executable code and reproducible evidence establish what is built. Cirvanna should grow through clear ownership, validated contracts, integrated user journeys, and measured outcomes—not feature labels that outrun the software.
