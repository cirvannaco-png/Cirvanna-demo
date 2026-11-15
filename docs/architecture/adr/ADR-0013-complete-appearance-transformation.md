# ADR-0013: Complete Appearance Transformation across Cirvanna

- Status: Accepted — shared contract foundation only; renderer and surface integration remain gated
- Date: 15 November 2026
- Owners: Product Architecture / DermalSight / Virtual Twin / Virtual Try-On / PNELLY / Wardrobe / Marketplace

## Context

The product requirement is broader than a hairstyle simulator. A person must be able to explore complete grooming, beauty, fashion and accessory combinations from their own source photograph or authorized Virtual Twin. The same look must remain coherent as the user moves between Cirvanna, Virtual Twin, Virtual Try-On, PNELLY, Wardrobe and Marketplace.

The supported discovery space includes hairstyles and length, hair texture and colour, hairlines, facial hair, brows, lashes, lipstick, makeup, skincare products and immediate cosmetic-finish previews, garments, shoes, jewellery and earrings, eyewear, hats/headwear, bags, hair accessories, nails and fragrance. Catalogues must remain expandable and must not encode conventional beauty norms, gender assumptions, cultural exclusivity or popularity as hard eligibility filters.

Existing services have intentionally separate responsibilities:
- DSI provides purpose-authorized, non-diagnostic skin and geometry evidence; its measurements and classifiers are not yet validated for all requested uses.
- Virtual Twin owns persistent person representation and private Twin asset references; production full-body mesh reconstruction/rendering remains a separate gate.
- Virtual Try-On owns render orchestration and private output lifecycle; its current worker is garment-oriented, not a general grooming/accessory compositor.
- Wardrobe owns user-owned item inventory and saved outfit records.
- PNELLY is the single canonical conversational assistant. Complementer remains an optional styling collaborator.
- Catalog/Commerce own product and offer truth; CAL remains the product-display authority.
- Asset Service owns private binary media and authorization/deletion.

Creating a second profile store or giving any assistant/model permission to override these owners would create conflicting state and unsafe display paths.

## Decision

### 1. One shared, versioned look composition

Adopt the provider-neutral contract in packages/appearance_intelligence as the common vocabulary for every appearance surface. Its primary entities are:
- Look ID and immutable look version;
- root source lineage (private source-photo asset IDs or authorized Twin ID/source assets);
- an ordered list of component operations;
- typed component, action, target-region, reference, user/recommendation provenance and styling parameters;
- a fidelity assessment bound to the exact look version, private output asset and SHA-256-pinned renderer revision.

A look can contain any number of operations and any expandable set of component variants. There is no fixed style catalogue, 12-image gallery limit or popularity-based exclusion. Infrastructure rate limits may protect capacity but must not restrict what aesthetic direction a user can request.

A subsequent edit starts from the original source lineage by default. It may branch from a previous render only when the user deliberately chooses that result; the branch must retain the original source references and explicit parent-render lineage. This prevents accumulated drift from silently replacing the user's original face.

### 2. Source fidelity and user autonomy

The user's uploaded photo is the authoritative source for photo-based transformations. A Twin transformation uses the user's currently authorized Twin representation. Every edit is local to its declared target regions unless the user requests another edit.

The renderer must preserve source identity, facial geometry, underlying skin tone, expression, pose, clothing, background and lighting outside the requested edit. The user may separately request hairstyle, colour, hairline, beard, brow, lash, lipstick, makeup, garment or accessory edits; a request for one component does not authorize edits to other components.

Hairline styling may alter the visible hairline silhouette as an explicitly requested simulation, but may not deform forehead or facial anatomy. It must not imply actual hair growth/restoration. Facial hair is opt-in and never inferred from gender. Cultural hairstyles and protective styles must be represented respectfully and be searchable by the user's chosen wording, not restricted to a presumed demographic.

Recommendations are grouped as harmonious, expressive, experimental, practical or transformational. These labels describe a recommendation approach, not a beauty score. The user can directly request any permitted style regardless of recommendation track, profile history, inferred geometry or conventional suitability. A DSI failure or declined DSI consent falls back to non-DSI exploration; it does not block the requested look.

### 3. Surface responsibilities

| Surface | Responsibility for the same look |
|---|---|
| Cirvanna core / Experience Lab | Entry point, source selection, look editor, catalogue exploration, compare, undo, reset, save and continue |
| DermalSight (DSI) | Optional skin-region, tone, facial-geometry and appearance observations with consent, provenance and uncertainty. Evidence only; no rendering or veto |
| Virtual Twin | Persistent person base, authorized body/face representation and Twin-bound look preview; must not become a duplicate wardrobe or product database |
| Virtual Try-On | Render orchestration for selected Catalog products and Wardrobe items, preserving look ID/version and asset provenance |
| PNELLY | Natural-language interface that turns the user's request into proposed component operations, explains options, searches authorized wardrobe/catalogue context and hands the selected look to the editor |
| Complementer | Optional advice on colour, silhouette, grooming and accessory coordination; no mandatory dependency and no final rendering/display authority |
| Wardrobe | Owned clothing, accessories and beauty/hair/skincare inventory; saved outfits/looks reference owned items and versioned look compositions without copying Catalog facts |
| Marketplace | Discover and compare current products across fashion, hair, beauty, skincare, makeup, jewellery and accessories; current Catalog/Commerce facts only, with CAL SHOW required before product/offer details are displayed |

