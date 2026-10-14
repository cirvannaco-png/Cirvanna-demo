# Cirvanna

Cirvanna is an identity-first beauty, fashion, fit, and purchase-certainty platform. This repository is the canonical **Cirvanna monorepo integration home**: product domain modules and deployable services belong here unless a later architecture decision proves a separate repository is justified.

> **Current status (14 October 2026): architecture foundation and source inventory.** The uploaded source bundle contains overlapping generations, multiple languages, truncated snippets, naming conflicts, and unsafe example credentials. The structure below is established, but candidate implementations are not yet certified or represented as production-ready.

## Product architecture

Cirvanna validates a decision before it reaches the user or checkout. It combines declared user identity, User Style Index (USI), explicit and learned Negative Preference Layer (NPL), eligibility/context policy (EEPL), cultural requirements, fit confidence, and virtual visualization. CaTaCaCi is the governing decision core; its Cognitive Arbitration Layer (CAL) decides whether an item is shown, blocked, or requires review. CAL is not a recommender or a weighted-score substitute.

## Repository layout

- apps/ — user-facing applications and the demo.
- services/ — deployable APIs and workers.
- packages/ — domain logic, shared contracts, reusable libraries.
- infrastructure/ — local development, deployment, observability and operations.
- docs/architecture/ — system boundaries and canonical decision flow.
- docs/migration/ — source lineage, intake status and migration decisions.
- tests/architecture/ — automated checks for repository governance and module inventory.

## Canonical decision responsibilities

1. **EEPL** applies eligibility and context constraints such as age, location, occasion and climate.
2. **Cultural identity** resolves declared requirements and severity; it must not infer identity solely from appearance.
3. **USI** represents the user's stated and learned style preferences.
4. **NPL** enforces explicit and learned negative preferences. A hard negative cannot be overruled by trend or popularity.
5. **Fit intelligence** (FCI and the CFRP candidate) estimates fit confidence and communicates uncertainty.
6. **CaTaCaCi / CAL** arbitrates conflicting evidence and emits an auditable show / block / review decision.
7. **Virtual Twin, Virtual Try-On, DermalSight, wardrobe and Xari** provide capabilities behind explicit contracts; none may bypass decision arbitration.

The source bundle uses both **CFRP** and the separately remembered **CRFP** label. They are intentionally not treated as aliases until their contracts are compared.

## Governance rules

- One owner per domain; shared behavior belongs in a package rather than being copied between services.
- UI code does not own business rules; services do not reach into another service's database.
- Contracts are versioned, inputs are validated, and decisions carry correlation IDs, reason codes and policy/model versions.
- Secrets and real user data never enter source control. Environment examples contain names and safe placeholders only.
- A module is not production-ready because a source note calls it so. It must pass automated tests, security review, integration tests and domain acceptance criteria.
- Source variants stay tracked until a canonical version is selected and parity is demonstrated. Do not delete behavior merely to make the tree look clean.

## Validation

Run with Python 3.11+:

    python scripts/validate_architecture.py
    python -m unittest discover -s tests/architecture -v

These checks validate repository structure and source lineage only. They do not certify runtime behavior or model quality.

## Migration status

See docs/migration/2026-10-14-source-intake.md and docs/migration/module-inventory.json. This branch establishes a traceable, secure destination before promoting unverified or truncated source into executable paths.
