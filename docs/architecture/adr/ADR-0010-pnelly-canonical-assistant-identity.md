# ADR-0010: PNELLY canonical assistant identity and Xari contract migration

**Status:** Accepted for implementation on this feature branch; commercial brand use remains subject to trademark clearance.
**Date:** 6 November 2026
**Supersedes:** The canonical assistant-name decision in ADR-0005 and the Xari-preservation clauses in ADR-0008, PR #104, and issue #108.
**Related:** ADR-0005, ADR-0007, ADR-0008, PR #81, PR #104, issue #108.

## Context

The product owner has explicitly changed the canonical assistant name from Xari to **PNELLY**. This is an identity migration, not permission to create a second assistant, duplicate router, parallel memory, or separate orchestration state. The existing Xari API is already consumed by the Marketplace BFF and other service contracts; breaking those routes or requiring a synchronized deployment would create avoidable production risk.

PNELLY is the canonical product-facing assistant and orchestration identity. Xari, Tari and Xyra are legacy names retained only for compatibility and source lineage. The PNELLY brand remains subject to the legal clearance gate in PR #81.

## Decision

1. **One assistant runtime:** PNELLY is the only canonical assistant identity. There is no independent Xari assistant or second PNELLY runtime. The existing orchestration implementation is rebranded in place during the compatibility window; the old services/xari source path is retained temporarily so current build/deployment definitions and imports do not break. It is an implementation path, not a second product/service identity.
2. **Preserve the orchestration HTTP contract:** Existing POST /v1/route, POST /v1/marketplace/search, GET /health, GET /ready, and GET /capabilities routes remain available with their existing request/response semantics. Contract version remains 1.0.0 for this compatible release. No client must change merely because the assistant name changed.
3. **Credential migration:** PNELLY_API_URL and PNELLY_API_TOKEN become preferred configuration names. XARI_API_URL / XARI_API_TOKEN and TARI_API_URL / TARI_API_TOKEN remain fallback aliases during one migration window. If multiple names are configured, PNELLY takes precedence. Secrets are not copied, printed, or rotated by this code change.
4. **Canonical capability metadata:** /capabilities reports canonical_name: PNELLY, with Xari/Tari/Xyra listed as legacy aliases and an explicit compatibility marker for the preserved Xari routes.
5. **Domain boundaries remain unchanged:** Wardrobe owns garments; USI owns positive preferences; TAL owns consented learning events; NPL owns explicit hard exclusions; EEPL supplies context eligibility; Catalog/Commerce own product and offer facts; CAL owns product-display authorization; Virtual Twin owns the user-specific representation; Virtual Try-On owns rendering orchestration; Complementer remains optional styling advice.
6. **No fake completeness:** PNELLY must not claim a persistent Twin, generated preview, fit certainty, or completed model execution unless the corresponding owner service and validated provider prove it.
7. **Rollback:** Revert the PNELLY identity commit. The Xari routes and XARI/TARI credential fallbacks remain available, so rollback does not require database changes or secret rotation.

## Migration sequence

- Release 1: canonical capability identity and PNELLY-first credentials; preserve all existing Xari routes and XARI/TARI fallbacks.
- Release 2: migrate deployment configuration and consumers to PNELLY names; observe legacy credential/route use.
- Release 3: move source/package paths only after all Docker builds, deployment manifests, imports and CI path filters target the new path; keep a compatibility shim for at least one release.
- Remove legacy aliases only through a separate reviewed ADR and measured deprecation window.

## Verification

- Tests prove PNELLY credential precedence and XARI/TARI fallback behavior.
- Tests prove all existing route paths and payload schemas remain unchanged.
- Capability metadata reports PNELLY as canonical and legacy aliases accurately.
- CI must include Xari-era consumers and all marketplace/Twin/VTON contracts.
- This ADR does not certify trademark clearance, persistent Twin readiness, real renderer quality, or staging/production deployment.

## Consequences

The product identity changes immediately without forcing a flag-day API migration. The old Xari contract remains an interoperability surface while PNELLY becomes the sole product and runtime name.