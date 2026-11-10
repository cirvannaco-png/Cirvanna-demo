# Cirvanna Intelligence Layer — domain contracts

This package is the first implementation slice of the platform-wide Cirvanna Intelligence Layer. It is a pure-Python contract package; it does not yet provide an HTTP service, durable source registry, model hosting, automated ingestion, or production recommendation ranking.

## Responsibilities

- `source_registry.py`: explicit source ownership, access method, rights status, permitted purpose, attribution and expiry. Public visibility alone never authorizes commercial reuse.
- `evidence.py`: evidence grade, scope-bound product claims and a fail-closed claim assessment. Ingredient-level evidence cannot establish finished-product efficacy.
- `product.py`: canonical product ingredient declarations linked to product-specific evidence. Catalog remains the canonical product identity and version-history owner.
- `models.py`: model cards, validation populations, limitations, metrics and calibration requirements. Only independently validated, calibrated models can be marked eligible for user-facing assessment.
- `feedback.py`: purpose-bound-consent outcome events and cohort aggregation. Rejections, clicks, purchases and ignored recommendations are not converted into suitability outcomes without an explicit user report. A negative cohort signal requests review; it does not suppress or authorize a product.

## Run tests

From the repository root:

```bash
python -m unittest discover -s tests/intelligence_layer -v
```

The Catalog integration contract tests are under `services/catalog-service/tests` and run in the Catalog Service workflow.

## Boundaries

The calling service must verify active consent receipts, signed CAL decision receipts, source registry membership and source-rights status before creating or using events. The contracts validate their shape; they are not an authentication, authorization, privacy-preserving storage, or legal-compliance service. CAL remains the sole SHOW/BLOCK/REVIEW display authority.
