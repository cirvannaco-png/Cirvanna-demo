# Appearance Intelligence shared contract

**Status:** versioned domain contract and tests implemented. It is not a renderer, model, asset store, saved-look database, or proof that any transformation surface is production-ready.

This package defines the common appearance vocabulary that Cirvanna surfaces exchange. It allows a single look to combine hair, hair colour, hairline, facial hair, brows, lashes, lipstick, makeup, skincare-application previews, garments, footwear, jewellery, eyewear, headwear, hair accessories, bags, nails and fragrance/product references.

## Core rules

- A look has a stable look ID, monotonically versioned composition, and an immutable root source lineage.
- A source-photo look points to original private asset IDs. A Twin look points to the owner-authorized Twin and its source assets. A deliberate previous-render branch must retain both the prior render reference and the original source lineage.
- Each edit names exactly one component, action, target region and provenance. User-directed edits are distinct from recommendations the user explicitly accepted.
- The operation list is extensible. The contract has no fixed hairstyle list, style count, or 12-image gallery limit. Runtime quotas may protect service availability but must not become a style-discovery policy.
- Identity, facial geometry, underlying skin tone and all unrequested regions remain preserved by default and cannot be disabled in this contract.
- A user can explore experimental, culturally rooted, uncommon, classic or mainstream styles. Recommendation tracks describe the type of suggestion; they are not eligibility filters or beauty rankings.
- Output assets are private opaque asset references. URLs and arbitrary paths are not accepted.
- A render is releasable only after a complete fidelity assessment. Core identity/geometry/skin/region/lighting/anatomy/photo checks must be evaluated and pass. A failed or uncertain check withholds the output instead of silently changing the face.

## Ownership

The package contains schema and invariants only.

- DSI owns consented, non-diagnostic skin/geometry evidence and its uncertainty. It does not decide what the user is allowed to try or render the image.
- Virtual Twin owns the persistent user representation and authorized Twin assets.
- Virtual Try-On owns render job orchestration, request idempotency, provider provenance and output lifecycle.
- Asset Service owns private image/model/output bytes and access/deletion authorization.
- Wardrobe owns user-owned inventory and saved outfit/wardrobe records.
- Catalog owns canonical product identity and product attributes; Commerce owns offers, prices, inventory and transactions.
- PNELLY turns the user's natural-language request into a proposed look edit and optional discovery query. It cannot change the look without the user's action, invent product facts, or authorize product display.
- CAL remains the product-display authority. A visual preview is not a fit guarantee, product endorsement, skin-care efficacy claim or checkout authorization.

## Try-On coverage

The contract can describe non-garment components, but the current Virtual Try-On worker is garment-oriented. Hair, hairline, facial hair, makeup, brows, lashes, lipstick, hats, earrings and other accessory renderers require their own pinned and licensed adapters, occlusion/anchor logic, device evaluation and privacy review. A component must remain unavailable in a production UI until its actual renderer and acceptance evidence are ready.

Skincare product recommendations and saved product records are commerce/inventory items. A cosmetic application preview may depict an immediate finish only; it must not fabricate long-term biological results or imply treatment efficacy. Fragrance is a non-visual product/style reference.

## Validation

Run the shared architecture contract tests with:

    python -m unittest tests.architecture.test_appearance_intelligence -v

These tests verify contract invariants only. They do not validate model quality, photorealism, identity preservation, commercial licensing, consent deployment or rendering readiness.
