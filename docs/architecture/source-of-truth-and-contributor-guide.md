# Source of truth and contributor guide

This is the entry point for deciding **where production code belongs, which implementation is authoritative, and what evidence is required before promotion**. Read it before moving, copying, importing, or deploying recovered source.

## 1. Source classification

The repository uses explicit lifecycle labels. A file's presence, name, version number, passing syntax check, or inclusion in a source archive does not make it runtime code.

| Label | Meaning | Permitted use |
|---|---|---|
| **Canonical source** | The reviewed owner path for the current domain implementation or contract | Runtime imports and normal development, subject to that capability's own readiness gates |
| **Implementation scaffold** | A canonical integration/API location whose provider, persistence, model, or E2E behavior is incomplete | Contract work and guarded development; do not advertise as live or production-ready |
| **Candidate** | A preserved implementation proposed for comparison or selective extraction | Isolated evaluation only; no canonical runtime imports |
| **Experimental** | A prototype or research implementation with unapproved behavior/dependencies | Isolated experiments only; no production authority |
| **Archived** | Historical snapshots, extracted source, superseded versions, and provenance records | Read-only reference and lineage; do not edit to create a new canonical version |
| **Deprecated** | A once-supported path scheduled for removal or migration | Compatibility maintenance only under an approved removal plan |

The current path-level register is [runtime-source-registry.json](runtime-source-registry.json). It describes source ownership and maturity, **not a production deployment certification**.

## 2. Canonical ownership map

| Domain / capability | Canonical source owner | Boundary |
|---|---|---|
| Final product display arbitration | `packages/identity-intelligence/catacaci/` | CAL is the sole authority for SHOW/BLOCK/REVIEW; it does not retrieve products or invent evidence |
| Eligibility and context | `packages/identity-intelligence/eepl/` | Produces eligibility/context evidence; it does not perform final display arbitration |
| User-declared cultural constraints | `packages/identity-intelligence/cultural_identity/` and the corresponding service contract | Use explicit declarations; never infer sensitive identity from appearance or location |
| Style preference interpretation | `packages/identity-intelligence/usi/` | Separate from fit confidence and hard-negative enforcement |
| Negative preference enforcement | `packages/preferences/npl/` | Hard negatives remain constraints, not ranking weights |
| Fit confidence and calibration | `packages/fit-intelligence/fci/` | Owns fit-confidence estimation/evaluation; uncalibrated heuristics cannot authorize SHOW |
| Wardrobe domain | `packages/wardrobe/` | Domain types and rules; persistence/API ownership remains in the service boundary |
| Shared DTOs/contracts | `packages/shared-contracts/` | Types and schemas only; no duplicated business policy |
| API orchestration | `services/api-gateway/` | Authentication, authorization, orchestration, and service adapters; no alternative policy implementation |
| Catalog | `services/catalog-service/` | Canonical product identity/metadata and catalog persistence |
| Commerce | `services/commerce-service/` | Merchant, offer, variant, inventory, cart, order, checkout and payment state |
| Marketplace browser boundary | `services/marketplace-bff/` | Public same-origin BFF routes; internal/admin operations remain private |
| USI/TAL persistence | `services/identity-learning-service/` | Consent-bound identity profile and temporal event storage; internal API |
| Other bounded APIs | Their service roots in the runtime registry | Their README, API contract, owning domain package, and workflow govern implementation maturity |

When a domain package and a service both contain code, the package owns reusable domain rules and typed contracts; the service owns transport, authorization, transactions, infrastructure adapters, and deployment. Do not copy domain policy into a second service.

### Decision authority is not duplicated

The accepted CaTaCaCi ADR defines the arbitration boundary. CAL is the only component that may convert normalized evidence into `SHOW`, `BLOCK`, or `REVIEW`. Evidence producers may veto within their defined hard-constraint domain, but they do not get a second display authority. TAL is a consented learning workflow, not a per-candidate arbiter. See [ADR-0001](adr/ADR-0001-catacaci-decision-contract.md).

### CFRP / CRFP naming hold

CFRP V6 is an archived candidate label, while CRFP has no verified in-repository specification. They are not aliases. Neither is a canonical runtime capability. Do not add integrations based on the spelling alone. See [ADR-0002](adr/ADR-0002-crfp-cfrp-contract-status.md).

## 3. Quarantine and archive rules

The following are not runtime import roots:

