# Source-candidate syntax repairs

**Date:** 2026-10-15  
**Scope:** Five syntax-blocking files under `integration-staging/source-candidates/`.

## What changed

| Candidate file | Repair | What the repair does not prove |
|---|---|---|
| `23-virtual-tryon-1-.txt/gsis/validators.py` | Completes the truncated fabric-weight validation and returns warnings or raises the existing validation error. | Does not certify garment-policy correctness or integration. |
| `24-virtual-tryon-2-.txt/gsis/validators.py` | Same minimal completion as the sibling candidate. | Does not prove the variants are equivalent beyond the repaired validator. |
| `26-virtual-tryon-improved.txt/gsis/validators.py` | Same minimal completion as the sibling candidate. | Does not certify the full Virtual Try-On system. |
| `25-virtual-tryon-.txt/gsis/service.py` | Completes the truncated list method and CRUD service using the structurally complete sibling candidate as a reference. Adds pagination bounds. | Database behavior, migrations, model compatibility, transactions, and integration tests remain unverified. |
| `30-wardrobe-2-3-and-4-.txt/services/api-gateway/app/main.py` | Completes the syntax but keeps the missing proxy handler fail-closed with an explicit upstream error. | This does **not** implement a functioning API gateway. Routing, authentication, header filtering, circuit-breaker integration, upstream forwarding, and response mapping must still be implemented and tested. |

## Provenance and promotion policy

The original merged source archive and the extracted intake snapshots remain preserved under `integration-staging/source-intake/`. This repair modifies only assembled candidate copies; it does not rewrite the original archive.

All these directories remain **source-intake candidates**, not canonical runtime code. Syntax compilation is a basic integrity gate only. Before promotion, each component requires dependency and interface review, security checks, focused unit tests, integration tests, and an explicit architecture-owner decision. Avoid describing candidate code as production-ready based solely on README claims or successful compilation.

## Validation

The `Source candidate syntax` GitHub Actions workflow compiles Python files under `integration-staging/source-candidates/`. A green result establishes only that Python syntax compilation completed for the checked files; it does not prove importability, dependency availability, business correctness, or production readiness.
