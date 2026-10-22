# Canonical decision flow

This is the target governance contract. It is not a claim that every provider or service is production-ready. See [ADR-0001: CaTaCaCi is a decision contract, not a stack of cognitive services](adr/ADR-0001-catacaci-decision-contract.md) for the normative rules.

```text
Request
  -> authentication / authorization / consent / schema validation
  -> canonical candidate + attribute coverage
  -> gather typed evidence from domain owners
       EEPL / legal eligibility / product safety
       explicit user hard constraints / cultural requirements
       NPL hard negatives / USI identity-style alignment
       FCI calibrated fit evidence
  -> normalize evidence once into the CAL contract
  -> CaTaCaCi / CAL (sole final display authority)
       BLOCK  = trusted hard-veto violation
       REVIEW = missing, unknown, conflicting, or insufficient required evidence
       SHOW   = all required gates pass and fit policy is satisfied
  -> persist minimal versioned decision receipt
  -> display / supported preview only for CAL SHOW
  -> consented feedback event -> validated, reversible preference learning
```

## Precedence invariants

- Safety, legal eligibility, explicit user hard constraints, NPL hard negatives, hard cultural requirements, and context eligibility cannot be overridden by style, trends, popularity, fit scores, or a model output.
- A missing or unknown required gate is not a pass. An unavailable policy/model provider must fail closed.
- Non-veto conflicts and insufficient evidence produce `REVIEW`; only an explicit `SHOW` authorizes display.
- NPL owns negative-preference semantics. Repeated rejection may inform learning, but it is not irrevocable consent; users need a transparent correction/removal path.
- Cultural rules apply to user-declared requirements and explicit context. Appearance is not consent and must not be used to infer protected identity.
- FCI confidence must reflect its actual evidence and calibration. Low confidence triggers review or a clearly labeled fallback, not an invented positive result.
- CAL is an arbiter, not a scorer. Retrieval and ranking can shortlist candidates but cannot bypass final arbitration before exposure.
- Learning and counterfactual tooling stay outside the synchronous authority path. Observed outcomes and simulated alternatives remain distinguishable.
- The display decision does not itself authorize checkout, a medical claim, or a claim that a virtual rendering is accurate.

## Execution model

The domain checks need not run in a rigid serial order. Independent evidence providers can run in parallel; high-value hard-veto checks may run early to avoid wasted computation. CAL evaluates the normalized evidence once, so provider execution order does not change decision semantics.

## Current implementation boundary

- `packages/identity-intelligence/catacaci/core.py` contains the deterministic CAL kernel.
- `packages/identity-intelligence/catacaci/pipeline.py` composes canonical EEPL, NPL, USI and FCI contracts and submits signals to CAL.
- `services/api-gateway/app/main.py` calls the package-level pipeline and marks a candidate displayable only when CAL returns `SHOW`.
- The service-level `services/api-gateway/app/decision_pipeline.py` is a second composition adapter. It must not become a second source of decision policy.
- The gateway currently has no independent safety policy provider and no calibrated FCI provider. Its default response should therefore remain fail-closed to `REVIEW`, not be represented as production-ready.
- The gateway's development SQLite audit stores verdict and reason codes, but not the full evaluated-gate trace/source versions needed for robust replay. Production release requires a durable versioned receipt written before response release.

## Legacy compatibility

The uploaded CDIC engine exposes `APPROVED`, `BLOCKED`, and `NEEDS_REVIEW`. CaTaCaCi has a separate CAL contract. A future adapter may map legacy outputs only after the semantics, defaults, and failure behavior have dedicated contract tests. No legacy decision may override CAL.
