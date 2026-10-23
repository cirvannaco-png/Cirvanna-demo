# Cirvanna

**Computing purchase certainty before checkout.**

Cirvanna is an identity-first beauty, fashion, fit, and purchase-decision platform. Its purpose is to help people understand whether a product is appropriate for their preferences, context, and fit needs before they buy—and to help commerce partners improve purchase confidence and reduce avoidable returns.

> **Critical implementation notice — 22 October 2026:** The repository now contains a deterministic CaTaCaCi/CAL arbitration kernel and package-level EEPL/NPL/USI/FCI contract pipeline, initial TAL/CAM/CIL/VSL governance contracts, an authenticated purchase-decision gateway, a catalog API, marketplace browser/BFF and catalog/commerce/decision service code, a guarded Virtual Try-On API, and a consent- and model-gated DermalSight API. Architecture and relevant feature workflows passed on the reviewed PR heads, including [PR #41](https://github.com/cirvannaco-png/Cirvanna-demo/pull/41), [PR #43](https://github.com/cirvannaco-png/Cirvanna-demo/pull/43), [PR #44](https://github.com/cirvannaco-png/Cirvanna-demo/pull/44), and [PR #48](https://github.com/cirvannaco-png/Cirvanna-demo/pull/48). This establishes tested code contracts, not an end-to-end product. There is still no configured independent safety-policy provider or calibrated FCI provider; the decision audit store is development-only and lacks a full evaluated-signal receipt; actual user sign-in/consent/profile persistence, validated Twin/Try-On renderers, validated DermalSight inference, live marketplace identity/database/payment integration, and deployment/restore evidence remain incomplete. CFRP V6 remains a staged candidate and is not a canonical runtime dependency. **Cirvanna is not production-ready.**

## Contents

- [Product vision](#product-vision)
- [Intended user experience](#intended-user-experience)
- [Product capability map](#product-capability-map)
- [Target system architecture](#target-system-architecture)
- [CaTaCaCi decision governance](#catacaci-decision-governance)
- [Canonical decision pipeline](#canonical-decision-pipeline)
- [Target repository layout](#target-repository-layout)
- [Data, privacy, and security](#data-privacy-and-security)
- [Implementation roadmap](#implementation-roadmap)
- [Validation and release gates](#validation-and-release-gates)
- [Current implementation status](#current-implementation-status)
- [Feature readiness and integration gates](docs/architecture/feature-spine-readiness-2026-10-23.md)
- [Contribution and engineering rules](#contribution-and-engineering-rules)

## Product vision

Most commerce experiences concentrate on helping people find products. Cirvanna aims to validate a purchase decision before checkout.

The platform's intended intelligence combines personal style, hard and soft preferences, eligibility and context, user-directed cultural requirements, fit evidence, and visualization. Rather than blindly maximizing clicks or recommendation scores, the system should determine whether a candidate is suitable enough to show, should be blocked, or needs further review.

Cirvanna has two connected value propositions:

**For users**
- Discover beauty and fashion products aligned with their preferences and intended use.
- Express what they like, dislike, and consider non-negotiable.
- Preview possible looks and combinations where supported by validated visualization technology.
- Understand uncertainty and make the final decision themselves.
- Retain control over personal identity data, photos, and preference history.

**For commerce partners**
- Improve product relevance and purchase confidence before checkout.
- Surface fit and suitability information where evidence supports it.
- Generate measurable insight into product suitability and avoidable returns.
- Evaluate performance using controlled pilots and transparent metrics rather than unsupported savings claims.

These are product goals. Commercial impact must be demonstrated through pilots and measured outcomes; it must not be presented as an achieved result without evidence.

## Intended user experience

The intended experience is a connected journey:

1. **Establish preferences:** users provide relevant style preferences, constraints, and optional context.
2. **Build a personal style representation:** the system derives a revisable user style profile from user input and permitted interactions.
3. **Explore products:** users search or browse the catalog and discover relevant candidates.
4. **Evaluate suitability:** eligibility, hard dislikes, cultural requirements, and available fit evidence are checked.
5. **Preview where supported:** the user may use virtual try-on, beauty visualization, or wardrobe experiences if the relevant capability is implemented and available.
6. **Understand the decision:** the system explains key reasons and uncertainty in understandable language.
7. **Choose independently:** the user decides whether to save, explore further, or purchase.
8. **Learn responsibly:** feedback can improve future results under transparent controls, without silently reversing hard constraints.

A missing model, unavailable catalog, failed image pipeline, or uncertain fit result must not be disguised as a successful analysis. The product should show an honest fallback.

## Product capability map

The following is the **target capability map**, not a declaration that each feature has been implemented.

### Identity and personalization

- **USI — User Style Index:** represents user-stated and learned style preferences. It should be revisable and sensitive to changes in preference over time.
- **NPL — Negative Preference Layer:** records explicit dislikes and permitted learned exclusions. Explicit hard negatives must take precedence over trends, popularity, and aggregate user behavior.
- **Cultural identity layer:** supports requirements stated or selected by the user. The system must not infer sensitive cultural identity from a face or body image.
- **EEPL — eligibility and context policy:** applies relevant age, location, occasion, climate, and other eligibility constraints where lawful and appropriate.
- **Revival / preference continuity:** the intended ability to retain useful preference context across sessions, subject to user controls, consent, retention limits, and deletion support.

### Fit and purchase confidence

- **FCI — fit-confidence intelligence:** the broader fit-intelligence capability intended to estimate suitability from available product and user evidence.
- **CRFP / CFRP:** the source material uses both labels. Their definitions, contracts, and implementations must be compared before either name is designated canonical.
- **Purchase-certainty decision:** the system should communicate evidence and uncertainty, not claim that an outcome is certain when it is only probabilistic.
- **Merchant insights:** intended aggregate reporting for participating brands, subject to data minimization, privacy controls, and validation of metric definitions.

### Visualization and personal experiences

- **Virtual Twin:** intended personal representation for supported preview experiences.
- **Experience Lab and moodboards:** intended spaces for exploring, saving, and comparing looks.
- **Virtual Try-On:** intended visualization for supported beauty, fashion, accessories, or hairstyle categories. Accuracy and supported categories must be measured rather than assumed.
- **Wardrobe digitization:** intended catalog of user-owned clothing and combinations, with appropriate image and data controls.
- **RadianceScore:** a proposed product or experience metric whose definition, validation, limitations, and user-facing interpretation must be established before launch.
- **DermalSight:** intended skin-analysis experience requiring specific privacy, consent, safety, bias, and clinical-claim boundaries. It must not present unvalidated outputs as a diagnosis.
- **Xari:** intended AI beauty and product-discovery assistant, potentially connecting user questions, catalog search, and supported look-generation flows. Its tools and permissions must be explicitly bounded.

### Marketplace and commerce

- Product catalog and product-description search.
- Product detail, save, preview, and purchase journeys.
- Merchant onboarding and product-data ingestion.
- Catalog indexing and search infrastructure.
- Transaction and integration interfaces.
- Merchant analytics and return-related outcome measurement.

Any stated catalog size, latency target, conversion improvement, or return-reduction figure is a target or hypothesis until the relevant environment and measurement methodology demonstrate it.

## Target system architecture

The following architecture describes the intended destination. It must be reconciled with the actual repository before code is moved, renamed, or treated as canonical.

### Application layer

User-facing web or mobile experiences should own presentation, navigation, accessibility, and interaction state. They should call documented application interfaces rather than reimplementing policy logic in the UI.

### Application and domain services

Services should expose bounded capabilities—for example, identity/preferences, catalog/search, fit assessment, decision arbitration, visualization orchestration, and merchant insights—only when the implementation and operational needs justify those boundaries. Avoid creating empty microservices merely to match a diagram.

### Shared domain packages and contracts

Shared packages should define validated data structures, error semantics, versioned interfaces, and common domain rules. Contracts should make ownership explicit and avoid circular dependencies.

### Data and search

The target may include transactional storage, object storage for authorized media, and a search/vector index for product retrieval. The actual database, embedding model, vector index, retention policy, and performance profile must be selected and tested against real workloads. A design target such as sub-100 ms retrieval is not an achieved benchmark.

### AI and model integration

Models should be accessed behind explicit interfaces with documented inputs, outputs, timeouts, cost controls, version tracking, and fallback behavior. Model output is evidence for a decision—not authority to bypass policy, consent, or hard user constraints.

### Observability and operations

The intended system should include structured logs, metrics, distributed correlation IDs, health checks, error reporting, deployment traceability, and operational runbooks. Logs must avoid unnecessary sensitive user data.

## CaTaCaCi decision governance

**CaTaCaCi** is the intended governing cognitive decision core. Its **Cognitive Arbitration Layer (CAL)** is designed to arbitrate among conflicting evidence and produce an auditable decision. CAL is not simply another recommender or a weighted sum with a different name.

The planned decision-support components are:

- **CAL — Cognitive Arbitration Layer:** determines whether a candidate should be shown, blocked, or reviewed according to explicit policy and evidence.
- **TAL — Temporal Learning:** models preference changes over time and helps identify potential identity drift.
- **CAM — Counterfactual Auditing:** records why a decision occurred and supports evaluation of alternative outcomes.
- **CIL — Collective Intelligence:** extracts carefully governed aggregate signals for trend or product insight without overriding individual hard constraints.
- **VSL — Value System Layer:** governs changes to decision values through controlled evaluation, versioning, and review.

CAL now has an initial deterministic arbitration kernel; TAL, CAM, CIL, and VSL have initial pure/domain contracts only. Those contracts do not establish durable storage, production governance workflows, or end-to-end integration.

### CAL decision inputs

The planned arbitration process may consider:

- Eligibility and contextual constraints.
- User Style Index alignment.
- Explicit and learned negative preferences.
- User-directed cultural requirements and severity.
- Fit evidence and confidence.
- Data completeness, freshness, and uncertainty.
- Policy and model versions.
- Safety, consent, and operational constraints.

### CAL decision outputs

The intended result should be a typed decision such as:

- **SHOW:** candidate satisfies required constraints and meets the applicable evidence threshold.
- **BLOCK:** candidate violates a hard constraint or an exclusion policy.
- **REVIEW / INSUFFICIENT EVIDENCE:** available evidence is conflicting, incomplete, or below the threshold required for a confident decision.

Each decision should carry structured reason codes and a correlation ID. Where applicable, it should record the policy version, model version, timestamp, and evidence provenance. It should not expose hidden internal reasoning or sensitive data to users; user-facing explanations should be concise and grounded in permitted evidence.

### Priority and conflict rules

1. Legal, safety, consent, and eligibility constraints cannot be overridden by a recommendation score.
2. An explicit hard negative cannot be overridden by trend, popularity, or collaborative signals.
3. User-directed cultural requirements must be respected according to their configured severity.
4. Fit confidence must reflect actual available evidence and must expose uncertainty.
5. Conflicts or missing evidence must produce a safe fallback rather than an invented positive result.
6. Preference learning must not silently weaken explicit user constraints.
7. Changes to arbitration rules must be versioned and regression-tested.

The exact arbitration mathematics, thresholds, and conflict-resolution protocol remain implementation decisions until specified, tested, and reviewed.

## Canonical decision pipeline

The target flow is:

1. **Validate the request:** authenticate and authorize the caller, validate the schema, and assign a correlation ID.
2. **Apply EEPL:** enforce relevant eligibility and context rules.
3. **Apply cultural requirements:** use user-directed settings and explicit severity rules.
4. **Evaluate USI:** assess style alignment from permitted profile data.
5. **Enforce NPL:** reject candidates that violate hard negative preferences; do not let aggregate scores override them.
6. **Evaluate fit intelligence:** calculate a confidence estimate from available evidence and label missing or uncertain data.
7. **Arbitrate with CaTaCaCi / CAL:** resolve conflicts and return SHOW, BLOCK, or REVIEW with reason codes.
8. **Deliver approved results:** route candidates to the relevant catalog or supported experience through defined interfaces.
9. **Record an auditable event:** store minimal decision metadata needed for debugging, measurement, and permitted learning.
10. **Process feedback safely:** update preference signals under explicit rules and preserve hard constraints.

The order and interfaces must be enforced by executable code and tests; a README description alone does not enforce them.

## Target repository layout

The intended organization is:

- `apps/` — user-facing applications and demo experiences.
- `services/` — deployable APIs and workers, where justified.
- `packages/` — domain logic, shared contracts, and reusable libraries.
- `infrastructure/` — local development, deployment, observability, and operations.
- `docs/architecture/` — system boundaries, decision flows, and architecture decision records.
- `docs/migration/` — source lineage, intake status, and migration decisions.
- `tests/` — unit, integration, contract, architecture, and end-to-end tests.

This is a target layout, not a guarantee that every directory or component currently exists. Before creating or restructuring files, inspect the repository tree, identify the actual entry points, and map each supplied source file to its intended domain.

## Data, privacy, and security

Cirvanna may process personal preferences, body or face images, skin-related information, and shopping history. Such data requires careful handling.

- Collect only what is necessary for a defined feature.
- Explain the purpose of image and profile processing and obtain appropriate consent.
- Define retention, export, correction, and deletion behavior.
- Enforce authentication, authorization, least privilege, and tenant separation.
- Encrypt sensitive data in transit and at rest where supported by the selected infrastructure.
- Never commit real credentials, access tokens, private customer data, or production environment files.
- Use safe example values and a documented secret-management approach.
- Restrict access to uploaded images and generated assets.
- Avoid treating skin-analysis output as medical diagnosis unless the product is specifically validated and legally authorized for that purpose.
- Do not infer sensitive cultural or personal identity from appearance.
- Define abuse controls, rate limits, upload validation, and secure file handling.
- Ensure logs, analytics, and AI prompts do not unnecessarily reproduce sensitive information.

If a supplied file contains credentials or secrets, do not copy them into new locations. Identify the exposure, remove the secret from active source, and rotate it if it may have been real.

## Implementation roadmap

The implementation sequence should be evidence-driven. Do not jump to a polished demo while core decision behavior remains undefined.

### Phase 0 — Source intake and baseline

- Inventory all supplied files and record their origin, language, completeness, dependencies, and intended purpose.
- Identify duplicates, truncated snippets, conflicting versions, placeholders, and credential exposure.
- Inspect the actual repository tree, default branch, dependency manifests, workflows, and existing tests.
- Establish a baseline of what currently builds and what fails.
- Create a traceable source-to-target migration map.

**Exit criteria:** the source inventory is reproducible, critical unknowns are recorded, and no file is assumed implemented merely because it exists.

### Phase 1 — Contracts and architecture decisions

- Define canonical domain models and error formats.
- Decide the ownership and interfaces of USI, NPL, EEPL, fit intelligence, CAL, catalog search, and experience orchestration.
- Resolve the CRFP/CFRP naming conflict.
- Specify decision reason codes, audit events, model/policy versioning, and safe fallbacks.
- Record material choices in architecture decision records.

**Exit criteria:** interfaces and invariants are documented and reviewed before dependent implementations are integrated.

### Phase 2 — Minimal vertical slice

Implement one complete, testable path rather than many disconnected stubs:

1. Accept a validated user preference profile.
2. Retrieve a small controlled catalog of candidate products.
3. Apply eligibility and hard negative preferences.
4. Run deterministic arbitration with explicit reasons.
5. Return results through an API and display them in a basic interface.
6. Add unit, contract, and integration tests.

**Exit criteria:** a reproducible end-to-end test proves the complete path works; missing features are clearly labeled.

### Phase 3 — Personalization and fit evidence

- Implement USI and preference persistence.
- Implement NPL hard-negative behavior and safe feedback updates.
- Define fit data requirements and confidence calibration.
- Test conflict cases, missing data, preference changes, and profile deletion.
- Evaluate fairness and behavior across supported product categories and user groups.

**Exit criteria:** behavior is measured, testable, and documented; no unsupported fit guarantee is presented.

### Phase 4 — Visualization and beauty capabilities

- Integrate Virtual Twin, Try-On, wardrobe, DermalSight, and Xari only through explicit contracts.
- Validate supported inputs, outputs, latency, quality, privacy, and failure modes per feature.
- Add user consent, deletion, and safe fallback flows.
- Keep unimplemented capabilities visibly unavailable instead of simulating success.

**Exit criteria:** each capability passes its own acceptance criteria and security/privacy review.

### Phase 5 — Marketplace and merchant integrations

- Implement catalog ingestion, validation, search, product detail, and purchase handoff.
- Define merchant authorization and tenant boundaries.
- Add measurable analytics for product relevance and purchase outcomes.
- Establish a controlled pilot and a documented baseline before claiming commercial improvement.

**Exit criteria:** integration tests pass and business metrics are measured against an agreed baseline.

### Phase 6 — Production hardening

- Complete threat modeling, dependency review, secrets management, backup/recovery, monitoring, and incident runbooks.
- Run load, failure-recovery, and end-to-end tests.
- Verify deployment configuration and rollback procedures.
- Release gradually with feature flags and observable health indicators.

**Exit criteria:** all required release gates pass with recorded evidence and an accountable owner.

## Validation and release gates

The repository's previously documented architecture checks use Python 3.11 or newer:

```bash
python scripts/validate_architecture.py
python -m unittest discover -s tests/architecture -v
```

First verify that these paths actually exist in the checked-out repository. If they do not, report that fact; do not claim the commands passed.

As implementation grows, add the relevant checks:

- Unit tests for deterministic domain rules.
- Contract tests for service and package boundaries.
- Integration tests for databases, search, models, and external services.
- End-to-end tests for real user journeys.
- Security and privacy checks, including secret scanning.
- Dependency and build reproducibility checks.
- Performance tests against stated workload and latency objectives.
- Resilience tests for timeouts, unavailable dependencies, partial data, and retries.
- Accessibility and usability checks for user-facing flows.
- Model evaluation, calibration, and bias checks where machine learning is used.

Every validation report should identify the commit, environment, command, result, and known limitations. A passing architecture test is not a substitute for application tests, and a successful build is not proof of production readiness.

## Current implementation status

**Cirvanna is not yet a verified end-to-end product.** The following status distinguishes tested domain/API contracts from live services, calibrated models, and production operations; passing a workflow does not erase the remaining release gates.

| Area | Status represented by this README | Evidence needed to advance |
|---|---|---|
| Product vision and target architecture | Documented intent | Reviewed architecture decisions |
| Source bundle and migration | Original archive and 31 extracted snapshots preserved; candidate syntax repairs tracked; canonicalization and runtime integration remain incomplete | Reviewed source-to-target map, duplicate/dependency analysis, canonical implementation decisions, and integration tests |
| USI, NPL, EEPL, fit intelligence | Target responsibilities documented; implementation unverified | Canonical code, unit tests, integration tests |
| CaTaCaCi / CAL and supporting layers | Deterministic CAL arbitration and a contract-level EEPL/NPL/USI/FCI pipeline exist; initial TAL/CAM/CIL/VSL pure contracts are present. Full trusted signal provenance, calibrated providers, durable evidence receipts, replay, and production workflows remain incomplete. | Validate independent safety and calibrated-fit providers, strengthen adversarial contract tests, persist complete decision evidence/version receipts, and prove end-to-end authorization before display |
| Catalog, marketplace and decision API | Catalog API, authenticated decision gateway, marketplace browser/BFF, and catalog/commerce/decision service code are merged with CI checks on their reviewed heads. Local saved items/bag are not a durable account/cart implementation; the marketplace release runbook remains blocked pending live identity, separate managed databases, migrations, payment/webhook verification, stock/order invariants, backup restore, and end-to-end staging tests. No live deployment is certified. | Run authenticated staging browse-to-checkout and payment-webhook flows, verify tenant boundaries/inventory/idempotency, test restore/recovery, and record actual deployed service-to-service evidence |
| Virtual Try-On | Guarded FastAPI orchestration API is merged (PR #46); API/privacy-gate tests and the Docker build passed. Rendering remains disabled until real server-side consent, asset authorization, and renderer/model integrations are deployed. | Integrate the selected model in an isolated GPU worker, connect authorized asset storage and consent services, then validate image quality, privacy, cost, latency, and output persistence |
| Virtual Twin and Virtual Try-On | Guarded APIs are merged, but Twin generation and Try-On rendering remain disabled until validated model/renderer adapters, server-side consent, asset authorization, and output storage are integrated and tested. | Validate model/render quality, ownership boundaries, privacy, latency, cost, failure paths, and deployed end-to-end preview behavior |\n| DermalSight | Consent- and model-gated API code and API tests are merged; validated skin-inference weights/provider and real inference are not configured or independently verified. No medical diagnosis claim is supported. | Validate the model/data license, output quality and bias, input/consent/access controls, inference provenance, retention/deletion, and production runtime behavior |
| Security and privacy | Requirements documented; compliance unverified | Threat model, secret scan, access-control and privacy tests |
| CI and deployment | Architecture, decision-gateway, marketplace/catalog/commerce, Virtual Twin, DermalSight API, and staged CFRP candidate workflows passed on their reviewed PR heads. The current merge set still does not prove live cross-service operation or deployment; no marketplace or beauty inference deployment is certified. | Run main-branch checks after the latest merges, real staging smoke tests, infrastructure/security checks, backup restore drills, operational runbooks, and evidence from a real environment |
| Production readiness | **Not established** | All required release gates with recorded evidence |

This table deliberately avoids inventing completion percentages. Update it only when the underlying code, tests, and operational evidence support a status change.

## Contribution and engineering rules

For every implementation change:

1. Inspect the existing repository and the relevant supplied source before editing.
2. Identify the domain owner, canonical contract, and migration impact.
3. Preserve source lineage until behavior has been compared and parity demonstrated.
4. Prefer a small, complete, tested vertical slice over a large collection of disconnected placeholders.
5. Add tests for normal behavior, boundaries, conflicting constraints, and dependency failures.
6. Do not fabricate API responses, AI results, test results, benchmarks, or production status.
7. Do not introduce secrets, personal data, or unreviewed external dependencies.
8. Document breaking changes, limitations, setup steps, and rollback implications.
9. Run the checks that are actually available and report exact results.
10. Update this README when verified implementation status changes.

## Final principle

**The README defines the destination; executable code and reproducible evidence establish what has actually been built.** Cirvanna should advance from source intake to clear contracts, then to a tested vertical slice, then to validated capabilities. Architectural ambition matters—but correctness, user trust, and demonstrated behavior matter more.
