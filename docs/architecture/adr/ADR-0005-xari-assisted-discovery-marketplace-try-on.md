# ADR-0005: PNELLY orchestration, Complementer collaboration and marketplace Try-On

**Status:** Accepted — PNELLY supersedes Xari as canonical runtime identity. Operational readiness remains gated.
**Date:** 6 November 2026
**Supersedes:** The original Xari canonical-name and service-path decision. Domain ownership and API v1 schemas remain unchanged.
**Related:** ADR-0007, ADR-0008, issue #108.

## Context

Cirvanna has separate foundations for orchestration, Complementer advisory styling, marketplace discovery, Wardrobe, Virtual Twin and Virtual Try-On. The product owner selected PNELLY as the canonical assistant/runtime identity and requested migration from Xari without breaking existing orchestration clients. The existing runtime already exposes stable `/v1/route` and `/v1/marketplace/search` contracts. The old implementation must be moved behind PNELLY rather than duplicated.

The old Xari name remains in source paths, deployment configuration and v1 error codes. Those identifiers need a bounded compatibility period. This naming decision is not trademark clearance; complete Kenya and relevant international trademark, company-name and domain review before commercial launch.

## Decision

### 1. PNELLY is the single canonical orchestration runtime

- PNELLY is the canonical runtime, API identity and user-facing assistant name.
- The canonical implementation lives in `services/pnelly`.
- `services/xari` is a compatibility shim to the same implementation. It must not own independent business logic, state, memory or model execution.
- `PNELLY_API_URL`, `PNELLY_API_TOKEN` and `PNELLY_CHAT_API_URL` are canonical configuration variables.
- During migration, `XARI_API_*` aliases are accepted second and `TARI_API_*` aliases third. PNELLY wins when multiple values are configured. New clients and deployment definitions must use PNELLY variables.
- Existing v1 paths, request/response models, consent keys, candidate semantics and historic `XARI_*` error codes remain unchanged. A future error-code rename requires a versioned API contract.
- All aliases resolve to one runtime. There is no dual-run assistant, duplicate memory or separate orchestration state.

### 2. Preserve orchestration boundaries

PNELLY coordinates capabilities but does not take their domain ownership. Wardrobe owns garment records/lifecycle; USI owns positive style preferences; TAL owns consented learning events and receipts; NPL owns explicit hard exclusions; EEPL supplies context eligibility; Catalog owns canonical product identity/attributes; Commerce owns live merchant offers, inventory and transactions; FCI owns validated fit evidence; CAL is the only product-display authority; Virtual Twin owns persistent user-scoped representations; Virtual Try-On owns rendering and job orchestration.

PNELLY may plan or invoke only fixed server-configured upstreams. It must not accept caller-supplied service URLs, bypass consent, synthesize product/merchant/price/stock facts, override NPL, infer sensitive cultural attributes or bypass CAL. A route-planning response does not prove an upstream executed.

### 3. Complementer remains optional

Complementer supplies advisory outfit/styling composition when requested or explicitly enabled. It does not own user profiles, negative preferences, product facts, prices, stock, fit evidence or display decisions. Its output is reversible and explainable. It is not required for basic PNELLY search or Wardrobe operation.

### 4. Marketplace discovery

PNELLY may interpret natural-language product/look requests and retrieve candidates through the private Vision Intelligence adapter. Candidate scores are not probabilities, fit confidence or permission to display. Product facts and merchant offers come from Catalog/Commerce. NPL and explicit cultural requirements must pass before CAL; only CAL SHOW exposes eligible product and offer details. Different currencies require separately sourced, timestamped FX evidence.

### 5. Virtual Twin and Virtual Try-On

The browser calls only the same-origin Marketplace BFF. BFF derives subject identity from verified Commerce `/me`, keeps service tokens private and accepts no browser-supplied user/asset identifiers. Virtual Twin verifies purpose-specific resource-bound consent, stores owner-bound representations and source assets, and permits deletion after consent withdrawal. Asset access binds subject, asset, purpose and parent resource. Virtual Try-On verifies image-processing/Try-On consent, re-resolves the live Twin and Wardrobe garment, invokes the pinned FASHN worker, persists output privately with expiry, and rechecks consent and current source before preview reads.

The current Twin representation is a pose skeleton, not a calibrated body mesh, measurement model or fit guarantee. VTON output is a visual preview, not fit evidence. Production enablement requires a real GPU deployment with verified weights, successful pipeline initialization, validated inference samples, asset/consent/Twin dependencies and end-to-end staging evidence.

## Migration and compatibility

1. Move canonical implementation/tests to `services/pnelly`; replace old Xari modules with import shims.
2. New clients use PNELLY service path and environment variables. Xari/Tari variables remain read-only fallback aliases for a bounded transition period.
3. Keep `POST /v1/route`, `POST /v1/marketplace/search`, API v1 schemas and historic `XARI_*` error codes.
4. Change user-facing UI/docs to PNELLY. Historical ADR references and compatibility documentation may identify Xari as the previous runtime.
5. After telemetry proves legacy alias traffic is zero for the agreed period, remove Xari/Tari aliases in a separate release.
6. Rollback is a revert of runtime/BFF/UI migration commits. The import shim preserves v1 callers during migration.

## Verification

- PNELLY and Xari compatibility tests prove both import paths load the same implementation.
- PNELLY token precedence is tested over Xari/Tari aliases.
- Existing v1 schemas, paths, consent gates and stable error codes remain tested.
- BFF tests prove PNELLY configuration preference and legacy fallback behavior.
- Asset/Twin tests cover resource isolation, revocation, deletion and failure recovery.
- CI does not prove trademark clearance, GPU quality, deployment health or production staging.

## Consequences

Cirvanna has one canonical assistant/runtime called PNELLY, with a migration bridge for old Xari/Tari identifiers. One runtime coordinates bounded domain owners rather than becoming a monolith or spawning competing assistants.
