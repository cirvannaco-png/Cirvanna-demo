# Fit Confidence Index (FCI)

**Status:** calibrated-estimate contract implemented; no production fit predictor or empirical calibration model is certified.

The FCI contract validates a model estimate's confidence, uncertainty interval, evidence provenance, model version, and calibration version. It maps a calibrated estimate into a typed CaTaCaCi fit-confidence signal. An uncalibrated estimate becomes `UNKNOWN`, which routes through CAL to review; it is never treated as a pass.

## What this does not claim

- It does not train or run a fit-prediction model.
- It does not establish that confidence values are statistically calibrated or predictive of returns.
- It does not invent weights, combine correlated evidence, or silently average disagreeing models.
- A valid FCI signal does not authorize display. CAL applies the configured threshold and final arbitration.

## Verification

```bash
python -m unittest discover -s tests/architecture -v
python scripts/validate_architecture.py
```

Production promotion requires a reviewed model adapter, held-out calibration evidence, interval coverage tests, demographic/measurement bias evaluation, data provenance, and end-to-end fit/return outcome validation.
