# Fit Confidence Index (FCI)

**Status:** typed estimate contract, offline calibration metrics, and evidence-coverage gate implemented; no production fit predictor or empirical calibration model is certified.

The FCI estimate carries confidence, uncertainty bounds, evidence provenance, model version and calibration version. The confidence assessment additionally reports declared required evidence categories, observed categories, missing categories and coverage ratio. Coverage and estimator claims enter the canonical CaTaCaCi pipeline as a CAL signal; the gate maps missing requirements, incomplete coverage, or an uncalibrated estimate to `UNKNOWN` so CAL routes the candidate to review.

The decision API accepts coverage fields only inside the provider-signed fit-evidence payload. The HMAC verification covers the canonical serialization of the complete fit object, including required/observed field lists. Do not treat unsigned client declarations as trusted model evidence.

## What this does not claim

- It does not train or run a fit-prediction model.
- It does not establish that confidence values are statistically calibrated or predictive of returns.
- Evidence-field coverage is not the same as model accuracy, measurement accuracy, or statistical calibration.
- A valid FCI assessment never overrides safety, legal, user hard constraints, NPL, cultural requirements, or other CAL gates.

## Verification

```bash
python -m unittest discover -s tests/architecture -v
python scripts/validate_architecture.py
```

Production promotion requires a reviewed model adapter, representative held-out outcomes, calibration and interval-coverage evidence, confidence/coverage stratification, measurement and subgroup-bias analysis, data provenance, and end-to-end fit/return outcome validation.
