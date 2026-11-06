# ADR-0008: PNELLY capability, Wardrobe integration and runtime naming migration

**Status:** Accepted for implementation; commercial brand use remains subject to trademark clearance.
**Date:** 6 November 2026
**Supersedes:** The previous ADR-0008 decision that treated PNELLY only as a Wardrobe companion and explicitly retained Xari as runtime. It preserves ADR-0007 domain ownership and the daily-look product decision.
**Related:** ADR-0005, ADR-0007, PR #81, PR #104, issue #108.

## Context

PNELLY was first introduced as the Wardrobe companion and daily-look capability. The product owner has now selected PNELLY as the canonical assistant and orchestration runtime as well. The previous distinction—PNELLY as a Wardrobe surface and Xari as the runtime—no longer reflects the product decision. The migration must not create two assistants or merge unrelated domain responsibilities.

## Decision

1. **One canonical runtime:** PNELLY is the only assistant/orchestration runtime. Canonical implementation: `services/pnelly`. The old `services/xari` code is a compatibility shim to the same implementation, not an independent service.
2. **PNELLY retains the Wardrobe capability:** it coordinates the three daily-look roles—Everyday, Elevated and Explore—through Wardrobe and the existing decision gateway. PNELLY does not own Wardrobe records or duplicate the user style profile. Recommendation service/Complementer remains advisory composition only.
3. **Canonical names:** `PNELLY_API_URL`, `PNELLY_API_TOKEN`, `PNELLY_CHAT_API_URL`, and `services/pnelly`. `XARI_*` and `TARI_*` are temporary configuration aliases. PNELLY wins if multiple values are configured. Historic `XARI_*` error codes and API v1 schemas remain until a versioned compatibility change.
4. **Routes:** `/v1/pnelly/daily-looks` and `/api/wardrobe/pnelly/daily-looks` are canonical daily-look routes. `/v1/tari/daily-looks` remains a hidden deprecated alias for one migration window and delegates to the same handler. Existing `/v1/route` and `/v1/marketplace/search` orchestration endpoints are preserved.
5. **Domain ownership:** Wardrobe owns garment records/lifecycle; USI owns positive preferences; TAL owns consented observations/receipts; NPL owns explicit hard exclusions; EEPL supplies context; Catalog/Commerce own product and offer facts; CAL alone authorizes product display; Virtual Twin owns persistent user representations; Virtual Try-On owns render orchestration and output assets. PNELLY coordinates but does not replace these systems.
6. **Media consent:** image processing, body-measurement processing, Twin storage, Wardrobe image storage and Try-On processing are distinct purpose scopes. Receipts are bound to subject, consent bundle and resource. Withdrawal affects the specified resource bundle, not another garment or Twin. Data deletion remains available after consent withdrawal.
7. **Virtual Twin/try-on status:** persistent Twin storage and private asset boundaries are implemented as service/API foundations on the feature branch. The current representation is a pose skeleton, not a full body mesh, calibrated measurement model or fit guarantee. The FASHN worker is a real model adapter in source, but real GPU inference and staging validation remain release gates until pinned weights, a checksum manifest, GPU runtime and end-to-end render evidence are supplied.
8. **Brand/legal gate:** PNELLY is the selected name, not a claim of registered or cleared trademark. Complete Kenya and relevant international trademark, phonetic similarity, domain and company-name checks before public commercial launch.

## Migration and compatibility

- Move runtime implementation, routing module, tests and workflow to `services/pnelly`.
- Retain `services/xari` only as an import shim; all requests and imports execute the same PNELLY runtime.
- New clients, deployment manifests and UI use PNELLY. Accept old Xari then Tari aliases only for the defined transition period, and instrument alias usage before removal.
- Do not rename persisted owner IDs, Wardrobe items, consent receipt IDs, Twin IDs or Try-On jobs. The migration is a service/product identity migration, not a data-owner migration.
- Continue hiding the deprecated Tari daily-look route from the browser; preserve it as an internal compatibility alias for one release window.
- Rollback: revert runtime/BFF/UI migration commits. Existing v1 routes and compatibility shim preserve old callers while rollback is reviewed.

## Verification

- Unit and import tests prove Xari compatibility imports are the same PNELLY module, not duplicated code.
- Route/auth tests prove PNELLY-first token precedence and legacy alias support.
- Contract tests preserve old v1 request/response shapes and historic error codes.
- UI and docs expose PNELLY, not Xari/Tari.
- Media tests cover resource-scoped consent revocation, cross-user isolation, deletion, retries and private asset access.
- A mocked renderer test is contract verification only. Real render quality must be validated with the pinned GPU worker and licensed evaluation set before production activation.

## Consequences

PNELLY now names both the Wardrobe companion capability and the single conversational/orchestration runtime. The architecture remains bounded: one runtime coordinates many domain owners, rather than becoming a monolith or spawning competing assistants.
