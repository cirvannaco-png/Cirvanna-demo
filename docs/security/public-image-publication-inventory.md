# Public image publication inventory and fail-closed contract

**Audit snapshot:** 22 November 2026  
**Repository baseline:** reviewed main at `bba0b82efa327300b48a1625ac39c626fa7b87d1`  
**Status:** marketplace serializers withhold unverified image URLs; the Privacy Governance publication evaluator and Vision face masker are present on main. Click It remains disabled at the public BFF before multipart parsing. Global publication safety is **not certified**.

This inventory distinguishes three separate authorities: CAL authorizes product/offer display; Identity/TAL authorizes the user's image-processing purpose; Privacy Governance plus trusted Vision attestation authorizes public media publication. None substitutes for another.

## Known image-bearing boundaries

| Surface | Current main behavior | Remaining requirement |
|---|---|---|
| API Gateway marketplace discovery, POST /v1/discover | Recursively removes unverified top-level and nested image URL fields. | Preserve suppression until the exact asset/version attestation is consumed by the publication owner. |
| API Gateway decisions, POST /v1/decisions | Returns no product image URLs. | CAL display authorization is not media-publication authorization. |
| Commerce marketplace offers | Public offer responses withhold image URLs. | Recheck every serializer after Commerce changes. |
| Marketplace BFF public offers and recommendations | Recursively strips unverified image URLs. | Maintain defense in depth; never expose Catalog directly to browsers. |
| PNELLY Look It | Authenticates the user, records and verifies a short-lived resource-bound image_processing + look_it consent bundle, sends the image to private Vision retrieval, returns aggregate counts and validated decomposition only, sets image_persisted=false, and withholds product/merchant/price/media details pending CAL. | The Vision Look It route now requires the pinned face detector and masks detected faces before quality analysis, image embedding and optional outfit decomposition; it closes the unmasked decoded image before downstream processing and closes the masked buffer on all exit paths. This source-level control does not prove detector recall, live detector provisioning or independent privacy acceptance. Look It retains its own consent/retrieval route and does not invoke Click It. PR #255 fixes immediate revocation of both consent receipts. |
| Marketplace BFF Click It upload, POST /api/vision/click-it | Rejects with 503 before multipart parsing, body reads or upstream calls. The handler accepts Request rather than FastAPI Form/File parameters. | Keep disabled until the resource-bound consent, masking, rights, private asset and publication-attestation path is connected end-to-end. |
| Virtual Twin internal Click It orchestrator, POST /click-it | Private API bearer only; verifies resource-bound Identity consent and current jurisdiction policy before reading the upload; forwards only to the private Vision Click It worker, which masks before quality analysis/embedding; returns aggregate candidate metadata with `image_persisted=false`, `display_authorized=false` and `public_sharing_allowed=false`. The service is `private_api` and not production-enabled. | Keep private and disabled in production until the detector is independently evaluated and the full consent, rights, asset and publication-attestation pipeline is verified. This route is now explicitly covered by the publication-route guard and machine-readable ingress inventory. |
| Vision Click It worker, POST /v1/click-it/scan | Requires worker auth and explicit scopes; detects and blurs faces before embedding; rejects uncertain detector output; drops original decoded image; no source image persistence; does not perform face recognition. | It is not publicly reachable through BFF. Requires pinned detector artifact, independent false-negative evaluation and consent/asset authorization from the orchestrator. |
| Vision text/image search | Withholds unverified image URLs and product/merchant/price details until CAL. | CAL display and public media publication remain distinct decisions. |
| Catalog product records | Internal service data can contain merchant-supplied source image references. | Keep records private; do not treat HTTPS or a Catalog image field as publication authorization. |
| Merchant listing ingestion | Main sanitizes source URLs but may retain them internally. | No public rendering until opaque asset ownership, exact-byte digest and publication receipt are verified. |
| Virtual Try-On and Twin assets | Internal/private outputs; public renderer and persistent Twin release remain gated. | No public URL or shared link without the central publication gate and deletion propagation. |
| Public profile, community feed, merchant surface, shared link, restore and syndication | No single Content Lifecycle owner/call-site inventory has been independently verified across every mutation path. | Audit every create, update, restore, syndicate, share, CDN origin and derivative route. Fail closed when a route cannot prove gate invocation. |

## Central publication gate on main

Privacy Governance exposes:

POST /internal/v1/privacy/assets/publication/evaluate

