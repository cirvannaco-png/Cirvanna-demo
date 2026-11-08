# Persistent Virtual Twin provider evaluation

**Evaluation date:** 8 November 2026  
**Decision status:** shortlist for controlled technical evaluation; no provider approved for production and no paid integration authorized.

## Executive decision

Run a self-hosted SAM 3D Body proof of concept first, and keep Bodygram as the commercial comparison track.

Do not make the production provider decision yet. A body mesh or avatar file is not proof of accurate measurements, stable identity representation, garment fit, or inclusive performance. The provider must pass Cirvanna's own consent, private-asset, mesh-validation, deletion, and representative-quality gates.

The most important architectural choice is to keep the generator behind the provider-neutral contract in services/virtual-twin/app/generation_contract.py. Provider-specific IDs, URLs, schemas and model versions must not leak into the Twin registry or BFF.

## Candidate comparison

| Candidate | What the public material confirms | Material limitations / risks | Recommendation |
|---|---|---|---|
| Meta SAM 3D Body, self-hosted | Single-image full-body 3D human mesh recovery using the Momentum Human Rig (MHR); estimates pose and shape and produces body vertices/parameters. Meta publishes checkpoints, inference code and evaluation data. | GPU/runtime and full dependency stack must be operated by Cirvanna. Checkpoint access is gated. The published headline metrics are benchmark-specific and do not establish Cirvanna fit accuracy or performance for target users. Need separate licence review for all dependencies and a representative body/garment evaluation. | **Lead technical PoC.** Best privacy architecture if source images stay inside Cirvanna-controlled infrastructure. Not a production approval. |
| Bodygram Platform | Commercial body scan API. Stats-only or two-photo (front + right-side) scan returns estimated body measurements and a 3D avatar; photo scan adds body composition/posture outputs. API returns a Base64 Wavefront OBJ avatar. Server-side permanent deletion endpoint exists. | PhotoScan schema requires age, gender (male/female), height, weight and two photos. Images may be retained up to 30 days; scan-derived measurements/avatar can remain for contract duration. Anonymized measurements/attributes may be used to improve its technology/business development. Contract, gender handling, data location, deletion semantics and output quality need diligence. | **Commercial comparison track.** Potentially stronger packaged measurement workflow, but the input and retention terms may conflict with Cirvanna's desired consent/data-minimization model. |
| fal-hosted SAM 3D Body | Hosted API accepts an image URL and returns a GLB body mesh, optional PLY meshes and structured keypoint/camera metadata. The model listing is marked for commercial use. | Request payloads are stored for 90 days by default; uploaded/generated media can be stored on fal CDN. ZDR is not enabled by default and requires sales confirmation for endpoint coverage. API returns provider-hosted file URLs. Need account-level ZDR, CDN expiry/ACL, processor terms, endpoint readiness, region, and deletion proof before any human photo. | **Evaluation accelerator only.** Do not send real user images until ZDR and endpoint-specific terms are confirmed in writing. Prefer self-hosting the model if feasible. |
| Avaturn | Paid API can create avatars programmatically and supports custom UX; its Pro price page currently lists $800/month for up to 1,000 avatars, with enterprise options including full-body scans and dedicated cloud. | API example requires front and side facial photos plus a binary male/female body-type field. The published standard plan is not evidence of the full-body body-shape/measurement quality required for Cirvanna's canonical fit Twin. | **Do not use as the canonical Twin provider.** It may be revisited for an optional expressive/stylized avatar only if its data collection is justified. |

## Evidence and interpretation

### 1. Meta SAM 3D Body — preferred technical experiment

Meta describes SAM 3D Body as single-image full-body human mesh recovery using MHR, with body, feet and hand pose estimation and a parametric mesh representation. Its public repository documents checkpoints and an inference path; access to the model checkpoints requires approval through Hugging Face. The public README reports benchmark metrics on named datasets, not Cirvanna-specific fit results.

The SAM licence grants a worldwide, non-exclusive, royalty-free limited licence to use, reproduce, distribute, copy, create derivative works of and modify the covered SAM materials, subject to its terms. It also requires legal/privacy compliance, imposes redistribution conditions, disclaims warranties including fitness for purpose, and puts output-use risk on the licensee. This is not a blanket clearance of every dependency. Inventory and review the exact versions and licences for detection, segmentation, field-of-view estimation, rendering and runtime dependencies before commercial deployment.

