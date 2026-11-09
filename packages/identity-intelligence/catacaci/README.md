# CaTaCaCi decision core

**Owner:** Canonical decision arbitration. **Status:** initial deterministic Python core implemented; production integration not certified.

CaTaCaCi governs the decision process. CAL is the final arbitration authority—not a recommender or another weighted score. TAL handles temporal learning, CAM counterfactual auditing, CIL privacy-governed collective intelligence, and VSL controlled value-system evolution. The executable core in `core.py` is the first CAL contract and remains deliberately independent of persistence, model inference, and network services.

## Initial contract

The current arbitration contract is **1.1.0**.

- **Verdicts:** `SHOW`, `BLOCK`, and `REVIEW`. Only `SHOW` authorizes display; `REVIEW` is fail-closed.
- **Hard-veto precedence:** safety, legal eligibility, user hard constraints, NPL hard negatives, cultural requirements, and context eligibility cannot be overridden by high scores.
- **Required gate coverage:** safety, legal eligibility, user hard constraints, NPL hard negatives, cultural requirements, context eligibility, identity alignment, and fit confidence are required by default. A missing gate routes to `REVIEW`; a required gate marked optional upstream cannot bypass this rule.
- **Unknown evidence:** an unknown required signal routes to `REVIEW`; it is never silently treated as a pass.
- **Fit confidence:** missing confidence or confidence below the configured threshold routes to `REVIEW`. Conflicting fit-confidence sources are not averaged; a disagreement greater than 0.10 routes to `REVIEW`.
- **Determinism:** signals are ordered deterministically, identifiers must be unique, and confidence values must be finite and within [0, 1].
- **Explainability:** every verdict includes reason codes, explanations, evaluated signal IDs, and contract/policy versions.

## Scope and limitations

This is an initial, dependency-free arbitration kernel, not the complete CaTaCaCi architecture. TAL, CAM, CIL, and VSL are not implemented by this module. No production service currently proves that all upstream signals are correctly computed, calibrated, consented, or connected. The 0.70 default fit threshold and 0.10 disagreement tolerance are configurable engineering defaults, not empirically validated business or clinical thresholds.

Run the contract tests from the repository root:

```bash
python -m unittest discover -s tests/architecture -v
python scripts/validate_architecture.py
```

Before promotion, add property-based and adversarial tests, validate policy ownership and versioning, connect only trusted typed signals, and verify the end-to-end display gate in the consuming service.


## Governance extension contracts — initial kernels

The following pure contracts now accompany the CAL arbitration core:

- **TAL** (`tal.py`): consented, idempotent temporal events; latest-value reads are user-scoped and respect expiry without resurrecting stale values.
- **CAM** (`cam.py`): records observed-versus-simulated CAL verdicts and changed signal IDs. Counterfactual scenarios are explicitly not causal claims.
- **CIL** (`cil.py`): contributor-deduplicated cohort aggregation with a minimum-contributor suppression threshold. This is **not differential privacy**.
- **VSL** (`vsl.py`): versioned priority proposals require a distinct approver; safety and legal eligibility remain invariant top priorities.

These are domain contracts and in-memory/pure-function implementations, not production services. Durable event storage, replay infrastructure, privacy-preserving aggregation, access controls, approval workflow, observability, and end-to-end tests remain open.


## Decision-quality event aggregation

The quality_monitor module defines a privacy-minimized event contract and offline snapshot for CAL verdict counts, non-SHOW display leaks, incomplete required evidence, provider failures, and fit outcomes that were actually observed after exposure. A displayed candidate with verdict other than SHOW is always critical. Missing outcomes are never imputed as failures or successes.

This is not a live metrics exporter, durable audit store, dashboard, alerting integration, or production monitor. The serving path must first persist complete versioned decision receipts and publish these events to the approved telemetry system without user IDs, raw measurements, images, or other unnecessary personal data.
