# CFRP V6 Integration Audit — 2026-10-18

## Scope and disposition

Reviewed the current `main` branch of `cirvannaco-png/Cirvanna-demo`, the staged CFRP V6 candidate, and the catalog-service status. This is a source-level review, not a claim that a full local test suite or production deployment was run.

**Disposition: do not promote the CFRP V6 candidate into canonical runtime paths yet.** Preserve it in `integration-staging` until blockers below are resolved and validated.

## Findings

### Blockers

1. **Learning-prior path can fail at runtime.** `src/core/epistemic_state.py` uses `np.array` but does not import NumPy. The failure occurs when `reinforce(..., prior=...)` is called.
2. **Snapshot restore is unimplemented.** `CFRPInstance._load_state()` reads a snapshot but ends in `pass`; state is not reconstructed after restart.
3. **Durable event replay is unimplemented.** The source comment says replay is needed, but no durable event store/replay path is wired. The in-memory reinforcement log is lost when the process exits.
4. **Persistence clients are simulations.** The Redis and S3 clients shown in the candidate use in-process dictionaries, not real Redis/S3. They must not be represented as durable production infrastructure.
5. **Decay invariant can reject ordinary long elapsed periods.** `EpistemicState.decay()` applies exponential decay, while `EpistemicInvariants.validate_decay()` caps decay using a separate linear daily bound. These formulas can conflict and raise an invariant violation during maintenance or advice generation.
6. **Actor queue cleanup is unsafe on exceptions.** `CFRPActor._run()` does not guarantee `queue.task_done()` for every dequeued message when execution raises, and exception handling does not reliably propagate failures for all paths. Shutdown can also block when the bounded queue is full.

### High priority

7. **Input validation is missing.** Reinforcement values and identifiers should be validated (including finite numeric values and an explicit accepted range) before changing state.
8. **Shared mutable metadata is returned by reference.** New states reuse `learning_metadata` and `context_features`; defensive copying or immutable value objects are safer.
9. **Maintenance task lifecycle needs correction.** The loop creates competing sleep/shutdown tasks and does not cancel/gather the pending task after the first completion. Repeated cycles can leak tasks.
10. **Per-user actor management is process-local.** A manager lock and in-memory instance map do not provide cross-worker coordination or distributed single-writer guarantees.
11. **Event log contract is incomplete.** Event schema/versioning, persistence acknowledgement, replay ordering, idempotency, retention, and corruption handling are not established.

### Marketplace boundary

The catalog service README explicitly describes the service as a **scaffold only**. It should own canonical product/garment identity, attribute validation, versioning, import, and persistence. Wardrobe ownership, fit prediction, personalization, ranking, and checkout should remain separate bounded contexts with explicit interfaces. This audit does not certify marketplace functionality.

## Required remediation sequence

1. Add focused unit tests reproducing the NumPy import failure, decay/invariant conflict, queue exceptions, and restart-state loss.
2. Define and validate the confidence/decay mathematics; align invariant checks with the actual decay function and test boundary cases.
3. Replace simulated persistence with explicit ports and production adapters, or keep the candidate clearly marked as a non-production reference implementation.
4. Implement versioned snapshot serialization, restoration, durable event replay, idempotency, and recovery tests before claiming persistence.
5. Make actor processing exception-safe: always complete queue accounting, propagate per-message results/errors, and implement bounded, cancellation-safe shutdown.
6. Cancel and await all pending maintenance tasks; test repeated start/stop and shutdown under queue saturation.
7. Add validation and defensive copying for state inputs/outputs.
8. Run syntax, type, unit, integration, dependency, and security checks in CI. Do not promote unless required checks pass.
9. Integrate CFRP with USI/CaTaCaCi only through documented contracts and tests; CFRP must remain an advisory/confidence input, not silently override hard NPL or cultural safety constraints.
10. Keep marketplace work in its catalog and commerce domains; do not mix product persistence, wardrobe ownership, fit prediction, or payment handling into CFRP.

## Promotion gate

Promotion is blocked until the runtime-failure paths and persistence/recovery blockers are resolved, tests pass, and reviewers confirm that the candidate is the intended source version. No existing canonical implementation should be overwritten without a diff and migration plan.

## Evidence and limits

This review was based on GitHub source inspection of the staged CFRP V6 candidate and the catalog service README. No claim is made that local tests, integration tests, load tests, or deployment verification were run as part of this review.


## 2026-11-03 naming correction

The earlier CFRP label in this audit was a typo. The canonical acronym is CRFP, with distinct marketplace and system-wide scopes. This source-level audit describes historical candidate material only; it does not establish which CRFP scope the candidate belongs to or authorize its promotion. Preserve the original source artifact, filename and hashes for provenance. See [ADR-0003](../architecture/adr/ADR-0003-crfp-marketplace-and-system-scopes.md).