**POC implications:** host inference in an isolated GPU worker under Cirvanna control; keep raw source photographs in private storage; pass bytes from the trusted asset service rather than user-controlled URLs; pin the exact checkpoint and dependency revisions; store the actual generated GLB/mesh under a private opaque asset ID; compute SHA-256 after storage; and send the stored bytes to a separate validator.

**Do not claim:** calibrated circumferences, garment fit, or a persistent user Twin merely because SAM 3D Body returned an MHR mesh. Its output is a 3D body/pose estimate. A separate calibration/fit programme is necessary.

### 2. Bodygram — commercial comparison

Bodygram's Platform docs state that stats-only scans return measurements and a 3D avatar; adding front and right-side photos enables richer outputs. Its API documents an OBJ avatar encoded as Base64. The scan API key is server-side only and must not enter the browser or mobile binary.

Its Platform privacy policy distinguishes Bodygram acting as processor for client-directed API/feature use from separate controller activities. It states body images are automatically deleted within a maximum of 30 days, while body-scan data such as measurements and 3D avatars may be retained for the contract duration. It describes anonymized measurements and attributes being used for technology/business development. The API exposes a permanent scan deletion route, which deletes the scan and derived results.

**POC implications:** require a signed DPA and processing instructions, specify data residency/transfer and subprocessor disclosures, confirm whether model-improvement use can be contractually disabled or limited, confirm how promptly DELETE propagates to backups and derived data, and determine whether the API can satisfy Cirvanna's optional/non-binary identity design without forcing a user into a male/female classification. Test actual OBJ geometry and measurement error against controlled references.

### 3. fal-hosted SAM 3D Body — not privacy-ready by default

The hosted endpoint accepts image_url and returns a model_glb, optional individual PLY meshes, and keypoint/camera metadata. A binary upload path may upload media to fal's CDN; generated files are also returned as provider-hosted URLs.

fal's retention documentation states Model API payloads are stored for 90 days by default. It separately controls CDN media retention. ZDR covering prompts, inputs, outputs and content-bearing logs is supported only when confirmed with sales for the actual endpoint; it is not enabled by default. Disabling request-history storage alone does not disable CDN media or application logs.

**POC implications:** no real customer or employee photos may be sent until fal confirms ZDR coverage and endpoint eligibility in writing, account-level payload-storage defaults are disabled, CDN object lifecycle/ACL is configured, input/output deletion is demonstrated, and a DPA/subprocessor/region review is complete. Do not expose fal output URLs to Cirvanna clients; retrieve the file server-side, validate it, transfer it to private asset storage, and delete/expire provider copies.

### 4. Avaturn — wrong default for the canonical representation

The public API workflow requires a frontal face image and two side-face images, together with a binary body-type value. This requests more facial imagery than Cirvanna needs for a fit-oriented body representation. Its current Pro plan is listed at $800 per month for up to 1,000 avatars; enterprise has separate full-body scan and dedicated-cloud options. Its suitability for fit measurement has not been established.

## Required evaluation protocol

Use only consenting adults for the first evaluation. Participation must be opt-in, purpose-specific, revocable and separate from any public publishing permission. Do not use Click It or other people's photos as Twin training/evaluation inputs.

### Test set design

Build a consented, human-reviewed pilot set with variation across:

- Height, body proportions, body composition, age bands (18+), poses and occlusion.
- Skin tones, lighting conditions, camera quality and common smartphone capture conditions.
- Clothing types and fit/coverage variation, including modest clothing preferences; do not require revealing clothing.
- The target operating markets in Africa, Asia, the Middle East and India, represented through voluntary recruitment and self-described market context rather than inferred ethnicity.

Record capture failures, unsupported poses and low-confidence outputs. Do not silently remove failures from the denominator.

### Ground truth and scoring

Compare estimates against independently collected, consented reference measurements and human-reviewed mesh landmarks. Report results by the capture/body-condition strata above, not just one pooled average.

