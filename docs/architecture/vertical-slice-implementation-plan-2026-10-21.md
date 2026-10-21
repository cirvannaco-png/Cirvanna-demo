# Cirvanna First End-to-End Vertical Slice

**Date:** 2026-10-21  
**Status:** Proposed execution plan; implementation and release evidence remain pending.

## Objective

Deliver one honest, testable purchase-decision path before expanding into the full beauty, fashion, fit, and visualization roadmap.

The first slice must accept a user-controlled preference profile, retrieve candidate catalog items, enforce hard constraints, produce a typed decision with reason codes, and expose the result through a documented API. It must never imply that a model ran when it did not.

## Scope

1. **Catalog contract:** define and validate stable product identifiers, required metadata, optional attributes, and explicit unknown/missing-data semantics.
2. **Preference contract:** represent user-stated style preferences, explicit hard negatives, user-directed cultural requirements, and applicable context. Do not infer sensitive identity from images.
3. **Deterministic decision core:** enforce legal/safety/consent/eligibility constraints and hard negatives before any ranking. Return SHOW, BLOCK, or REVIEW/INSUFFICIENT_EVIDENCE with stable reason codes.
4. **API composition:** connect existing canonical services through documented contracts. Keep policy logic out of the browser and avoid duplicate implementations of CaTaCaCi/CAL.
5. **Persistence:** select and implement the smallest durable persistence boundary required by this slice; document ownership, migrations, deletion, and tenant isolation.
6. **Demo UI:** show candidate products, decision outcome, reasons, and uncertainty. Clearly distinguish unavailable capabilities from successful analysis.
7. **Evidence:** add unit, contract, integration, security, and end-to-end tests, recording the commit and exact commands/results.

## Explicitly out of scope for the first slice

- Production checkout or payment processing.
- Claims that fit predictions, skin analysis, virtual try-on, or Virtual Twin generation are validated.
- Promotion of files from `integration-staging/source-candidates/` directly into runtime without lineage review and parity tests.
- Performance, conversion, or return-reduction claims without measured evidence.

## Required decision invariants

1. Consent, legal, safety, and eligibility vetoes cannot be overridden by a relevance score.
2. Explicit hard-negative preferences cannot be overridden by popularity, trends, or learned preferences.
3. User-directed cultural requirements are applied only according to explicit user settings and defined severity.
4. Missing, conflicting, stale, or insufficient evidence returns REVIEW rather than fabricated certainty.
5. Every decision includes a correlation identifier, reason codes, contract version, and policy version where applicable.
6. Logs contain only necessary decision metadata and avoid unnecessary sensitive personal data.
7. A failed dependency produces a documented safe error/fallback; it must not silently return mock success.

## Execution order

### Gate 0 — Repository reality check
- Inspect current `main`, dependency manifests, service entry points, test commands, CI workflows, and branch-specific changes.
- Confirm the current state of catalog service, API gateway, identity/policy packages, and demo UI.
- Run available baseline checks before editing; record failures as well as passes.
- Keep the preserved source archive isolated.

**Exit evidence:** commit SHA, inventory of actual runtime entry points, reproducible baseline commands and results.

### Gate 1 — Contract alignment
- Reconcile canonical product IDs and data schemas across catalog and consumers.
- Reconcile USI, NPL, EEPL, cultural policy, fit-confidence, and CAL request/response contracts.
- Resolve naming drift (including CRFP/CFRP and legacy Tari/Xyra versus canonical Xari) in documentation and interfaces without deleting source lineage.
- Define reason-code registry and error envelope.

**Exit evidence:** contract tests and documented ownership.

### Gate 2 — Deterministic decision service
- Implement or integrate one canonical policy path.
- Test positive cases, every hard veto, conflicting preferences, missing fields, stale data, and dependency failure.
- Prove that scores cannot bypass hard constraints.

**Exit evidence:** unit and contract tests with explicit conflict-case coverage.

### Gate 3 — API plus durable data
- Connect catalog lookup, preference input, and decision service through actual service interfaces.
- Add persistence only for the entities required by the slice.
- Verify authorization, consent handling, tenant boundaries, and deletion behavior.
- Keep credentials in the deployment secret manager; reject unsafe defaults.

**Exit evidence:** integration tests against the selected persistence implementation and API.

### Gate 4 — Usable demo
- Present candidate, decision, reasons, and uncertainty.
- Show clear unavailable states for unimplemented models and renderers.
- Ensure UI does not reimplement decision policy.

**Exit evidence:** end-to-end test from preference input through decision display.

### Gate 5 — Release review
- Run the complete relevant CI suite, secret/dependency checks, and deployment smoke tests.
- Record known limitations, rollback steps, and evidence.
- Do not declare production readiness until privacy, threat-model, reliability, and operational gates pass.

## Completion definition

The slice is complete only when a clean checkout can reproduce the documented build and tests, a real API request traverses the canonical decision path, the result is persisted where required, the UI presents the actual response, hard constraints are proven by tests, and failure cases are handled honestly.

A plan or passing unit test alone is not proof of end-to-end completion.