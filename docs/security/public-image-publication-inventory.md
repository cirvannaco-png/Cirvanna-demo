# Public image publication inventory and fail-closed contract

**Audit snapshot:** 6 November 2026.
**Status:** the known public marketplace image leak is fixed on main by merged PR #112. The broader gate has digest-bound, human-review requirements in draft PR #111. Global publication safety is NOT certified because no Content Lifecycle service or complete publish/restore/share route inventory exists.

## Known image-bearing boundaries

| Surface | Current behavior | Evidence / release condition |
|---|---|---|
| API Gateway marketplace discovery, POST /v1/discover | CAL-authorized product and offer payloads return empty image_urls; tests inject unmasked Catalog and Commerce URLs and assert both are removed. | services/api-gateway/app/main.py; services/api-gateway/tests/test_marketplace_discovery.py |
| Commerce marketplace offers, GET /marketplace/offers | Returns image_urls as an empty list. This fix is merged to main in PR #112. | services/commerce-service/app/main.py; services/commerce-service/tests/test_commerce.py |
| Marketplace BFF public offers | Independently strips top-level and nested product image URLs even if upstream regresses. Merged to main in PR #112. | services/marketplace-bff/app/main.py; services/marketplace-bff/tests/test_main.py |
| Vision text search | Removes top-level and nested image URLs from ranked candidates on main. | services/vision-intelligence/app/main.py; services/vision-intelligence/tests/test_api.py |
| Vision Click It upload | Main now returns 503 before decoding, scoring, embedding or catalog retrieval; PR #113 merged this temporary fail-closed stop because main had no masking stage. The masked pipeline exists in the unmerged #107/#111 branches, but is not active on main. | services/vision-intelligence/app/main.py on main; PR #113; masked candidate pipeline in #107/#111 |
| Catalog product CRUD and batch reads | Image URLs remain in Catalog records, but endpoints require internal Catalog credentials. They are not public publication routes and must never be exposed directly by a gateway. | services/catalog-service/app/main.py |
| Merchant listing creation | PR #111 changes the authenticated merchant listing workflow to persist and return no image URLs until an asset-bound masking receipt is verified. | services/commerce-service/app/main.py; services/commerce-service/tests/test_commerce.py |
| Virtual Try-On model worker | Returns a consented, private, no-store image response to its authenticated internal caller; this is not a public media URL or a publishing route. Real renderer/provider remains unconfigured. | services/virtual-try-on/model-worker/app/main.py; services/virtual-try-on/README.md |

## Central publication gate

The internal Privacy Governance endpoint accepts five target surfaces: public_profile, community_feed, marketplace, merchant_surface and shared_link.

A PASS requires a trusted Vision provider receipt that:
- matches the opaque asset ID and SHA-256 digest of the exact stored asset bytes;
- carries an active, independent human privacy review bound to that same digest, with review receipt, reviewer reference and timestamp;
- confirms every detected face was masked before publication, zero unmasked faces remain and every detected region was processed;
- confirms no face recognition, face embeddings or age estimation occurred; and
- identifies the SHA-256 digest for the pinned masking model.

Missing providers, digest mismatch, missing human review, stale/revoked receipts, incomplete masking or unsafe processing block publication. A prior receipt cannot be replayed after asset bytes change. The trusted provider must independently resolve the stored asset and verify its digest; a caller-supplied digest alone is not proof.

## Main-branch exposure versus PR protection

The 6 November comparison found a main-branch leak: Commerce GET /marketplace/offers returned stored Listing.image_urls and the unauthenticated Marketplace BFF proxy passed them through. Vision text search and Click It also exposed Catalog image URLs.

PR #112 is merged to main (merge commit 357ae63a5018306a6fc8ba3c218adec2f0018a2a). It fixes the known public marketplace surfaces in Commerce, Marketplace BFF and Vision. PR #113 is also merged (merge commit da63a343565392d9acb5078e74cbea25014090e7) and disables Click It uploads before image decoding until the masked pipeline is released. PR #111 adds further fail-closed protection for merchant listing persistence and strengthens the Privacy Governance gate. PR #107 remains a draft and contains the broader consent, image-rights and jurisdiction-aware privacy service.

**Production qualification:** merged source fixes are not proof of deployed production URLs. Recheck the deployed public BFF and Commerce endpoints after deployment. The Click It endpoint is intentionally unavailable on main until its masked pipeline is released. No production deployment is claimed here.

## Critical coverage gap

The repository still has no Content Lifecycle service and no implemented public profile, community-feed, shared-link, restore or syndication publisher to wire to this gate. Therefore the gate is a tested policy contract, not globally enforced publication middleware. Existing marketplace response tests prove only that known product-discovery surfaces withhold URLs; they do not prove protection for absent services, external applications, CDN origins or future routes.

**Release rule:** keep all public image URLs withheld until a provider-neutral Content Lifecycle owner exists and every upload, publish, restore, syndication, shared-link and merchant-publication route is inventoried and integration-tested against the gate. No bypass/fallback may publish an image when the provider is unavailable. Validate the exact asset digest at the storage/CDN origin, not from client-supplied metadata.

## Remaining live dependencies

- The Vision Dockerfile now provisions the versioned BlazeFace full-range model and verifies its exact size and SHA-256 during build; deploy that image and verify runtime readiness. A real, consented representative-image false-negative evaluation remains mandatory.
- Provision the Vision attestation provider with exact asset digest binding and independent human-review evidence.
- Provision Content Lifecycle storage/quarantine/deletion/CDN invalidation and connect every publication path.
- Provision jurisdiction, guardian-authority and rights-authority providers; provide counsel-approved signed policy bundles.
- Run the real model against a consented representative image set and conduct adversarial false-negative review. Mocked detector tests are not model recall evidence.
- Run physical Android QA for Living Filters on the required device matrix; browser CI cannot substitute for camera, lifecycle, thermal or performance measurements.