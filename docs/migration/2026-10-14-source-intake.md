# Source intake and migration plan — 14 October 2026

## Finding

The current default branch was a minimal demo shell: a small README, a space-suffixed file containing a proposed directory tree, and the license. The attached merged(0).txt contains 52,551 lines and 31 labeled source snapshots spanning TypeScript, Python, JSON, Docker, environment examples and service specifications. It is a source bundle, not a validated working tree.

This branch establishes target ownership, source lineage, module folders and a CI guard. It does **not** claim that the 31 snapshots have all been copied, compiled or integrated.

## Why promotion is gated

The bundle contains several variants of the same modules (CDIC, EEPL, FCI, Tari/Xyra, Virtual Try-On, Virtual Twin and wardrobe services). Some end at visibly incomplete Python expressions or statements; other segments are structurally truncated. Some documentation asserts production readiness without providing matching test artifacts. Virtual Try-On examples contain hard-coded sample passwords and API-key-like strings. Those values are not copied to this repository. If such values were ever real or reused, rotate them.

A direct bulk copy would create architecture drift, duplicate implementations, broken imports and a misleading green build. The safe order is: inventory -> canonical-version selection -> code extraction -> secret/dependency scan -> module tests -> contract reconciliation -> integration tests -> runtime/performance certification.

## Canonical destination map

- apps/demo-web: demo presentation and user interaction only.
- services/api-gateway: request boundary, authentication, rate limits, API composition.
- services/catalog-service and services/wardrobe-service: catalog and user wardrobe; garment persistence has clear ownership.
- services/virtual-twin and services/virtual-try-on: separate body/avatar representation from rendering/simulation.
- services/dermalsight: skin perception and clinically sensitive outputs behind consent and safety controls.
- services/xari: original source path for the assistant/orchestrator; the current canonical identity is PNELLY under ADR-0010. Xari/Tari/Xyra remain legacy names and source lineage.
- services/graph-service, services/recommendation-service, services/perception-service and services/sync-service: proposed separate service boundaries for wardrobe-related capabilities.
- packages/identity-intelligence: CaTaCaCi, CDIC legacy adapter, USI and EEPL.
- packages/fit-intelligence: FCI and unresolved CFRP/CRFP candidate.
- packages/preferences/npl: negative-preference domain and enforcement contract.
- packages/shared-contracts: shared API/event DTOs without business logic.
- infrastructure: deployment, observability and local service wiring.

## Migration phases

1. **Foundation (this branch):** boundaries, source inventory, safe environment template and structural CI.
2. **Canonicalization:** select one version per module; compare behavior, not filenames alone.
3. **Extraction:** move complete files to mapped destinations; resolve imports and dependency direction.
4. **Verification:** Python compile/lint/type tests, TypeScript typecheck/tests, schema validation, secret scan, API contract tests and service integration tests.
5. **Runtime proof:** exercise real app paths and infrastructure. Only then update production-readiness claims.

## Current limitations

No live runtime, production deployment, model weights, vendor credentials or complete test evidence accompanied the source bundle. The architecture check validates inventory and folder ownership only; it is not application certification.