Not every surface is a separate renderer. The shared look ID/version is the continuity mechanism; each surface invokes only the capability it owns. PNELLY cannot silently mutate a look, Wardrobe cannot claim a marketplace item is owned before verified ownership, and a preview cannot assert fit or product efficacy.

### 4. Component and provider boundaries

- Hair, hairline, facial hair, brows, lashes, lipstick, makeup, skincare-finish, apparel, footwear, jewellery, eyewear, headwear, bags and hair-accessory rendering require explicit region anchors, occlusion handling and category-specific validation.
- A renderer must be version-pinned, license-cleared for the intended commercial deployment, privately authenticated and independently quality-evaluated. One garment VTON model must not be treated as a universal renderer.
- DSI outputs may inform a renderer only when the exact attribute is validated, consented, current and authorized for that purpose. No unvalidated skin-tone result may drive shade ranking, skin recolouring or a product eligibility decision.
- Skincare products may be catalogued, compared and saved. A visual application preview may show an immediate cosmetic finish only; it may not fake long-term treatment results, biological improvement or clinical efficacy. Fragrance is a product/style reference rather than a face-rendering operation.
- Catalog/Commerce facts, offers, merchant information, price, stock, delivery and tax are never generated by PNELLY or the renderer. Product visibility still requires CAL SHOW. Try-On is not a fit guarantee or purchase authorization.

### 5. Consent, privacy and asset lifecycle

Separate consent purposes remain separate: image processing, DSI geometry, DSI skin/body analysis, Virtual Twin storage, Virtual Try-On/rendering, Wardrobe image storage, preference learning and global model training. One consent does not imply another. Consent must be active, resource-bound, subject-bound, unrevoked and rechecked at the required lifecycle checkpoints.

Source and output images use opaque private asset IDs, not public URLs. The browser never supplies an authoritative subject ID or asset URL to a renderer. Outputs are private by default; failures, uncertain fidelity checks, consent revocation and deletion requests must prevent display and trigger the applicable cleanup workflow. Global model training requires its own separate rights, consent and evaluation gates; generated looks are not training data by default.

### 6. Fidelity and release policy

The shared contract requires a complete report for:
1. identity consistency;
2. facial geometry preservation;
3. underlying skin-tone preservation;
4. unaffected-region preservation;
5. hairline integration;
6. hair/facial-hair realism;
7. garment/accessory occlusion and placement;
8. lighting consistency;
9. anatomical correctness;
10. photographic credibility.

The assessment is bound to the exact look version and renderer digest. The core identity, geometry, skin-tone, unaffected-region, lighting, anatomy and photographic checks must all pass. A failed check is withheld; an uncertain check requires review. A visually attractive render is not acceptable if it changes the person's face. Identity consistency validation must not introduce face recognition, identity matching or identity embeddings.

The contract tests verify schema invariants, not photorealism. A production renderer still requires independent human-reviewed evaluation, source/output region comparisons, demographic and device/lighting subgroup evidence, private asset lifecycle testing, and commercially valid model/weight licensing.

## Current repository reality and non-claims

This ADR does not make all component renderers available. Current Virtual Try-On is garment-oriented; it does not yet render hairstyles, hairlines, beards, brows, lashes, lipstick, makeup, skincare finishes, hats or jewellery. Virtual Twin currently has guarded orchestration foundations but not validated full-body reconstruction and persistent rendering. DSI still has unvalidated geometric ratios/coarse segmentation and an experimental colour-calibration preview; absolute body/skin tone alignment is not established. Wardrobe and Marketplace category records do not themselves mean every product provider or try-on adapter is live.

Do not claim that Cirvanna currently generates photorealistic, identity-preserving transformations for every category. Keep each unsupported operation visibly unavailable or in an explicitly experimental state. Never show a fake successful preview.

## Consequences and implementation sequence

1. Shared look contract and architecture tests (this ADR's first increment).
2. Extend Wardrobe's stable item taxonomy and saved-look references while preserving owner-scoped persistence and explicit storage consent.
3. Add a trusted BFF look-session/editor flow with original-source reset, per-component edits, versioning, undo/branch and comparison gallery.
4. Generalize Virtual Try-On orchestration to multiple typed private assets and renderer adapters, while retaining the current garment worker as one adapter.
5. Add separately licensed and evaluated head/hair/beard/makeup/accessory renderers with occlusion anchors and per-category fidelity gates.
6. Connect PNELLY to the shared look contract and wardrobe/catalog context; add only user-approved edits.
7. Expose validated DSI attributes to Twin/Try-On as optional evidence, gated by consent and evidence version.
8. Add independent human-reviewed visual evaluation and device/skin-tone/capture-condition coverage before enabling production features.

No step may bypass CAL, user consent, asset authorization, canonical domain ownership or user-directed discovery.