A PASS requires:
- An opaque asset ID and SHA-256 digest for the exact stored object bytes.
- Active, subject- and resource-bound consent with image_processing, click_it, public_media_publication and the applicable photographed-person declaration scopes.
- A trusted Vision attestation matching the same asset ID, digest, target surface and masking-attestation ID.
- An approved, digest-pinned masking model.
- Independent human privacy review bound to the exact same asset digest, with a review receipt ID, opaque reviewer reference and timezone-aware timestamp.
- Every detected face masked before exposure, zero unmasked faces, and all face regions processed.
- Explicit evidence that face recognition, face embeddings and age estimation were not performed.
- Minor media publication is prohibited.

Missing providers, unavailable readiness, absent model pin, digest mismatch, missing/invalid review provenance or unsafe output block publication. A caller-supplied boolean or claimed digest is not proof; trusted Vision must independently resolve the private asset and verify its bytes.

This is a gate contract, not global publication middleware. The Content Lifecycle/publication owner must invoke it immediately before every public publish, restore, syndication and share-link activation, then verify the same immutable object version/digest at the storage origin. An earlier check in a separate request is insufficient against object replacement between authorization and publication.

## Click It masking and detector qualification

The Vision Click It worker uses a face-detection-only MediaPipe BlazeFace full-range asset pinned by exact digest. It does not perform identity recognition, face verification, embeddings or age estimation. The worker rejects low-confidence/invalid detector output, masks detected regions in memory, discards the unmasked decoded image and returns no persisted source photo.

Container integrity and a model-load smoke test are not proof that every face is detected. A consented, representative Cirvanna false-negative evaluation across image conditions, lighting, pose, scale, skin tones and operating markets, plus adversarial human review, remains mandatory. A face detector must never be described as a guarantee that every person has been found.

## Rights, consent and deletion

The Privacy Governance service on main provides consent grant/revocation, jurisdiction policy, guardian-authority checks, image-rights intake, urgent quarantine/unpublication, review, deletion propagation and audit events. Merged [PR #265](https://github.com/cirvannaco-png/Cirvanna-demo/pull/265) exposes the public BFF consent and photographed-person rights intake/status routes. The earlier [PR #256](https://github.com/cirvannaco-png/Cirvanna-demo/pull/256) was closed as superseded by #265. The public API journey now exists in code, but live jurisdiction, identity, quarantine, deletion and provider integrations remain unverified.

Urgent reports for unmasked faces, possible minors or non-consensual images are not accepted unless quarantine and unpublication are confirmed. Removal is complete only when all required surfaces report deletion propagation, including CDN/cache, shared links, merchant surfaces and derivatives. A request receipt is not proof of completed deletion.

## Required live dependencies and release evidence

- Trusted Vision privacy-attestation provider that independently resolves private asset bytes and verifies signed, digest-bound masking receipts.
- Counsel-controlled Ed25519 signing key and current signed jurisdiction policy bundles.
- Trusted jurisdiction resolution, guardian-authority verification and rights-requester-authority verification.
- Content Lifecycle provider for synchronous quarantine/unpublish, deletion propagation, CDN/cache invalidation, shared-link and merchant-surface revocation.
- Staffed independent human privacy review and image-rights removal operation.
- Production asset storage/versioning, migration, backup/restore, monitoring and byte-level staging evidence.
- Consent-based face-detector false-negative evaluation stratified by image conditions and target operating markets.
- Automated route inventory tests proving every public media mutation path invokes the publication gate immediately before publication and rejects missing, stale, mismatched or revoked attestations.

## Reconciliation notes

- The Privacy Governance service, its publication evaluator, and the Vision face-masking implementation are present on main. Their existence does not prove that every publisher invokes them.
- The older privacy-publication hardening branch contains code already represented on main; its missing publication inventory documentation is being forward-ported here.
- Merged PR #265 forward-ported the BFF consent and photographed-person rights routes onto current main. These routes are a user-facing intake boundary, not proof that a real provider has quarantined or deleted every copy.
- PR #255 fixes a Look It consent-revocation defect: both request-scoped receipts must be revoked, and failure to revoke either suppresses the response.
- Click It remains disabled at the BFF. Do not enable it merely because the internal Vision worker can mask a test image.

**Release rule:** keep Click It unavailable and all unverified public image URLs withheld until exact-head CI, independent face-masking evaluation, live provider readiness, immutable asset-digest verification, end-to-end publisher call-site coverage and deployment evidence are complete.
