# Persistent Virtual Twin integration for Daily Looks

**Tracking:** issue #108  
**Current status:** not integrated into the Daily Looks request path. The Wardrobe page must continue to display the explicit unavailable state until the existing Twin service can return a persistent, user-scoped Twin and a verified preview.

## Integration boundary

Do not create a second Twin store inside Wardrobe or Recommendation Service. The Virtual Twin service remains the owner of persistent Twin profiles, avatar identity, model/asset versions, and preview generation. Wardrobe owns garment records; Catalog owns product facts; the Daily Looks composer owns outfit selection. The BFF is the authenticated orchestration boundary.

The public flow must be:

1. Browser session authenticates through Commerce.
2. Marketplace BFF resolves the user from the verified Commerce session. The browser never chooses `owner_user_id`.
3. BFF calls the existing Virtual Twin service using its internal service credential and the verified subject.
4. Twin service returns a versioned Twin snapshot and whether a preview can be rendered under the current consent state.
5. BFF sends the selected, eligible garment references and a pseudonymous look reference to the preview contract.
6. The renderer returns an opaque preview asset reference and status. The BFF returns only a short-lived authorized preview URL or a safe unavailable state.

The recommendation service must not receive raw facial/skin measurements, account identifiers, long-lived asset URLs, or storage credentials.

## Required contract

A confirmed service contract must support:

- User-scoped `GET current Twin` and versioned snapshot retrieval.
- Explicit consent state for persistent profile storage and preview/rendering. Revoked or missing consent fails closed.
- Stable `twin_id` plus immutable `twin_version`/snapshot version, so the same look can be re-rendered deterministically.
- Opaque asset IDs only in internal storage contracts; preview URLs must be short-lived and authorized.
- Render request idempotency keyed by Twin version + look reference + renderer/model version.
- Explicit result states: `ready`, `pending`, `unavailable`, `consent_required`, and `failed`. A missing model or missing asset must never be represented as a ready preview.
- Deletion/revocation propagation across Twin snapshots, uploaded assets, derived preview assets, caches, and associated learning records.
- Audit fields for model/renderer version, asset lineage, consent receipt, creation time, and deletion completion.

## Release acceptance

- [ ] Confirm the existing Virtual Twin service API, database owner, migrations, and asset-storage provider before adding code.
- [ ] BFF derives the Twin owner exclusively from the verified Commerce subject.
- [ ] Cross-user access tests prove one account cannot read or render another account's Twin.
- [ ] Persist a Twin update, restart services, and retrieve the same version from a second session/device.
- [ ] Render one approved wardrobe look against the stored Twin and verify garment/asset lineage.
- [ ] Missing or revoked consent blocks profile hydration and rendering.
- [ ] A missing model/asset returns a safe unavailable state and does not break Daily Looks.
- [ ] Twin deletion/revocation removes or queues deletion of original and derived assets; readiness does not claim deletion complete until the worker confirms it.
- [ ] Preview URLs are short-lived, HTTPS-only, not logged, and not included in the evaluation trace.
- [ ] Android physical QA confirms the preview panel, loading state, failure state, and permission/revocation state on the target handset.

## Current behavior

The Wardrobe page is connected to the Daily Looks BFF endpoint and can render the three role-specific wardrobe recommendations. It explicitly states that the result is a wardrobe recommendation, not a rendered try-on, when the Twin preview is unavailable. This is intentional. The current change does not claim that persistent Twin storage or the renderer has been completed.
