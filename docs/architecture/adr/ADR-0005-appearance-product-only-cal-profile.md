# ADR-0005: Explicit product-only CAL profile

- Status: Proposed for review
- Date: 2026-10-24
- Scope: Catalog-backed cosmetic and non-fit-sensitive appearance product display

## Context

The canonical CAL default correctly requires fit-confidence evidence. That requirement is appropriate for physical fit-sensitive candidates such as apparel and footwear. It is not semantically valid to invent a fit-confidence score for a lipstick, cleanser, or other catalog-only product.

## Decision

Add an explicit `require_fit_confidence` option to the canonical `ArbitrationRequest`, defaulting to `true` to preserve existing behavior. The appearance package sets it to false only for registry-declared non-fit-sensitive product domains. This skips the physical-fit gate only; safety, legal eligibility, user constraints, NPL, cultural requirements, context eligibility, and identity-alignment evidence remain required.

The caller controls this profile in trusted server-side code, not from request payloads. Apparel, eyewear and footwear remain fit-strict. A missing fit provider never becomes a synthetic score or a passing fit signal.

## Consequences

- Existing callers remain fit-strict because the default is unchanged.
- Product-only decisions can be made without conflating product metadata matching with physical fit confidence.
- Safety/legal evidence remains UNKNOWN by default, so catalog records alone do not get an unconditional SHOW.
- CAL remains the sole display authority; this change does not implement recommendation ranking, virtual try-on, or checkout authorization.