- `integration-staging/source-intake/` — preserved extracted source and intake records;
- `integration-staging/source-candidates/` — candidate bundles and recovered versions;
- `integration-staging/source-manifest.json` and associated lineage ledgers — provenance and integrity records;
- `integration-staging/recovered-*` and similar recovered monoliths — research references, not deployable services;
- `packages/**/candidates/` and `packages/**/experimental/` — isolated candidate implementations;
- `tests/cfrp_candidate/` — candidate-only tests, not production package tests.

Do not rename these directories to make them importable. Do not add the archive to `PYTHONPATH`, TypeScript path aliases, build roots, container contexts, or service runtime images. A canonical implementation must live in its owner path and must have its own source/provenance record.

The archive must remain intact unless a separate, explicit retention/legal decision authorizes otherwise. A candidate can be rejected or superseded without deleting its evidence.

## 4. Controlled promotion workflow

A contributor proposing behavior from a candidate must:

1. Identify the source bundle, original path, source line/section, source hash, current candidate hash, license, and known modifications.
2. Classify it as exact duplicate, near duplicate, unique, malformed, incomplete, dependency-bound, or rejected.
3. Compare its contract and behavior with the current canonical owner; record conflicts, especially policy, identity, consent, storage, and display authority.
4. Select one small coherent behavior. Do not wholesale-copy a project, service, model, or decision pipeline.
5. Port or reimplement that behavior under the canonical owner. Preserve provenance in the source-candidate lineage ledger and document why the implementation differs.
6. Add tests against the canonical contract: normal, boundaries, conflict/veto, missing/unknown, stale/untrusted, failure, replay/idempotency, and cross-user/cross-candidate cases as applicable.
7. Complete dependency/license review, secret and personal-data review, static/type checks, and relevant service integration tests.
8. Update the owner README, runtime registry if ownership/status changed, capability status, and release evidence where applicable.
9. Run the architecture checks and relevant service workflow. Report the exact commit, commands, results, skips, and limitations in the PR.

A source candidate must not become canonical merely because it is newer, larger, more feature-rich, passes compilation, or appears in a README.

## 5. Contributor first 15 minutes

From a clean checkout:

```bash
python --version
python scripts/validate_architecture.py
python scripts/validate_source_boundaries.py
python scripts/validate_release_gates.py
python scripts/audit_source_lineage.py --allow-unreconciled
python scripts/build_code_snippet_inventory.py --check
python -m unittest discover -s tests/architecture -v
python scripts/scan_source_secrets.py
```

Then read, in order:

1. [Monorepo governance](monorepo-governance.md) — layers and ownership.
2. [CaTaCaCi decision contract](adr/ADR-0001-catacaci-decision-contract.md) — the display authorization boundary.
3. [CRFP/CFRP status](adr/ADR-0002-crfp-cfrp-contract-status.md) — unresolved candidate naming.
4. [Marketplace production readiness](../marketplace-production-readiness.md) — release-blocking evidence.
5. The README and workflow for the service/package you intend to change.

Run the service's own tests from its documented working directory. The architecture commands above do not replace service tests, model validation, database recovery drills, or deployed E2E tests.

## 6. PR checklist

- [ ] I identified the canonical owner and inspected its current contract and tests.
- [ ] I did not import or deploy archived, candidate, or experimental code.
- [ ] I preserved source provenance for any promoted behavior.
- [ ] I changed one authoritative implementation rather than adding a duplicate policy path.
- [ ] I versioned any API/event/schema change and documented compatibility and migration behavior.
- [ ] I tested hard constraints, missing/unknown evidence, invalid identity/consent, and dependency failure where relevant.
- [ ] I reviewed dependencies, licenses, secrets, privacy, and logging.
- [ ] I updated the relevant README, registry, and capability/readiness status.
- [ ] I attached exact CI/deployment/evaluation evidence and stated what remains unverified.

## 7. What a green check does not mean

- Source-lineage integrity is not proof that every archived file maps semantically to its original source.
- Syntax, lint, unit, and container-build checks do not prove model accuracy, calibration, security, or live integration.
- A service health endpoint does not prove identity, database recovery, payment, or marketplace correctness.
- A deterministic CAL contract test with mocked passing evidence does not validate a real safety or FCI provider.
- A successful checkout redirect does not prove a captured payment or correct webhook reconciliation.

Production promotion is governed by the [release evidence matrix](../release/release-gates.json) and [production readiness runbook](../marketplace-production-readiness.md). Every blocking gate needs independently reviewable evidence for the exact release candidate.
