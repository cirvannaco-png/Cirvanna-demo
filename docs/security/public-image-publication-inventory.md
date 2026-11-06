# Public image publication inventory and fail-closed contract

**Audit snapshot:** 6 November 2026, branch feature/outfit-evaluation-publication-guards.
**Status:** existing marketplace outputs withhold image URLs; the central gate is stricter and tested. Global publication safety is NOT certified because no Content Lifecycle service or complete publish/restore/share route inventory exists in this repository.

## Known image-bearing boundaries

| Surface | Current behavior | Evidence / release condition |
|---|---|---|
| API Gateway marketplace discovery, POST /v1/discover | CAL-authorized product and offer payloads return empty image_urls; tests inject unmasked Catalog and Commerce URLs and assert both are removed. | services/api-gateway/app/main.py; services/api-gateway/tests/test_marketplace_discovery.py |
| Commerce marketplace offers, GET /marketplace/offers | Returns image_urls as an empty list. | services/commerce-service/app/main.py; services/commerce-service/tests/test_commerce.py |
| Vision text search, POST /v1/search/text | Removes top-level and nested product image URLs unless separately attested; current implementation withholds them. | services/vision-intelligence/app/main.py |
| Vision Click It, POST /v1/click-it/scan | Detector/mask must run before quality scoring, embedding and catalog retrieval; original decoded image is closed before quality scoring; response is no-store and reports image_persisted=false; candidate image URLs are withheld. | services/vision-intelligence/app/main.py; services/vision-intelligence/app/click_it_privacy.py; services/vision-intelligence/tests/test_api.py; services/vision-intelligence/tests/test_click_it_privacy.py |
| Catalog product CRUD and batch reads | Image URLs remain in Catalog records, but these endpoints require the internal Catalog read/write token. They are not public publication routes and must not be exposed directly by a gateway. | services/catalog-service/app/main.py |
| Merchant listing creation | Authenticated merchant workflow snapshots Catalog image URLs for the merchant's own listing. Customer-facing Commerce offers still return no image URLs. If a future merchant/customer surface displays these assets, it must call the publication gate first. | services/commerce-service/app/main.py; services/commerce-service/tests/test_commerce.py |

## Central publication gate

The internal Privacy Governance endpoint accepts five target surfaces: public_profile, community_feed, marketplace, merchant_surface and shared_link.

A PASS now requires a trusted Vision provider receipt that:
- matches the opaque asset ID and the SHA-256 digest of the exact asset bytes;
- carries an active, independently human-reviewed privacy decision bound to that same digest;
- confirms all detected faces were masked before publication, zero unmasked faces remain and all detected regions were processed;
- confirms no face recognition, face embeddings or age estimation occurred; and
- identifies a valid SHA-256 digest for the pinned masking model.

Missing providers, digest mismatch, missing human review, stale/revoked receipts, incomplete masking or unsafe processing block publication. A prior receipt cannot be replayed after the asset bytes change.

## Main-branch exposure versus PR protection

The 6 November comparison found a real main-branch leak: Commerce GET /marketplace/offers returned the stored Listing.image_urls, and the unauthenticated Marketplace BFF proxy passed those URLs through. The Commerce test on main also asserted that the public offer returned the merchant listing URLs.

PR #107 corrects this: its Commerce public-offer serializer always emits an empty image_urls list; its Marketplace BFF strips top-level and nested image_urls as defense in depth; and the Commerce/BFF tests now inject unmasked URLs and assert that they are withheld. These fixes are present in feature/privacy-governance-service (and therefore in the stacked branch for PR #111), but PR #107 remains an open draft and has not been merged or deployed. **Do not treat main or production as protected until that change is merged, deployed, and rechecked against the public BFF URL.**

## Critical coverage gap

The repository tree has no Content Lifecycle service and no implemented public profile, community-feed, shared-link, restore or syndication publisher to wire to this gate. Therefore the gate is currently a tested policy contract, not a globally enforced publication middleware. Existing marketplace response tests show that the known product-discovery surfaces withhold URLs; they do not prove protection for absent services, external applications, CDN origins or future routes.

**Release rule:** keep all public image URLs withheld until a provider-neutral Content Lifecycle owner exists and every upload, publish, restore, syndication, shared-link and merchant-publication route is inventoried and integration-tested against the gate. No bypass/fallback may publish an image when the provider is unavailable. Validate the exact asset digest at the storage/CDN origin, not from client-supplied metadata.

## Remaining live dependencies

- Provision and license the pinned face detector and verify its checksum in the deployed Vision worker.
- Provision the Vision attestation provider with exact asset digest binding and independent human-review evidence.
- Provision Content Lifecycle storage/quarantine/deletion/CDN invalidation and connect every publication path.
- Provision jurisdiction, guardian-authority and rights-authority providers; provide counsel-approved signed policy bundles.
- Run the real model against a consented representative image set and conduct adversarial false-negative review. Mocked detector tests are not model recall evidence.
- Run physical Android QA for Living Filters on the required device matrix; browser CI cannot substitute for camera, lifecycle, thermal or performance measurements.
