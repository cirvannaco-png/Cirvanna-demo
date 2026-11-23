# Eligibility and Environmental Policy Layer (EEPL)

**Status:** deterministic policy kernel implemented; service integration and policy-owner review are not yet certified.

EEPL evaluates explicitly supplied age, location, occasion, and climate context against versioned allowlists and age bounds. It does not infer missing context from appearance, identity, or location signals. If a configured required field is missing, the result is `REVIEW`; a violated rule produces `BLOCK`. A block dominates review reasons.

## Integration boundary

Request-body `age_years` is not verified age evidence. The API gateway currently suppresses client-supplied age before constructing `EEPLContext` and records it as `unverified_client_value` in strict context evidence. Consequently, a configured age-dependent rule returns `REVIEW` until an authenticated, purpose-appropriate age-evidence provider is integrated. Do not infer age from a face, image, name, profile styling, or other proxy. A future provider must bind the evidence to the verified subject, include source and observation/expiry metadata, and enforce data minimization.


`core.py` is a pure domain policy kernel. It does not fetch location, infer age, make medical/legal determinations, or authorize display. A consumer should map EEPL `BLOCK` to a hard eligibility veto and EEPL `REVIEW` to a fail-closed review state in CaTaCaCi CAL. Passing EEPL is not equivalent to CAL `SHOW`.

## Verification

Run from the repository root:

```bash
python -m unittest discover -s tests/architecture -v
python scripts/validate_architecture.py
```

Production promotion still requires policy-owner review, versioned rule distribution, consent and data-minimization review, API contract tests, and end-to-end display-gate integration.
