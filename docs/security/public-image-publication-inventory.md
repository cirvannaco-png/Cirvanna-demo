# Public image publication inventory and fail-closed contract

**Audit snapshot:** 8 November 2026  
**Repository baseline:** main at `6428b41d8334b7579e2b9620bd4a12d523bcfa1b`  
**Status:** known marketplace serializers withhold unverified image URLs. Click It processing remains disabled on main. The privacy publication evaluator exists only in the unmerged Privacy Governance candidate stack. Global publication safety is **not certified**.

## Known image-bearing boundaries

| Surface | Main-branch behavior | Remaining requirement |
|---|---|---|
| API Gateway marketplace discovery, `POST /v1/discover` | Recursively removes unverified top-level and nested image URL fields. | Keep URL suppression until exact asset/version attestation is consumed by a publication owner. |
| API Gateway decisions, `POST /v1/decisions` | Returns no product image URLs. CAL display authorization is not media-publication authorization. | Do not reintroduce product media without the central gate. |
| Commerce marketplace offers, `GET /marketplace/offers` | Public offer response withholds image URLs. | Verify the deployed endpoint and all serializers after each release. |
| Marketplace BFF public offers | Recursively strips top-level and nested image URLs. | Maintain defense in depth even if upstream services change. |
| Marketplace BFF wardrobe recommendations, PNELLY search and Click It responses | Unverified media URLs are recursively removed from client-facing payloads. | Add exact asset authorization before returning any future media. |
| Vision text search | Removes unverified top-level and nested image URLs from candidate responses. | CAL and media-publication authorization remain separate checks. |
| Vision Click It upload | Main returns 503 before decode, quality scoring, embedding or catalog retrieval. | Keep disabled until masking, consent and resource-bound evidence are live. |
| Marketplace BFF Click It upload | Main returns 503, but the existing route declares multipart `Form/File` parameters, so framework parsing happens before the handler. PR #173 removes the photo picker and makes the route reject without reading/parsing the request body; it is open and unmerged. | Merge and verify PR #173 before treating the browser-facing upload route as non-ingesting. |
| Catalog product CRUD and batch reads | Product image URLs remain in internal Catalog records behind service credentials. | Never expose Catalog directly to a browser or public gateway. Use opaque, private asset references and authorization. |
| Merchant listing creation | Main returns empty image URLs publicly, but the current main implementation can retain sanitized HTTPS source URLs in the internal Listing row. | The privacy candidate hardening changes merchant ingestion to persist no image URLs until an asset-bound receipt exists. Reconcile and test this before merging any listing-image path. |
| Virtual Try-On worker | Output is private/no-store and internal; production renderer remains unavailable. | Never expose internal output storage as a public URL. |

## Central publication gate candidate

The Privacy Governance candidate provides:

`POST /internal/v1/privacy/assets/publication/evaluate`

A PASS requires all of the following:

- Opaque asset ID and SHA-256 digest for the exact stored object bytes.
- Trusted Vision attestation matching the same asset ID, digest and masking-attestation ID.
- Active attestation and approved, digest-pinned masking model.
- Independent human privacy review bound to the same exact asset digest, with a review receipt ID, opaque reviewer reference and timezone-aware timestamp.
- Every detected face masked before exposure, zero unmasked faces, and all face regions processed.
- Explicit evidence that face recognition, face embeddings and age estimation were not performed.

Missing providers, unavailable readiness, absent model pin, digest mismatch, missing/invalid review provenance or unsafe output block. The caller must not supply a boolean or a claimed digest as proof; the trusted Vision provider must independently resolve the stored private asset and verify its bytes.

This is still a **gate contract**, not global publication middleware. The Content Lifecycle/publication owner must invoke it immediately before every public publish, restore, syndication and share-link activation, then verify the same immutable object version/digest at the storage origin. A check performed earlier in a separate request is not sufficient protection against object replacement between authorization and publish.

## Critical coverage gap

The current repository does not contain a verified Content Lifecycle service that owns all public media mutation operations. The inventory includes absent or unverified routes for public profile photos, community feeds, shared links, restore, syndication, external CDN origins and derivative propagation.

Therefore:

- Marketplace image URL suppression is not proof of global media safety.
- A passing Privacy Governance endpoint test is not proof that a publisher calls it.
- An internal asset record or a valid HTTPS URL is not proof that the photo has been masked.
- Merchant image URLs must not be persisted or exposed merely because they are HTTPS.
- A missing, stale, mismatched, revoked or unavailable attestation must never fall back to publishing the original.

## Face detector qualification

The candidate Vision Docker image pins MediaPipe BlazeFace full-range by immutable versioned URL, exact byte count and SHA-256. The image build performs a real model-load and inference smoke test.

This is container-integrity evidence only. The upstream model card documents sensitivity to face scale, orientation, lighting and image conditions and reports 89.3% average recall across its named geographic subregions. That is not sufficient evidence to guarantee that every face is detected. A real, consented, representative Cirvanna false-negative evaluation and adversarial human review remain mandatory. The detector must not be described as a guarantee that every person has been found.

For safety, Click It remains unavailable on main while the pipeline is unmerged and external consent/attestation providers are absent. Even after integration, a face detector by itself cannot authorize a public image.

## Required live dependencies

- Trusted Vision privacy-attestation provider that independently resolves private asset bytes and verifies signed, digest-bound masking receipts.
- Counsel-controlled Ed25519 signing key and current signed jurisdiction policy bundles.
- Trusted jurisdiction resolution, guardian-authority verification and rights-requester-authority verification.
- Content Lifecycle provider for synchronous quarantine/unpublish, deletion propagation, CDN/cache invalidation, shared-link and merchant-surface revocation.
- Staffed independent human privacy review and image-rights removal operation.
- Production asset storage/versioning, migration, backup/restore, monitoring and byte-level staging evidence.
- Consent-based false-negative evaluation stratified by image conditions and target operating markets.

## Reconciliation notes

- PR #107 contains the Privacy Governance service, consent and image-rights workflows, provider-authenticated readiness probes, and the guarded Click It masking candidate. It is stale relative to main and has no exact-head CI evidence.
- PR #111 adds exact asset-digest/human-review publication evidence, a pinned BlazeFace model asset, masker resource cleanup, and merchant-image withholding. Its branch is based on an older point in #107 and regresses provider readiness to configuration-only checks.
- Branch `reconcile/privacy-publication-gate-hardening-2026-11-08` selectively ports #111's safeguards onto the latest #107 head while preserving #107's authenticated live readiness probes. This is a reconciliation candidate, not a main-branch release.
- PR #173 separately removes the Click It photo picker and multipart parsing from the disabled main-branch BFF route. It is not merged.

**Release rule:** keep public image URLs withheld and Click It unavailable until exact-head CI, independent face-masking evaluation, live provider readiness, immutable asset-digest verification, end-to-end publisher call-site coverage and deployment evidence are complete.
