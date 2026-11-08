# Monorepo governance

> Contributor entry point: [Source of truth and contributor guide](source-of-truth-and-contributor-guide.md). The [runtime source registry](runtime-source-registry.json) defines authoritative source roots and quarantined locations.

## Repository responsibility

This repository owns Cirvanna product source: identity intelligence, fit intelligence, preference enforcement, cultural identity policy, wardrobe/catalog, virtual visualization, skin intelligence, orchestration and the web demo. The monorepo is the default because these domains share contracts and release coordination. A separate repository requires an explicit decision based on independent ownership, deployment, security boundary or release cadence—not merely a different language or module name.

## Architectural layers

| Layer | Owns | Must not own |
| --- | --- | --- |
| Apps / presentation | UI state, user interaction, accessibility, API clients | Policy decisions, persistence queries, model governance |
| Services / application | Use cases, orchestration, authorization, transactions | Another service's private tables or duplicated domain rules |
| Packages / domain | Entities, pure policy, decision protocols, typed contracts | HTTP wiring, credentials, deployment configuration |
| Infrastructure | Databases, queues, caches, storage, observability, deployment | Product-specific arbitration rules |
| Tests and docs | Contracts, invariants, threat models, migration lineage | Hidden alternate implementations |

## Ownership map

- **CaTaCaCi** owns canonical decision arbitration. CAL must return an explicit verdict with rationale and provenance. TAL manages temporal learning; CAM audits counterfactuals; CIL owns privacy-governed collective intelligence; VSL governs versioned value-system evolution.
- **EEPL** owns eligibility and context gates.
- **Cultural identity** owns user-provided cultural constraints and their versioned rule definitions.
- **USI** owns style preference interpretation, separate from fit confidence.
- **NPL** owns negative-preference capture, persistence, precedence and enforcement.
- **FCI** owns fit-confidence estimation and calibration.
- **CRFP** is one concept with two distinct scopes: marketplace CRFP and system-wide CRFP. The former CFRP spelling was a typo. Preserve the separate scope responsibilities and contracts; do not create competing authorities or infer unverified runtime semantics. Follow [ADR-0003](adr/ADR-0003-crfp-marketplace-and-system-scopes.md). Historical CFRP archive filenames remain unchanged for provenance; no archived candidate is promoted into runtime.
- **Virtual Twin** owns user-specific avatar/body representation and measurements.
- **Virtual Try-On** owns rendering/simulation orchestration, not preference policy.
- **DermalSight** owns skin-perception and clinically sensitive data; it does not make unsupported diagnoses.
- **Wardrobe/catalog** owns garment metadata and catalog persistence.
- **Xari** is the current product name for the assistant/skin-analysis/chat/marketplace-search/Try-On orchestration surface. Tari and Xyra are legacy source names and must be reconciled, not deployed as duplicates.
- **Shared contracts** define stable API events, identifiers, versioning and error envelopes.

## Integration requirements

1. Domain packages expose typed inputs/outputs and avoid direct infrastructure calls unless through a port/interface.
2. Services communicate through versioned APIs/events. Database ownership is per service.
3. User-facing responses include decision status, reason codes, uncertainty where applicable, correlation ID, and policy/model version.
4. Identity safety and hard negative preferences are constraints, not soft ranking boosts.
5. A failed optional capability degrades explicitly to NEEDS_REVIEW or a documented safe fallback; it never silently bypasses mandatory gates.
6. Every learned change is traceable, versioned, reversible and checked against counterfactual/regression tests.
7. User identity, skin, measurements and wardrobe data are sensitive. Enforce minimization, retention limits, access controls and deletion workflows.

## Source promotion gate

Uploaded code is not promoted into runtime paths until it has one canonical version, complete files, dependency/license review, secret removal, static checks, unit tests, contract tests and integration/acceptance tests. Conflicting generations remain inventoried until reconciled. Run `python scripts/validate_source_boundaries.py` to detect statically identifiable imports from source archives, candidate folders, and experimental paths. The guard is deliberately limited: dynamic filesystem loading, dependency/package indirection, generated code, and runtime behavior still require review.
