# Cirvanna

**Computing purchase certainty before checkout.**

Cirvanna is an identity-first beauty, fashion, fit, and commerce-intelligence platform. It is designed to help people evaluate whether a product or complete look fits their declared preferences, context, and available evidence before they buy. For merchants, the goal is to improve product relevance and measure avoidable returns through controlled pilots—not to promise unverified conversion or return-reduction gains.

> **Engineering status — 2 November 2026:** Cirvanna is an active, multi-service codebase with tested domain contracts and several runnable APIs. The current Complementer expansion and Catalog product-intelligence work are on [draft PR #72](https://github.com/cirvannaco-png/Cirvanna-demo/pull/72), branch \`feature/complementer-agent\`. Its relevant GitHub Actions checks passed on head \`7278e59df426ea344f54cdee6a93d557a2f07d93\`, including 22 Complementer tests and the Catalog, architecture, DermalSight, Vision Intelligence, marketplace-contract, and related service checks. PR #72 is **open, draft, and unmerged**. These results validate the tested commit and contracts; they do not certify a live production deployment or complete user journey. Durable TAL preference memory, trusted identity binding for Complementer, end-to-end marketplace ranking with CAL-gated display, and validated longitudinal skin forecasting remain incomplete. DermalSight's current capability contract explicitly reports longitudinal forecasting as unavailable. **Cirvanna is not production-ready.**

---

## Contents

- [Product vision](#product-vision)
- [Experience and capability map](#experience-and-capability-map)
- [System architecture and ownership](#system-architecture-and-ownership)
- [Complementer: Personal Aesthetic Intelligence](#complementer-personal-aesthetic-intelligence)
- [Marketplace product intelligence](#marketplace-product-intelligence)
- [CaTaCaCi decision governance](#catacaci-decision-governance)
- [Skin-state forecasting](#skin-state-forecasting)
- [Repository structure](#repository-structure)
- [Local development and validation](#local-development-and-validation)
- [Privacy, security, and responsible AI](#privacy-security-and-responsible-ai)
- [Implementation status](#implementation-status)
- [Roadmap and release gates](#roadmap-and-release-gates)
- [Contribution and engineering rules](#contribution-and-engineering-rules)
- [Architecture references](#architecture-references)

## Product vision

Most commerce systems optimize discovery and clicks. Cirvanna's intended distinction is to evaluate suitability before checkout.

The decision should combine user-declared preferences, explicit exclusions, occasion and climate context, product facts, available fit evidence, and uncertainty. A recommendation score is not permission to show a product. Candidates must pass the canonical decision process, and the user remains the final decision-maker.

### User value

- Build and revise a personal style representation from information the user chooses to provide.
- Coordinate clothing, makeup, fragrance, jewellery, hairstyles, and accessories without flattening individual identity.
- Discover products using climate, occasion, product attributes, and personal preferences.
- Understand why a suggestion was made and what evidence is missing.
- Preview looks only where the required visualization capability is genuinely available.
- Control consent, saved preferences, images, and personal history.

### Merchant value

- Improve product-data quality and relevance.
- Understand suitability signals and customer feedback with appropriate aggregation and privacy safeguards.
- Measure purchase confidence and return outcomes against a documented baseline.
- Run controlled pilots before making commercial performance claims.

Revenue, conversion lift, purchase certainty, and return reduction are hypotheses until measured in a real pilot with a reproducible methodology.

## Experience and capability map

This is the intended product map. A named capability is not automatically a shipped, connected, or production-enabled feature.

### Identity and personalisation

- **USI — User Style Index:** canonical owner of positive, user-declared style preferences and approved profile updates.
- **NPL — Negative Preference Layer:** canonical owner of explicit hard exclusions and governed negative preferences. A single rejected suggestion is not automatically a permanent veto.
- **Cultural context:** uses context explicitly selected by the user. Cirvanna must not infer culture, ethnicity, religion, or identity from a face, name, location, or shopping behaviour.
- **TAL — Temporal Learning:** intended owner of consented, versioned preference observations and temporal profile learning.
- **Revival / preference continuity:** intended cross-session continuity, subject to consent, retention, correction, export, and deletion controls.

### Personal Aesthetic Intelligence

Complementer coordinates a complete look using declared preferences and current-look information:

- Fragrance families and scent profiles, occasion, target longevity, intensity, and currency-scoped budget.
- Colour coordination across clothing, makeup, jewellery, and accessories.
- Jewellery and accessories including earrings, necklaces, glasses, and selected accessory categories.
- Aesthetic directions such as minimalist, elegant, classic, romantic, bold, bohemian, streetwear, editorial, and natural.
- Conservative look completion that preserves the user's existing silhouette and statement pieces.
- Explainable recommendations grounded in a stated preference, supplied look attribute, or clearly identified styling rule.
- Consent-gated feedback events intended for future preference learning.

Complementer is advisory. It must not become a second user-profile database, product database, NPL implementation, or final display authority.

### Fit and purchase confidence

- **FCI — Fit Confidence Intelligence:** intended to estimate suitability from actual product and user evidence.
- **CRFP / CFRP:** source material uses both names. Resolve their definitions and contracts before designating one canonical implementation.
- **Purchase-decision support:** communicates evidence and uncertainty; it must not imply certainty where only an estimate exists.
- **Merchant insights:** aggregate reporting subject to data minimisation, privacy controls, and measured definitions.

### Beauty, visualization, and personal experiences

- **DermalSight:** non-diagnostic cosmetic skin-attribute analysis. It requires a validated model, signed validation report, explicit consent, and appropriate privacy controls.
- **Virtual Twin and Virtual Try-On:** guarded orchestration and API foundations exist; actual generation/rendering remains dependent on validated model adapters, consent, asset authorization, and runtime deployment.
- **Living Filters:** face-tracked makeup, hairstyle, and accessory visualization requires verified runtime/model assets, licensing, offline/CSP review, and device QA.
- **Wardrobe:** intended digitisation and outfit-combination experiences.
- **Experience Lab and moodboards:** intended spaces to explore, save, and compare looks.
- **RadianceScore:** requires a defined construct, validation, calibration, and safe user-facing interpretation before it is treated as a reliable score.
- **Xari:** intended conversational beauty and product-discovery assistant. Tool permissions and downstream actions must be bounded by service contracts.

### Marketplace and commerce

The target includes canonical catalog ingestion, product search, product detail, merchant onboarding, offer/variant identity, saved products, cart and checkout, payment handoff, inventory invariants, and outcome measurement. Service code and browser/BFF foundations do not prove that a live marketplace, account system, payment integration, or durable cart is operational.

## System architecture and ownership

The architecture uses bounded domains and canonical owners. Cross-service integrations should use authenticated, versioned contracts rather than duplicated business logic.

| Domain | Canonical owner | Responsibility |
|---|---|---|
| Positive style preferences | USI | User-declared and approved positive preferences |
| Hard negative preferences | NPL | Explicit exclusions and governed negative-preference state |
| Temporal preference learning | CaTaCaCi / TAL | Consent-bound, versioned observations and temporal state |
| Decision arbitration | CaTaCaCi / CAL | Final SHOW, BLOCK, or REVIEW decision for candidates |
| Product identity and product facts | Catalog | Canonical products, attributes, provenance, and version history |
| Personal aesthetic coordination | Recommendation service / Complementer | Advisory styling and look coordination |
| Cosmetic skin attributes | DermalSight | Non-diagnostic skin-attribute inference |
| Final candidate display | CaTaCaCi / CAL | The final display authorization boundary |
| Commerce transactions | Commerce service | Order, payment, inventory, and transaction invariants |

Do not create parallel user-style or product truth stores inside Complementer. Do not let recommendation scores bypass CAL. Do not treat catalog metadata, merchant assertions, or aggregate outcomes as display authorization.

### Request and decision flow

The target flow is:

1. Authenticate the caller and derive the subject identity from a trusted credential—not from an untrusted user-supplied identifier.
2. Validate the request, assign a correlation ID, and enforce consent and eligibility requirements.
3. Load canonical user preferences from their owning services.
4. Retrieve canonical product and offer records from Catalog.
5. Evaluate explicit NPL exclusions and relevant context constraints.
6. Evaluate fit and other evidence only when the relevant provider is configured and validated.
7. Ask CAL to arbitrate the candidate and return SHOW, BLOCK, or REVIEW with reason codes.
8. Display only candidates authorized by CAL.
9. Record the minimum auditable decision metadata required for permitted operations and learning.
10. Process feedback through consented, reversible, idempotent workflows.

The exact integration path is not yet complete end to end. A README description does not enforce this flow; executable contracts, service authentication, integration tests, and production evidence must do so.

## Complementer: Personal Aesthetic Intelligence

Complementer v2 is implemented as advisory code on PR #72. It is designed as a coordinator, not an autonomous identity authority.

### Current advisory capabilities

- **Fragrance:** declared scent families/profiles, occasion, desired longevity, intensity, and budget with an explicit currency. Desired longevity is a preference target, not a guarantee of product performance.
- **Colour:** coordinates supplied clothing, makeup, jewellery, and accessory colours. Reasons should distinguish user preferences from curated harmony rules.
- **Jewellery and accessories:** earrings, necklaces, glasses, and user-selected accessory categories. Face shape is optional and self-reported; the service does not infer it from images.
- **Aesthetic direction:** minimalist, elegant, classic, romantic, bold, bohemian, streetwear, editorial, natural, and user-selected cultural context.
- **Look completion:** at most two optional changes, with an explicit statement of what should be preserved. Existing identity and silhouette are not defects to correct.
- **Explanations:** every recommendation should be tied to a declared preference or supplied look attribute. Missing inputs should produce \`needs_input\`, not invented personal facts.

### Feedback and learning boundary

The feedback contract accepts approval/rejection with explicit personalisation consent. A rejection is a soft observation; it must not silently create a permanent NPL hard veto. An optional save-preference action requires a value explicitly chosen by the user.

The current Complementer feedback implementation creates a versioned TAL handoff event and reports that persistence is not configured. The canonical TAL module currently provides an in-memory deterministic event ledger for contract testing; it is not durable storage. NPL has a separate authenticated, database-backed service, but NPL is not a substitute for TAL and must not receive every rejection as a hard exclusion.

Before this capability can be described as persistent personal memory, the platform needs trusted subject binding, canonical TAL persistence/replay, consent receipts, retention, export, correction, deletion, idempotency, audit, and tested cross-service integration. Those controls are not complete.

See [Complementer, Marketplace Product Intelligence and Skin-State Forecasting](docs/architecture/complementer-product-intelligence-skin-forecast.md).

## Marketplace product intelligence

Catalog's optional \`attributes.product_intelligence\` contract adds typed, evidence-backed product metadata to the canonical product record. The existing product attributes and version snapshots own this data; PR #72 does not introduce a parallel product database or a new migration for this namespace.

Supported metadata categories include:

- **Climate compatibility:** supported climate-condition tags such as hot-humid, hot-dry, temperate, and cool, with provenance.
- **Context usage:** intended contexts such as daily, work, evening, formal, travel, or sport.
- **Cultural usage:** editorially reviewed product/context tags. These describe a product or styling context; they do not classify the buyer.
- **Skin response:** ingredient-label and non-clinical cosmetic-intent/caution metadata with source evidence. This is not diagnosis or a guarantee of compatibility.
- **Appearance complement:** shade families, declared undertone matches, finishes, pairing colours, and feature-complement tags.
- **Observed outcomes:** consented aggregate metrics with a minimum cohort of 30, an observation window, source reference, and stated limitations.

The cohort threshold is a disclosure safeguard. It is not differential privacy, proof of representativeness, causal evidence, or a guarantee of future results. Merchant claims require provenance and review. Product candidates must still pass the canonical decision pipeline and CAL before display.

Live personalised Catalog/Commerce ranking, exact candidate-bound CAL authorization, and a complete user journey are not established by metadata validation alone.

## CaTaCaCi decision governance

CaTaCaCi is the decision-governance core. CAL is not merely a weighted recommender.

- **CAL — Cognitive Arbitration Layer:** resolves conflicts and determines SHOW, BLOCK, or REVIEW according to explicit policy and evidence.
- **TAL — Temporal Learning:** manages consented preference observations over time.
- **CAM — Counterfactual Auditing:** intended to preserve decision evidence and support analysis of alternatives.
- **CIL — Collective Intelligence:** intended to govern aggregate signals without overriding individual constraints.
- **VSL — Value System Layer:** intended to govern controlled, versioned changes to decision values.

The repository contains a deterministic CAL arbitration kernel and initial TAL/CAM/CIL/VSL domain contracts. The TAL implementation currently available in the shared package is an in-memory contract ledger; it does not provide durable personal memory. Full evidence receipts, replay, and production governance workflows remain incomplete.

### Arbitration invariants

1. Legal, safety, consent, and eligibility constraints take precedence over recommendation scores.
2. An explicit hard negative cannot be overridden by trends, popularity, or collaborative signals.
3. Cultural requirements are user-directed and must not be inferred.
4. Fit confidence must reflect real evidence and expose uncertainty.
5. Missing or conflicting evidence produces REVIEW or a safe fallback, not a fabricated positive.
6. Learning must not silently weaken explicit constraints.
7. Arbitration policy and model changes must be versioned and regression-tested.

## Skin-state forecasting

**Longitudinal skin-state forecasting is unavailable.** DermalSight's current \`/capabilities\` contract explicitly reports \`longitudinal_forecasting: false\` and an unavailable status until a validated longitudinal model and dataset exist.

A future scenario experience may compare a baseline with user-selected conditions over a stated horizon, including exact product/variant, ingredient-label facts, application frequency, humidity, self-reported sleep disruption, and optional user-reported cycle context. These inputs are not currently a validated forecasting model.

Before forecast outputs can be enabled, DermalSight requires:

1. A licensed longitudinal dataset with repeated measurements, exposure details, baseline variation, and consent for the intended use.
2. A distinct time-series model with versioned weights, preprocessing, and reproducible validation.
3. Calibration and error analysis across relevant skin-tone groups, devices, lighting, climate/humidity, sleep patterns, and coverage limitations.
4. Calibrated ranges with uncertainty, horizon, evidence coverage, and model/data versions—not deterministic promises or causal claims.
5. Temporal holdouts, a no-change baseline, drift monitoring, and independent review of user-facing claims.
6. Explicit revocable consent, minimised sensitive inputs, retention/deletion controls, access logging, and privacy/threat assessment.

Cycle or hormonal context is sensitive. It must be optional, separately consented, user-reported, minimised, excluded from advertising, and never inferred from a face, name, calendar, or behaviour. Cirvanna must not diagnose hormonal imbalance. A language-model narrative or heuristic score is not a substitute for a validated forecast.

## Repository structure

The repository contains both canonical application code and preserved source-intake material. The latter is evidence for migration and comparison; it must not be treated as a production runtime merely because it exists.

Important areas include:

- \`apps/\` — demo and user-facing application code.
- \`services/api-gateway/\` — authenticated API gateway and decision-pipeline integration.
- \`services/catalog-service/\` — canonical product catalog API and product metadata validation.
- \`services/commerce-service/\` — commerce domain service.
- \`services/decision-service/\` — decision API and governance integration.
- \`services/npl-service/\` — authenticated persistent NPL service.
- \`services/recommendation-service/\` — Complementer advisory service.
- \`services/dermalsight/\` — non-diagnostic cosmetic skin-analysis API and model adapter.
- \`services/virtual-twin/\`, \`services/virtual-try-on/\`, \`services/wardrobe-service/\`, \`services/xari/\` — experience and orchestration services.
- \`packages/identity-intelligence/\` — USI, CaTaCaCi, decision and cultural-identity domain packages.
- \`packages/preferences/npl/\` — canonical NPL domain logic and evidence contracts.
- \`packages/fit-intelligence/\` — fit-confidence and CFRP candidate work.
- \`packages/shared-contracts/\` — shared API/domain contracts.
- \`integration-staging/source-intake/\` and \`integration-staging/source-candidates/\` — preserved source material and candidate implementations; not automatically runtime code.
- \`docs/architecture/\` — architecture decisions, service boundaries, and release gates.
- \`.github/workflows/\` — service and architecture CI workflows.

Always inspect the current branch tree and service README before assuming a path, command, or deployment exists.

## Local development and validation

The repository is a multi-service project. Run checks from the relevant service or package directory; do not assume a single root command validates everything.

### Complementer

From \`services/recommendation-service/\`:

\`\`\`bash
python -m pip install -r requirements.txt
python -m pip check
python -m compileall -q app tests
python -m pytest -q
\`\`\`

### Catalog

From \`services/catalog-service/\`:

\`\`\`bash
python -m pip install -r requirements.txt
python -m pytest -q
\`\`\`

Use the service's documented migration procedure for database-backed tests and environments. Do not run production migrations from a developer workstation without an approved deployment plan.

### NPL

From \`services/npl-service/\`:

\`\`\`bash
python -m pip install -r requirements.txt
python -m pytest -q
\`\`\`

Production readiness requires a PostgreSQL database, applied schema, a high-entropy \`NPL_SERVICE_TOKEN\`, and a high-entropy \`NPL_EVIDENCE_HMAC_SECRET\`. The service's \`/ready\` endpoint checks token, signing, database, and schema readiness. Do not use SQLite outside the explicit test mode.

### DermalSight

From \`services/dermalsight/\`:

\`\`\`bash
python -m pip install -r requirements-dev.txt
pytest -q
\`\`\`

The API requires bearer authentication and explicit consent. Actual inference requires an approved ONNX artifact, manifest, signed validation report, and signing key. Unit tests and synthetic ONNX fixtures validate wiring, not model accuracy. No model weights or secrets should be committed.

### Architecture checks

The repository has architecture tests under \`tests/architecture/\`. Inspect the current workflow definitions and run the exact commands used by CI for the branch being changed. Do not assume an old README command remains valid if the workflow or tree has changed.

### CI evidence and reporting

For every validation report, identify:

- Repository and branch.
- Commit SHA.
- Workflow and job names.
- Exact test/build result.
- Warnings, skipped tests, and known limitations.

A passing test suite validates only the exercised code and environment. It does not prove production deployment health, live database readiness, real model quality, full cross-service operation, or business outcomes.

## Privacy, security, and responsible AI

Cirvanna may process personal preferences, face/body images, cosmetic skin attributes, and shopping history. These require strict purpose limitation and controls.

- Collect only data needed for a stated feature.
- Obtain explicit consent for image analysis and personalisation where required.
- Use trusted authentication and derive subject identity from verified credentials; do not trust arbitrary client-supplied user IDs for cross-account access.
- Enforce least privilege, tenant isolation, and service-to-service authentication.
- Define retention, export, correction, and deletion before claiming persistent personal memory.
- Encrypt data in transit and at rest where supported by the selected infrastructure.
- Keep credentials, tokens, model weights, validation reports, and customer data out of Git.
- Restrict access to uploaded images and generated assets; DermalSight currently processes uploaded images in memory and does not persist them.
- Avoid unnecessary personal data in logs, analytics, traces, and model prompts.
- Never infer sensitive identity or cultural affiliation from appearance.
- Treat skin outputs as non-diagnostic cosmetic attributes, not medical diagnosis or treatment advice.
- Keep model outputs subordinate to consent, policy, and explicit user constraints.
- Provide safe failure behavior when models, databases, or downstream services are unavailable.

If a secret may have been committed, remove it from active source and rotate it. Deleting a string from the latest commit does not invalidate an exposed credential.

## Implementation status

The table below describes the state supported by repository and CI evidence as of 2 November 2026. It intentionally distinguishes code, tests, integration, and production operation.

| Area | Verified state | Remaining gate |
|---|---|---|
| Complementer v2 | Advisory API/domain code and tests exist on draft PR #72; 22 tests passed on the recorded head | Trusted identity/profile hydration, durable TAL persistence, UI integration, end-to-end recommendation journey |
| Catalog product intelligence | Optional typed metadata validation and version-snapshot integration exist on PR #72; Catalog checks passed | Live product enrichment quality, provenance review, personalised ranking, candidate-bound CAL authorization |
| TAL | Deterministic in-memory event contract exists | Durable store, authenticated subject binding, consent receipts, replay, retention, export, correction, deletion, audit |
| NPL | Separate authenticated database-backed service and schema exist | Production PostgreSQL configuration, secret management, deployed readiness, gateway integration and verified subject binding |
| USI | Canonical domain package and architecture tests exist | Complete trusted profile service/persistence and end-to-end hydration into dependent services |
| CAL / CaTaCaCi | Deterministic arbitration kernel and initial supporting contracts exist | Complete trusted evidence receipts, production policy governance, replay, and full end-to-end display enforcement |
| DermalSight | Guarded API, consent/image validation, ONNX adapter and signed-report gate exist | Approved model artifact, representative validation, real model evaluation and deployed readiness |
| Longitudinal skin forecast | Explicitly unavailable in capability contract | Licensed longitudinal data, separate validated model, calibration, subgroup evaluation, privacy review |
| Virtual Twin / Try-On | Guarded API/orchestration foundations exist | Validated renderer/model, consent, asset authorization, runtime deployment, image-quality and privacy QA |
| Marketplace / Commerce | Catalog, service, and browser/BFF code foundations exist; related CI checks passed on reviewed heads | Live identity, durable cart/account, managed databases, payment/webhook and inventory verification, CAL-gated E2E |
| Living Filters | Product direction defined | Licensed model/runtime assets, segmentation and tracking validation, device QA, offline/CSP/security checks |
| Production operations | CI workflows provide code-level evidence | Verified deployed environments, health/readiness checks, monitoring, backups/restores, incident and rollback drills |

### PR #72 verification snapshot

- PR: [Expand Complementer into Personal Aesthetic Intelligence and product intelligence](https://github.com/cirvannaco-png/Cirvanna-demo/pull/72)
- State: **open, draft, unmerged**
- Head at verification: \`7278e59df426ea344f54cdee6a93d557a2f07d93\`
- Complementer: 22 passed, 0 failed; one non-blocking Starlette/httpx deprecation warning.
- Catalog, architecture, DermalSight API/model-contract and Docker build, Vision Intelligence, marketplace contract/headless browser, and related service build/check workflows reported success on that head.
- These are CI results for that commit. They are not a production deployment or a complete integrated user journey.

Do not change the status table to "production-ready" based only on unit tests or green CI.

## Roadmap and release gates

### 1. Complete trusted profile and feedback integration

- Define a gateway-authenticated subject context and remove reliance on client-asserted identity for cross-service operations.
- Hydrate Complementer from canonical USI and NPL providers.
- Connect feedback to canonical TAL persistence—not a new Complementer-owned database.
- Implement consent receipts, idempotency, correction, retention, export, deletion, and audit.
- Keep rejections as soft observations unless the user explicitly creates or confirms a hard exclusion.
- Add adversarial integration tests for cross-user access, replay, duplicate events, revocation, and correction.

### 2. Complete the marketplace decision path

- Retrieve canonical product and offer/variant identifiers from Catalog.
- Preserve metadata provenance and freshness.
- Rank only as an advisory retrieval step.
- Submit every candidate to CAL and display only candidates with an authorized decision.
- Test unavailable providers, stale metadata, hard negatives, and partial catalog responses.

### 3. Validate DermalSight forecasting as a separate capability

- Acquire licensed longitudinal data and define the target outcomes.
- Train and evaluate a distinct forecast model.
- Report calibration, subgroup errors, uncertainty, and temporal holdout performance.
- Keep optional sensitive context user-entered and separately consented.
- Do not enable forecasting until independent review and release criteria pass.

### 4. Production hardening

- Complete threat modelling, dependency and secret review, service authentication, and tenant isolation.
- Verify managed database migrations, backup and restore, and data-retention jobs.
- Run staging end-to-end tests, load tests, failure recovery, and observability checks.
- Validate model licensing, deployment integrity, drift monitoring, and rollback.
- Release behind controlled feature flags only after recorded acceptance evidence.

## Contribution and engineering rules

1. Inspect the current repository, branch, service contracts, and tests before editing.
2. Identify the canonical domain owner and data authority before adding a new model or store.
3. Preserve existing behavior and API compatibility unless a reviewed breaking change is intended.
4. Prefer one complete, testable vertical slice over disconnected feature stubs.
5. Add tests for normal behavior, boundaries, conflicting constraints, identity isolation, and dependency failure.
6. Do not fabricate model outputs, metrics, test results, deployment status, or business outcomes.
7. Do not introduce secrets, unnecessary personal data, or unreviewed dependencies.
8. Document migrations, rollback, configuration, limitations, and operational impact.
9. Run the actual checks and report their commit, command, result, and limitations.
10. Update this README when verified implementation status changes.

## Architecture references

- [Complementer, Marketplace Product Intelligence and Skin-State Forecasting](docs/architecture/complementer-product-intelligence-skin-forecast.md)
- [Decision flow](docs/architecture/decision-flow.md)
- [Architecture decision record: CaTaCaCi decision contract](docs/architecture/adr/ADR-0001-catacaci-decision-contract.md)
- [Integration staging and source intake](integration-staging/README.md)
- [Catalog service](services/catalog-service/README.md)
- [NPL service](services/npl-service/README.md)
- [Recommendation service](services/recommendation-service/README.md)
- [DermalSight service](services/dermalsight/README.md)

---

**Final principle:** The README describes the system honestly; executable code and reproducible evidence establish what is actually built. Cirvanna should grow through clear ownership, validated contracts, integrated user journeys, and measured outcomes—not through feature labels that outrun the software.
