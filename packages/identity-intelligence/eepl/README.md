# Eligibility and Environmental Policy Layer (EEPL)

**Status:** deterministic policy kernel implemented; service integration and policy-owner review are not yet certified.

EEPL evaluates explicitly supplied age, location, occasion, and climate context against versioned allowlists and age bounds. It does not infer missing context from appearance, identity, or location signals. If a configured required field is missing, the result is `REVIEW`; a violated rule produces `BLOCK`. A block dominates review reasons.

## Integration boundary

`core.py` is a pure domain policy kernel. It does not fetch location, infer age, make medical/legal determinations, or authorize display. A consumer should map EEPL `BLOCK` to a hard eligibility veto and EEPL `REVIEW` to a fail-closed review state in CaTaCaCi CAL. Passing EEPL is not equivalent to CAL `SHOW`.

## Verification

Run from the repository root:

```bash
python -m unittest discover -s tests/architecture -v
python scripts/validate_architecture.py
```

Production promotion still requires policy-owner review, versioned rule distribution, consent and data-minimization review, API contract tests, and end-to-end display-gate integration.


## Threshold-only age evidence

The pure EEPL context now supports `minimum_age_threshold` plus `minimum_age_threshold_met` for a trusted adapter that has already verified the provider attestation's signature, subject, request, purpose, policy ID/version, threshold and expiry. This is a boolean threshold proof; it is not a synthetic age and must never be populated from client input. It is accepted only when the attested threshold exactly matches the policy's `minimum_age` and no `maximum_age` rule is configured. A minimum-threshold proof cannot establish compliance with an upper age bound; that case remains REVIEW until a separate, supported upper-bound attestation contract is implemented and verified. Existing positional `EEPLContext` construction remains compatible.
