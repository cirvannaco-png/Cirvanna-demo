# Source reconstruction audit — 14 October 2026

## Scope and provenance

Audited GitHub branch `integration/source-reconstruction` at checkpoint `896fd3d`, then updated the architecture-validation workflow to run on integration and migration branches.

The repository tree at the checkpoint contained 565 tracked files. Of these, 530 were under `integration-staging/`, including 527 files under `integration-staging/source-candidates/`. Candidate file extensions included 356 Python files and 91 TypeScript files. The migration inventory tracks 31 labeled source snapshots and 14 architecture modules.

These counts describe repository contents, not the number of independently working modules.

## Findings

### 1. CI branch coverage gap — corrected on this branch

Before this audit, `.github/workflows/architecture-validation.yml` ran on pushes to `main` and `architecture/**`, plus pull requests targeting `main`. It did not run automatically when the active `integration/source-reconstruction` branch was pushed.

The workflow now also runs on pushes to `integration/**` and `migration/**`. The workflow still checks structural ownership and the source inventory only; it does not compile or execute all recovered application candidates.

### 2. Recovered Virtual Twin monolith is not production-ready

`integration-staging/recovered-virtual-twin.py` is a 938-line candidate with a title claiming production readiness, but static inspection found incomplete implementation points. In particular, `FitPredictionEngine.__init__` contains only `pass`, and its prediction method describes itself as a simple rule-based stub. The optional FastAPI import fallback also silently catches `ImportError`.

The candidate must remain staging material until its dependencies, import behavior, security controls, model integration, API contracts, and tests are verified. The README and user-facing claims must not describe it as certified or production-ready.

### 3. Candidate source has not passed a full verification pipeline

The branch now has CI checks for the architecture inventory, unit tests, and a lightweight credential-pattern scan. These checks are useful guardrails but do not verify every source candidate.

The first scan run identified credential-shaped database/cache/broker connection URIs and a test-fixture value in the staged snapshot tree. Representative URI examples use localhost or internal container-service hosts and development defaults; the exact values were not copied into this report. The scanner was narrowed to block on configured high-confidence patterns and HTTP(S) URL credentials, and explicitly reports that database/cache/broker URI credentials remain outside its coverage. **Before any candidate is promoted**, audit those connection strings, replace embedded credentials with environment-backed configuration, and rotate any value confirmed to be a real credential.

Python syntax/import validation across all recovered candidates, TypeScript typechecking, dependency vulnerability scans, full secret scanning, model-asset validation, service contract tests, and live integration tests have not been completed. The recovered tree must remain staging material until those gates pass.

### 4. Preserve variant lineage

The inventory correctly identifies duplicate and unresolved candidates, including CDIC, FCI, CFRP versus CRFP, Virtual Twin, Virtual Try-On, and Tari/Xyra versus Xari. Do not overwrite candidates merely because a filename or version number appears newer. Canonicalization must compare contracts and behavior, with regression tests.

## Next engineering sequence

1. Keep architecture, unit-test, and credential-pattern CI green on each integration branch.
2. Audit and externalize all database/cache/broker URI credentials in the staged tree; add a scanner for these schemes without printing values.
3. Add candidate-scoped Python syntax/import checks, TypeScript typechecking, and dependency vulnerability scans.
4. Select one module at a time, beginning with deterministic CAL arbitration and then trusted upstream gate adapters.
5. Keep source snapshots immutable; promote only reviewed variants into canonical package paths and add regression tests before wiring consumers.
6. Validate each promoted module independently and certify end-to-end behavior before any production-readiness claim.

## Current status

- Source checkpoint: preserved under `integration-staging/`; candidates remain untrusted and unpromoted.
- Initial CaTaCaCi/CAL deterministic arbitration core: implemented with typed verdicts, hard-veto precedence, deterministic reasons, fit-confidence checks, and required-gate coverage; TAL, CAM, CIL, and VSL are not implemented.
- CI: architecture inventory validation, focused unit tests, and the configured credential-pattern scan have passed on the latest completed branch check; these checks do not prove all-candidate runtime correctness.
- Embedded database/cache/broker development URI credentials remain a manual review and externalization gate before promotion.
- Full candidate syntax/type/security/dependency/integration certification: not complete.
- Production readiness: not certified.
