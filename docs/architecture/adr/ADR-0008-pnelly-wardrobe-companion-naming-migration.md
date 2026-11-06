# ADR-0008: PNELLY wardrobe companion and daily-look naming migration

**Status:** Accepted for implementation on the feature branch; commercial brand use remains subject to trademark clearance.
**Date:** 6 November 2026
**Supersedes:** The daily-look product-name decision in the initial Tari implementation contract only. It does not supersede ADR-0005's Xari runtime decision or ADR-0007's domain ownership boundaries.
**Related:** ADR-0005, ADR-0007, PR #81, PR #104, issue #108.

## Context

The daily three-look slice was initially labelled Tari. The product owner has now selected **PNELLY** (pronounced “Pinelly”) as the name for the wardrobe companion and its daily-look experience. ADR-0007 already defines PNELLY as the contextual companion surface within Wardrobe, connected to the user's wardrobe, EEPL context, USI/TAL learning and NPL exclusions. The old Tari label creates two names for the same product experience and must be retired.

PR #81 records PNELLY as a proposed brand and requires a migration ADR before changing service/UI naming. It also requires Xari to remain the current runtime identity pending legal review. This ADR satisfies the migration-decision gate; it does not constitute trademark clearance or authorize commercial launch.

## Decision

1. **PNELLY is the product-facing name** for the Wardrobe companion and the daily three-look experience. The three recommendation roles remain Everyday, Elevated and Explore.
2. **One runtime, not two assistants:** PNELLY is a product capability/surface, not a separately deployed agent, independent model runtime, identity store, wardrobe store, or profile database. The existing recommendation-service/Complementer capability performs advisory composition. Xari remains the shared conversational assistant/orchestration runtime under ADR-0005 and may coordinate PNELLY when conversational help is requested.
3. **Preserve canonical domain ownership:** Wardrobe owns garment records and lifecycle; USI owns positive preferences; TAL owns consented learning events; NPL owns explicit hard exclusions; EEPL supplies context eligibility; Catalog/Commerce own product and offer facts; CAL remains the product-display authority; Virtual Twin owns its future persistent representation; Virtual Try-On owns render orchestration.
4. **Canonical internal route names:** /v1/pnelly/daily-looks and /api/wardrobe/pnelly/daily-looks. The old /v1/tari/daily-looks route remains a hidden, deprecated compatibility alias for one migration window and delegates to the same handler. No duplicate implementation is permitted. No legacy Tari name is exposed in the user interface.
5. **No unnecessary service or secret rename:** Keep the existing services/recommendation-service, services/marketplace-bff, COMPLEMENTER_SERVICE_TOKEN, and Xari service credentials. Do not create PNELLY_API_TOKEN, a separate PNELLY service, or a second assistant identity.
6. **Virtual Twin remains honestly unavailable** until persistent user-owned Twin storage, purpose-specific server-side consent, authorized asset lifecycle, and a validated renderer pass issue #108's release gates. PNELLY must continue to provide wardrobe styling without pretending a pose skeleton or placeholder is a Twin preview.
7. **Brand/legal gate:** PNELLY is a selected product name, not a claim of registered or cleared trademark. Before public commercial launch, complete Kenya and relevant international trademark, phonetic similarity, domain and company-name checks described in PR #81.

## Migration and compatibility

- Update user-facing Wardrobe UI, CSS identifiers, docs, recommendation capability metadata, BFF/gateway paths, response capability identifiers and tests to PNELLY.
- Keep the deprecated internal Tari route as a hidden alias to the exact same handler for one release window. Record its usage before removal; do not add a second service or duplicate state.
- Browser UI calls only the PNELLY BFF route. Do not expose the legacy alias in UI, docs or new integrations.
- Existing persisted wardrobe, consent, USI/TAL, NPL, Twin or render data is not renamed or migrated because this change is a product label/route migration, not a data-owner migration.
- Rollback: revert the feature-branch migration commit(s); the old internal route alias remains available during the compatibility window. No database migration or production secret rotation is required.

## Verification

- Contract tests prove PNELLY canonical routes and capability metadata work.
- A compatibility test proves the hidden Tari alias delegates to the same PNELLY handler and returns the same schema.
- UI tests prove PNELLY is visible and the old name is absent from user-facing content.
- Existing ownership, consent, NPL, CAL, cross-tenant and fail-closed Twin-preview tests remain unchanged and pass.
- CI passing is not evidence of trademark clearance, persistent Twin readiness, real rendering, or production deployment.

## Consequences

The product has one clear Wardrobe companion identity, PNELLY, while retaining the already accepted Xari orchestration runtime and existing service ownership. The rename does not imply that PNELLY's full learning loop or persistent Twin integration is complete.