# Canonical decision flow

This is the target governance flow. It is an architectural contract, not a claim that every stage is implemented today.

    Request + user context
      -> input validation / consent / authorization
      -> EEPL: age, location, occasion, climate and eligibility
      -> cultural identity: declared constraints and severity
      -> USI: user style/identity alignment
      -> NPL: hard negative-preference veto
      -> fit intelligence: FCI and unresolved CFRP/CRFP candidate
      -> CaTaCaCi arbitration
           CAL: resolve conflicting evidence; show / block / review
           TAL: temporal state and identity-drift signals
           CAM: counterfactual audit and regression evidence
           CIL: privacy-governed aggregate signals
           VSL: versioned value-system governance
      -> auditable decision + explanation + correlation ID
      -> UI / Try-On / marketplace / checkout
      -> feedback event -> validated learning pipeline

## Precedence invariants

- Explicit user constraints and legally/safety-critical constraints cannot be overwritten by trend, popularity or a model score.
- NPL hard negatives veto candidates before ranking. Repeated rejection is evidence, not automatic irrevocable consent; the user needs a transparent correction path.
- Cultural rules operate on user-declared requirements and explicit context. Visual appearance is not a substitute for consent.
- Fit confidence expresses uncertainty. Low confidence triggers review, alternate-size flow or a clearly labeled estimate.
- CAL is an arbiter, not another scorer. It decides whether evidence satisfies rules and records why.
- Feedback changes learned state only through versioned, auditable updates; it never mutates a user's constraints invisibly.

## Legacy compatibility

The uploaded CDIC engine exposes APPROVED, BLOCKED and NEEDS_REVIEW. CaTaCaCi has a separate CAL arbitration contract. A future adapter may map legacy outputs, but the semantics are not assumed identical. Mapping, defaults and failure behavior need contract tests.
