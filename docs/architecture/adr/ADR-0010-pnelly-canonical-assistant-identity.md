# ADR-0010: PNELLY canonical assistant identity and Xari contract migration

**Status:** Accepted for implementation by product owner; commercial brand use remains subject to formal trademark clearance.
**Date:** 8 November 2026
**Supersedes:** ADR-0005's Xari canonical-name clauses and ADR-0006's Xari-runtime hold. Other product/service ownership decisions remain unchanged.
**Related:** ADR-0005, ADR-0006, ADR-0008, PR #118, issue #108.

## Context

The product owner has explicitly selected **PNELLY** as Cirvanna's canonical conversational assistant identity and requires the exact spelling PNELLY. Xari and Tari are legacy names from earlier source generations. This is an identity migration, not permission to create a second assistant, duplicate router, parallel memory store, or separate orchestration state.

The existing implementation path `services/xari`, its HTTP routes and its consumers are already established. Breaking those routes or requiring synchronized deployments would create avoidable risk. The product identity and runtime capability name can change without forcing a package-path or wire-contract migration in the same release.

The accepted product name does not establish trademark availability. The separate legal-clearance gate in ADR-0006 remains mandatory before commercial brand launch.

## Decision

1. **One assistant identity:** PNELLY is the sole canonical product-facing assistant and orchestration identity. Xari, Tari and Xyra are legacy aliases/source generations only. There is no independent Xari assistant or second PNELLY runtime.
2. **Preserve the source path during this slice:** Keep `services/xari` and the import package `xari` temporarily. This is a compatibility source path, not a separate service or product identity. Relocate it only in a later reviewed migration after every build, deployment manifest, import and CI path filter has been updated.
3. **Preserve the orchestration HTTP contract:** Existing `POST /v1/route`, `POST /v1/marketplace/search`, `GET /health`, `GET /ready` and `GET /capabilities` remain available with their existing request/response semantics. The contract remains version `1.0.0`; Xari-era clients do not need a route or payload change in this slice.
4. **Credential migration:** `PNELLY_API_URL` and `PNELLY_API_TOKEN` are the preferred paired configuration. `XARI_API_URL` / `XARI_API_TOKEN` and `TARI_API_URL` / `TARI_API_TOKEN` remain compatibility fallbacks. The BFF must never combine a PNELLY URL with an Xari/Tari token. If the PNELLY URL is selected but its paired token is absent or invalid, fail closed.
5. **Capability metadata:** `/capabilities` reports `canonical_name: PNELLY`, lists Xari/Tari/Xyra as legacy aliases, and explicitly declares that the Xari route contract is preserved.
6. **No fake completeness:** PNELLY must not claim persistent Twin generation, generated previews, calibrated fit, or completed model execution unless the corresponding owner service and validated provider prove it. Candidate retrieval is not CAL display authorization.
7. **Domain boundaries remain unchanged:** Wardrobe owns garments and wear history; USI owns positive style preferences; TAL owns consented learning observations; NPL owns explicit hard exclusions; EEPL supplies context eligibility; Catalog/Commerce own product and offer facts; FCI owns fit-confidence estimation; CAL remains the sole final SHOW/BLOCK/REVIEW display arbiter; Virtual Twin owns the user-specific representation; Virtual Try-On owns rendering orchestration; Complementer remains optional styling advice.
8. **Rollback:** Revert the PNELLY identity commit. Existing Xari routes and XARI/TARI credential fallbacks remain available; no database migration or secret rotation is required.

## Migration sequence

- **Release 1:** PNELLY canonical capability/service metadata and PNELLY-first paired credentials; preserve Xari routes and XARI/TARI aliases.
- **Release 2:** migrate deployment secret configuration and service consumers to PNELLY names; observe legacy credential use without logging secret values.
- **Release 3:** relocate the source/package path only after Docker builds, manifests, imports, CI path filters and release automation target the new path; keep a compatibility shim for at least one release.
- Remove legacy aliases only through a separate reviewed ADR and measured deprecation window.

## Verification

- Tests prove PNELLY credential precedence and XARI/TARI fallback behavior.
- The BFF fails closed when the PNELLY URL is configured without its matching token; it does not borrow a legacy token across providers.
- Tests prove existing route paths and payload schemas remain unchanged.
- Capability metadata reports PNELLY as canonical and legacy aliases accurately.
- CI includes Marketplace BFF, assistant API/routing and relevant gateway contracts.
- No persistent Twin, real VTON renderer, live user identity provider, CAL-approved products, trademark clearance, or staging/production deployment is certified by this ADR.

## Consequences

PNELLY becomes the single assistant identity without a flag-day API or source-path migration. The old Xari contract remains an interoperability surface during the compatibility window. Commercial launch under the PNELLY mark remains blocked pending formal legal clearance in each intended market.
