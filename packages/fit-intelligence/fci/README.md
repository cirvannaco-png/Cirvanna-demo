# Fit Confidence Index (FCI)

**Status:** typed estimate contract, evidence-coverage gate, offline calibration metrics, and a subject-disjoint / out-of-time predictive release validator implemented. There is still no trained production fit predictor or empirical calibration model certified.

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

## Predictive release validation\n\nThe predictive validator evaluates a candidate model against subsequently observed fit outcomes. It enforces a training/evaluation subject boundary, predictions strictly after the training cutoff, outcome timestamps after predictions, artifact and dataset SHA-256 identifiers, pre-registered thresholds, minimum sample/subject counts, and required market/category slices. It reports inconclusive, rejected, or candidate_pass; a candidate pass is not production approval and does not itself authorize a calibrated FCI signal.\n\nThe validator does not train or serve a model. No real validation cohort is bundled, and synthetic CI fixtures are not empirical evidence. Production promotion still requires an independently reviewed model adapter, representative consented outcomes, calibration and interval-coverage analysis, confidence/evidence-coverage stratification, measurement and subgroup-bias analysis, data provenance, temporal holdouts, drift policy, signed validation report, and end-to-end fit/return outcome validation.
