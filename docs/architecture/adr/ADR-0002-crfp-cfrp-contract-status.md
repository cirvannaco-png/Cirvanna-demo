# ADR-0002: CRFP and CFRP remain separate unresolved source labels

- **Status:** Accepted hold — no canonical CRFP/CFRP runtime contract
- **Date:** 2026-11-03
- **Scope:** Fit-intelligence naming, source promotion, and ownership boundaries
- **Supersedes:** No prior decision. This ADR refines the unresolved intake note in the monorepo governance document.
- **Review trigger:** A complete, attributable CRFP specification or implementation is submitted for comparison.

## Context

The repository contains two different references:

- **CFRP V6** is an archived source-candidate bundle at `integration-staging/source-candidates/05-cfrp-v6.txt`. Its inspected implementation models per-user signal reinforcement, confidence updates and decay, advisory adjustments, and an attempt to preserve USI autonomy.
- **CRFP** appears in prior architecture notes as a confidence/acceptance layer, but the repository does not currently contain an authoritative CRFP specification or a verified implementation that defines its public contract.

The names are not interchangeable merely because their letters are similar. The available evidence does not establish equal purpose, compatible inputs/outputs, equal veto semantics, or a common owner.

## Decision

1. **Do not select a canonical expansion or merge the names.** Keep CRFP and CFRP as distinct unresolved labels until their contracts are compared.
2. **CFRP V6 remains quarantined historical candidate material.** Its source files, bundle identity, hashes, and lineage records remain preserved. The directory `packages/fit-intelligence/cfrp/` is an intake/status marker only; it is not authorization for a runtime package, service, API, or import.
3. **CRFP remains an unverified architecture reference.** Do not create a package, service, endpoint, schema, event type, or product claim for it until an authoritative source and owner are supplied.
4. **Neither name has display, eligibility, fit-acceptance, or veto authority.** CAL remains the sole `SHOW` / `BLOCK` / `REVIEW` display-arbitration authority under ADR-0001. FCI remains the owner of fit-confidence estimation and calibration. NPL and other explicit hard constraints retain their existing precedence.
5. **No candidate is promoted by renaming.** A rename, folder move, or README change is not a contract comparison and must not be used to bypass the source-promotion gate.

## Evidence from the CFRP V6 candidate

The inspected candidate includes:

- a per-user `CFRPInstance` with per-signal confidence and reinforcement counts;
- reinforcement and time-decay updates with bounded confidence movement;
- an advisory adjustment based on confidence, recency, and event count;
- an invariant intended to cap CFRP influence and preserve a minimum USI contribution;
- a per-user actor queue that serializes work inside one process.

The inspected implementation also declares that persistence clients are simulations. Its lineage batch persistence method is a no-op, and its Redis abstraction is not evidence of a durable distributed state store. Its actor is process-local, not a distributed single-writer mechanism. The candidate therefore does not establish production durability, cross-process consistency, or a validated acceptance contract.

These observations describe the preserved candidate only. They do not certify its mathematical assumptions or recommend its behavior for live users.

## Required contract-comparison dossier

A future proposal must provide all of the following before a naming decision:

1. **Authority and provenance:** source owner, original specification, version, license, complete source bundle, content hashes, and known modifications.
2. **Purpose and boundary:** a one-sentence responsibility, explicit non-responsibilities, and overlap analysis against FCI, USI, NPL, TAL, EEPL, and CAL.
3. **Typed contract:** versioned request, response, identifiers, units, null/unknown states, error envelope, reason codes, and compatibility policy.
4. **State model:** what is stored, ownership/tenant key, retention, deletion, replay, idempotency, concurrency, and migration semantics.
5. **Scoring semantics:** equations, priors, update rules, confidence interpretation, bounds, calibration claims, decay behavior, and treatment of missing or conflicting evidence.
6. **Authority semantics:** whether outputs are advisory or binding. The proposal must not create a second display arbiter or weaken hard constraints.
7. **Trust boundary:** subject verification, consent, candidate/product binding, source freshness/version, signing, authorization, and failure behavior.
8. **Evaluation:** deterministic unit and property tests, contract tests, adversarial/conflict cases, replay tests, calibration evidence where probabilistic claims are made, and comparison against the existing canonical baseline.
9. **Operational evidence:** real persistence adapters, backup/restore, observability, performance/failure behavior, and rollback plan if a deployable boundary is proposed.

The comparison must produce an explicit disposition: merge as one concept, keep separate, rename one with a compatibility window, or reject/defer both. The decision must be recorded in a superseding ADR and reflected in the registry, docs, contracts, tests, and consumer imports in the same reviewed change.

## Consequences

Until that dossier is accepted, contributors must use the existing FCI contract for fit-confidence estimation and CAL for final display arbitration. They must not import CFRP V6 into canonical runtime, emit CRFP/CFRP values to production consumers, or describe either as a live capability.

The source archive and lineage remain intact. This is a deliberate hold, not a deletion or a claim that the underlying idea has no value.
