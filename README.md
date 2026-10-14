# Cirvanna

**Computing purchase certainty before checkout.**

Cirvanna is an identity-first beauty, fashion, fit, and purchase-decision platform. It is designed to help people discover products that fit their preferences, context, and identity before they buy—while giving commerce partners a path toward better product confidence and fewer avoidable returns.

> **Repository status — 14 October 2026:** This repository is the canonical integration destination and architecture foundation. The current source inventory contains overlapping implementation generations, multiple languages, naming conflicts, truncated snippets, and unsafe example credentials. Architecture and migration work must not be mistaken for a complete, tested, production deployment. Runtime readiness is established only by reproducible tests and evidence.

## Contents

- [Product vision](#product-vision)
- [Core architecture](#core-architecture)
- [Decision pipeline](#decision-pipeline)
- [Repository structure](#repository-structure)
- [Architecture and security principles](#architecture-and-security-principles)
- [Validation](#validation)
- [Migration and implementation status](#migration-and-implementation-status)
- [Contributing](#contributing)

## Product vision

Most shopping experiences optimize discovery. Cirvanna aims to validate the decision before checkout.

The platform brings together:

- **Personal style intelligence:** a User Style Index (USI) representing stated and learned style preferences.
- **Negative Preference Layer (NPL):** explicit and learned dislikes that prevent unsuitable recommendations from resurfacing.
- **Context and eligibility:** age-appropriate, location-aware, occasion-aware, and climate-aware constraints through EEPL.
- **Cultural identity:** user-directed requirements and cultural context, with safeguards against inferring identity from appearance alone.
- **Fit confidence:** fit-related evidence and uncertainty communicated before purchase.
- **Virtual visualization:** Virtual Twin, Virtual Try-On, wardrobe capabilities, and beauty experiences behind defined interfaces.
- **Beauty intelligence:** DermalSight and Xari capabilities, subject to their own validation, privacy, and safety requirements.
- **Decision governance:** CaTaCaCi, with the Cognitive Arbitration Layer (CAL) responsible for auditable show, block, or review outcomes.

The long-term goal is not to force a purchase. It is to help users make informed decisions—and to give commerce partners better signals about product suitability and purchase confidence.

## Core architecture

### CaTaCaCi and CAL

CaTaCaCi is the governing cognitive decision core. Its **Cognitive Arbitration Layer (CAL)** is the decision authority, not another recommender and not merely a weighted score.

CAL should consider relevant evidence—including fit confidence, USI alignment, NPL aversion, eligibility, cultural severity, and uncertainty—and produce an explainable outcome. Decisions should carry reason codes and enough versioned context to be audited and reproduced.

Related architecture responsibilities:

- **TAL — Temporal Learning:** tracks preference changes over time and supports identity-drift detection.
- **CAM — Counterfactual Auditing:** examines why an item was shown or blocked and evaluates alternative decisions.
- **CIL — Collective Intelligence:** uses appropriately aggregated cross-user signals for trend and product insight without overriding an individual's hard constraints.
- **VSL — Value System Layer:** governs the evolution of decision values under controlled evaluation and review.

These are architectural responsibilities, not a claim that every component is already implemented or production-certified.

### Canonical decision pipeline

1. **EEPL — eligibility and context:** apply applicable constraints such as age, location, occasion, and climate.
2. **Cultural identity layer:** apply user-directed cultural requirements and severity rules.
3. **USI — user style index:** evaluate alignment with the user's style preferences.
4. **NPL — negative preferences:** enforce hard dislikes and learned exclusions. Popularity, trends, or aggregate behavior must not override a hard negative.
5. **Fit intelligence:** assess available fit evidence and confidence, exposing uncertainty rather than inventing certainty.
6. **CaTaCaCi / CAL arbitration:** resolve conflicts and choose show, block, or review with auditable reason codes.
7. **Experience delivery:** pass approved results to the marketplace, Virtual Twin, Try-On, wardrobe, DermalSight, or Xari experiences through explicit contracts.

Exploration may be offered when evidence is incomplete only if hard constraints remain respected and uncertainty is clearly handled.

**Naming note:** the source inventory contains both **CFRP** and **CRFP** labels. They are not assumed to be aliases until their contracts and implementations are compared.

## Repository structure

The intended layout is:

- `apps/` — user-facing applications and demo experiences.
- `services/` — deployable APIs and workers.
- `packages/` — shared domain logic, contracts, and reusable libraries.
- `infrastructure/` — local development, deployment, observability, and operations.
- `docs/architecture/` — system boundaries, decision flow, and architecture records.
- `docs/migration/` — source lineage, intake status, and migration decisions.
- `tests/architecture/` — automated checks for repository governance and module inventory.

Treat this as the target architecture; verify actual files and executable paths before assuming every directory or capability is implemented.

## Architecture and security principles

1. **Single domain ownership.** Each domain has a clear owner; shared behavior belongs in versioned packages rather than copied implementations.
2. **Explicit boundaries.** UI code does not own business policy, and services do not access another service's database directly.
3. **Versioned contracts.** Validate inputs and outputs. Carry correlation IDs, decision reason codes, and relevant policy/model versions.
4. **Privacy by design.** Collect only necessary data, define retention and access controls, and obtain appropriate consent for sensitive image or skin-analysis workflows.
5. **Secret hygiene.** Never commit API keys, passwords, tokens, private customer data, or real credentials. Use environment variables or an approved secret manager; examples must contain safe placeholders.
6. **No silent identity inference.** Do not infer sensitive identity or cultural requirements from appearance. Let users state and control relevant preferences.
7. **Fail safely.** When required evidence or a dependency is unavailable, degrade gracefully without bypassing hard exclusions or misrepresenting confidence.
8. **Evidence over claims.** A source note or passing architecture check does not establish production readiness. Require tests, security review, integration evidence, and domain acceptance criteria.
9. **Preserve lineage.** Track competing source variants until a canonical implementation is selected and parity is demonstrated. Do not remove behavior simply to make the repository appear cleaner.
10. **Auditable evolution.** Changes to arbitration, preferences, or model behavior should be tested against regressions and counterfactual cases.

## Validation

The documented architecture checks require **Python 3.11 or newer**:

```bash
python scripts/validate_architecture.py
python -m unittest discover -s tests/architecture -v
```

These checks cover repository structure and source lineage only. They do **not** certify API behavior, model quality, end-to-end integrations, security, performance, or production deployment.

Before promoting a module to production, add and run the checks appropriate to it, including unit and integration tests, contract tests, security and privacy review, failure/recovery tests, and domain-specific acceptance tests. Record actual results; do not report unexecuted checks as passing.

## Migration and implementation status

The source-intake record and module inventory are the starting point for tracing existing variants:

- `docs/migration/2026-10-14-source-intake.md`
- `docs/migration/module-inventory.json`

The migration priority is to establish trustworthy source lineage, resolve naming and contract conflicts, remove unsafe credential examples, select canonical implementations, and prove compatibility before enabling production execution.

**Current limitation:** the architecture foundation and inventory are not evidence that every listed product capability is implemented, integrated, or production-ready. Keep status claims tied to reproducible test and deployment evidence.

## Contributing

For every change:

1. Identify the owning domain and relevant contract.
2. Inspect existing implementations and migration notes before adding a parallel version.
3. Make the smallest coherent change that preserves established behavior.
4. Add or update tests for normal, boundary, conflict, and failure cases.
5. Run the relevant validation commands and report the exact results.
6. Document contract changes, migration implications, security considerations, and any remaining limitations.

The governing rule is simple: **preserve user trust, preserve architectural integrity, and prove behavior before claiming readiness.**