Minimum gates before any persistent registration or Try-On enablement:

1. The output is a decodable, structurally valid full-body mesh with the expected MHR/GLB/OBJ coordinate and scale conventions.
2. Independent validation confirms finite geometry, valid topology, adequate surface coverage, no embedded source-photo pixels, and no unapproved face/identity artifact.
3. Measurement error is quantified against reference measures. Fit-sensitive measures require pre-registered tolerances set with a qualified fit/garment specialist; do not invent a universal accuracy percentage.
4. Failure/abstention rates and error distributions are reported for each evaluation stratum. A high aggregate score cannot hide poor performance for a subgroup or capture condition.
5. Model/version provenance, artifact digest, source asset set, consent version, validator receipt and deletion evidence are retained in the audit trail.
6. Redo, correction, revocation and deletion flows are tested end-to-end, including retries, provider timeout, partial upload and provider-side deletion failure.

A 30–50 participant feasibility pilot can identify obvious failure modes; it is not a statistically sufficient basis for broad market claims. Determine the final evaluation sample size from the intended claims and the variance observed in the pilot.

## Questions to close before vendor approval

### Meta / self-hosted stack
- Confirm access to the exact checkpoint, its current licence, associated MHR assets and any gated terms.
- Produce a full software/model bill of materials with pinned revisions and licence evidence for every dependency.
- Benchmark GPU memory, throughput, cold start, queue capacity and per-user cost on the infrastructure Cirvanna can actually operate.
- Test whether the generated mesh is sufficiently stable under clothing, occlusion and camera variation for the intended Twin use.

### Bodygram
- Obtain the current API commercial price schedule, minimum commitments and volume tiers.
- Confirm whether the male/female photoScan requirement can be removed or replaced without degrading or invalidating the service.
- Contractually document image, measurement, avatar, derived-feature and backup retention; deletion SLAs; model-improvement use; regions; subprocessors; and incident notification.
- Validate that the avatar OBJ can be converted to the canonical private mesh/renderer format without losing scale, rigging or ownership metadata.

### fal
- Confirm endpoint-specific ZDR availability and written coverage for request payloads, uploaded input media, generated output, CDN, logs and support/debugging paths.
- Confirm whether the endpoint is Enterprise-ready for the required ZDR setup and whether data can be processed in an acceptable region.
- Demonstrate ACL, expiry, deletion and no-public-URL behavior from a real test account before any human images are used.

## Architecture decision

Keep the current provider-neutral generation command/result/validation contract. Build a small self-hosted SAM 3D Body worker spike first, but do not connect it to the persistent registry until the independent validator and current consent/private-asset integrations are live. Keep Bodygram as the alternative if its contractual and input-design gaps can be closed. Keep fal behind a hard privacy hold until ZDR is contractually enabled and proven.

The current capability response must remain:

- persistent_twin_generation = false
- persistent_twin_preview = false
- full_surface_mesh = false
- try_on_available = false

until production evidence justifies changing them.

## Primary sources

- [Meta SAM 3D Body repository and README](https://github.com/facebookresearch/sam-3d-body)
- [Meta SAM 3D Body installation and gated checkpoint instructions](https://github.com/facebookresearch/sam-3d-body/blob/main/INSTALL.md)
- [Meta SAM License](https://github.com/facebookresearch/sam-3d-body/blob/main/LICENSE)
- [Meta announcement of SAM 3D Body and MHR](https://ai.meta.com/blog/sam-3d/)
- [Bodygram Platform introduction](https://docs.bodygram.com/platform)
- [Bodygram endpoint reference](https://docs.bodygram.com/platform/endpoints)
- [Bodygram Platform privacy policy](https://www.bodygram.com/en/policies/bodygram-platform-privacy-policy)
- [fal SAM 3D Body API](https://fal.ai/models/fal-ai/sam-3/3d-body/api)
- [fal Data Retention and Storage](https://fal.ai/docs/documentation/model-apis/media-expiration)
- [Avaturn programmatic avatar API](https://docs.avaturn.me/docs/integration/api/create-avatar-with-api/)
- [Avaturn developer pricing](https://avaturn.dev/pricing/)
