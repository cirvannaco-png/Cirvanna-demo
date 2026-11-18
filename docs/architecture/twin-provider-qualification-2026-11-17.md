# Cirvanna Persistent Twin — Provider Qualification Assessment

**Reviewed:** 17 November 2026  
**Status:** candidate assessment only; no provider approved or enabled  
**Decision owner:** Cirvanna product/security/engineering review

## Executive decision

Do not wire a production generator yet. Cirvanna needs two distinct capabilities that current products often conflate:

1. **Body geometry and measurement evidence:** a usable 3D body representation, repeatable measurements, documented capture quality and accuracy limits.
2. **Recognizable appearance and presentation:** face/head identity, skin/hair appearance, a rigged renderable avatar and an asset format usable in the web/mobile Twin scene.

A body-shape estimate is not a face-accurate personal avatar. A visually convincing avatar is not calibrated body measurement or fit evidence. A pose skeleton is neither.

The best next technical evaluation is a controlled comparison of 3DLOOK FitXpress and Bodygram for the body-geometry/measurement layer, with Avatar SDK MetaPerson as a candidate appearance/avatar layer. SAM 3D Body is a promising self-hosted research baseline for mesh recovery, not a production approval. This is a shortlist for diligence and a human-reviewed pilot, not a vendor selection.

## Candidate comparison

| Candidate | Relevant capability | Evidence from public materials | Main gaps for Cirvanna | Assessment |
|---|---|---|---|---|
| 3DLOOK FitXpress | Two-photo body scan, 80+ measurements, body-composition estimates and 3D body model; API/SDK | Vendor says front/side mobile capture, scan-quality validation, and 3D model plus measurements. Its Oct 29 2026 FAQ describes immediate photo deletion or retention up to 30 days by customer policy; measurements/models are retained ongoing unless the customer agreement or deletion request says otherwise. Hosting is primarily AWS us-west-2 and partly us-east-1. Customer ownership of deliverables is described in its terms. | Face is obfuscated; this is not the recognizable face/Twin layer. Vendor accuracy claims are vendor-reported and need independent validation. Contract must specify immediate source-photo deletion, output deletion, region, subprocessor list, permitted data use and API deletion SLA. | **First body-scan pilot candidate**, subject to contract and evaluation gates. |
| Bodygram Platform | Two-photo body measurement and OBJ avatar; optional body-composition and posture outputs | Docs specify front and right-side images with age, gender, height and weight; output includes measurements and base64 OBJ avatar. Bodygram's privacy policy says photos may be deleted immediately or retained up to 30 days depending on customer instructions; other outputs are governed by the client contract. | Required demographic inputs and gender field need product/legal review. Vendor stores outputs during contract unless otherwise agreed/deleted. Must verify face handling, output rights, region, retention and deletion API behavior for the intended plan. | **Alternative measurement/body-model pilot**, compare directly with 3DLOOK. |
| Avatar SDK / MetaPerson | Recognizable, rigged full-body avatar from a front-facing photo; GLB/glTF or FBX export | Vendor says the API produces rigged, animatable full-body avatars and supports cloud Enterprise or on-prem deployment. API docs describe body/head meshes, textures, blendshapes and fixed-topology avatar bodies; REST access for MetaPerson 2.0 is Enterprise. | Does not claim calibrated anthropometric measurement or fit accuracy. Need DPA, source-image retention/deletion, training-use restrictions, output rights, region/subprocessors, pricing and model/version pins. | **Appearance/avatar-layer candidate**, not the only source of body-fit geometry. |
| Meta SAM 3D Body | Single-image full-body human mesh recovery with MHR pose/shape representation and optional keypoint/mask prompts | Official repository describes single-image full-body mesh recovery. Checkpoints are gated on Hugging Face. The published SAM License grants broad use/reproduction/modification rights but requires acceptance and continued compliance; dependency/model licences still need separate review. | It is a mesh-recovery model, not a complete textured, identity-preserving avatar service. No production API, provider support or end-user lifecycle is supplied. Need pinned weights, GPU/runtime dependency review, subgroup evaluation, privacy validation and independent mesh validation. | **Self-hosted research baseline** for geometry comparison only. |

## Privacy and commercial gates

### 3DLOOK FitXpress

The public FAQ states that photos are deleted immediately after processing or within 30 days depending on customer policy, and that measurements/models persist unless otherwise specified by contract or deletion request. It describes AWS hosting primarily in us-west-2 and partly in us-east-1, and says production data is not used for model training without explicit documented authorization. The FAQ expressly says it does not replace the signed customer agreement/DPA.

Before a pilot, require a signed DPA and order form that select immediate source-photo deletion, identify data regions and subprocessors, define output ownership/use rights, prohibit model-training use absent separate explicit authorization, and specify a verifiable output deletion and incident process.

### Bodygram

The public policy describes processing of front/side photos and user-provided profile data, generation of body measurements and 3D body models, and photo deletion immediately or within 30 days according to the business client's instructions. It describes Bodygram acting as processor where the customer determines purposes and means. Contract review must establish the exact retention and deletion settings, data location, subprocessors and whether a scan output can be removed promptly from vendor systems.

### Avatar SDK

Its public site describes Enterprise Cloud API and on-prem options. Before any user image is sent, obtain written terms covering source-photo retention/deletion, DPA, data location, subprocessors, model training, export/output rights, concurrency, service levels and pinned pipeline/model revisions. A visually accurate avatar must not be treated as a calibrated body measurement.

### SAM 3D Body

The checkpoint repository is gated. The SAM License (last updated 19 November 2025) grants rights to use, reproduce, distribute, modify and create derivative works, with requirements and exclusions in the license; use still requires acceptance and legal review. The install guide lists a substantial PyTorch/Detectron2/MoGe/SAM and vision dependency set. Audit each dependency, model checkpoint and detector separately; the top-level model license is not a complete stack licence review.

## Recommended architecture for evaluation

- Keep **Twin Registry** as the one owner-bound metadata authority.
- Keep **Asset Service** as the one private binary authority for source images, canonical Twin representation and derived previews.
- Use a provider adapter for body geometry and, only if selected, a separate avatar/appearance adapter. Keep both behind the current trusted orchestration boundary.
- Normalize the canonical representation to a private GLB 2.0 artifact. Asset Service now has a bounded GLB upload route that checks container structure and blocks external buffer/image URIs; this is not body geometry validation.
- Require the generator to write its result to Asset Service and return only an opaque asset ID, pinned model ID, source commit revision, model-release digest and artifact digest.
- Require an independent validator to fetch and inspect the stored bytes itself, then issue a signed validation receipt bound to owner, Twin, consent version, exact source set, model revision, artifact ID and digest.
- Register only after re-checking resource-bound consent, asset ownership and validation attestation. Never allow a provider-supplied `validated=true` flag to create a Twin.
- Store only validated Twin asset references and provenance in Twin Registry. On consent withdrawal/deletion, immediately block authorization and dispatch all source/derived assets through the deletion outbox.

## Pilot acceptance protocol

Run a consented, human-reviewed evaluation before provider selection. Use a diverse cohort spanning the actual Cirvanna launch markets, skin tones, heights, body shapes, ages permitted by the product's age policy, hair/garment occlusion, poses and capture devices. Collect no more media than the approved protocol requires.

Measure at least:

1. Capture success and rejection reasons by cohort/device.
2. 3D surface reconstruction error against a suitable reference scan; report per-body-region error, not one aggregate score.
3. Measurement error against trained human measurements or an appropriate reference instrument, with named landmark/measurement definitions and repeatability.
4. Mesh topology, body-surface completeness, non-finite geometry, scale plausibility and source-photo pixel leakage.
5. Visual likeness/skin-tone preservation and identity fidelity separately from body-shape accuracy.
6. Clothing-overlay intersections and garment-placement stability, without calling either a fit guarantee.
7. Deletion completion across provider source media, private asset store, registry and logs; exercise failures and retries.
8. Performance, GPU cost, queue latency, throughput, regional availability and outage behavior.

Pre-register thresholds and subgroup slices before testing. Missing subgroup evidence, vendor-only accuracy claims or unverified deletion behavior remain `REVIEW_REQUIRED`; they are not a pass.

## Release gates remain closed

- No commercial provider or self-hosted model is approved by this assessment.
- No source photo/video capture is enabled by the onboarding UI.
- No pose skeleton, vendor avatar, or unvalidated mesh may replace the Blue Flame.
- No asset is used for Marketplace display, Try-On, CAL/FCI, sizing or fit claims until the relevant downstream service has independent validation.
- Production requires provider contracts, identity/consent integration, private storage readiness, registry readiness, restore/deletion drills and physical-device QA.

## Sources reviewed

- 3DLOOK FitXpress data/privacy/security FAQ (updated 29 Oct 2026): https://3dlook.ai/content-hub/fitxpress-data-privacy-security-regulatory-faq/
- 3DLOOK FitXpress Privacy Policy (22 Jun 2026): https://3dlook.ai/fitxpress-privacy-policy/
- 3DLOOK customer terms: https://3dlook.ai/fitxpress-customer-terms-conditions/
- 3DLOOK FitXpress API/SDK overview: https://3dlook.ai/
- Bodygram Platform docs: https://docs.bodygram.com/platform
- Bodygram scan endpoints and output schema: https://docs.bodygram.com/platform/endpoints
- Bodygram Platform Privacy Policy: https://www.bodygram.com/en/policies/bodygram-platform-privacy-policy
- Avatar SDK Avatar API: https://avatarsdk.com/avatar-api/
- Avatar SDK WEB API docs: https://api.avatarsdk.com/
- SAM 3D Body repository: https://github.com/facebookresearch/sam-3d-body
- SAM 3D Body checkpoint model card: https://huggingface.co/facebook/sam-3d-body-dinov3
- SAM License: https://github.com/facebookresearch/sam-3d-body/blob/main/LICENSE
- SAM 3D Body install guide: https://github.com/facebookresearch/sam-3d-body/blob/main/INSTALL.md


## Independent mesh-validator foundation — 18 November 2026

A separate \`services/twin-mesh-validator\` service now reads private, owner/purpose/Twin-bound GLB bytes and performs a bounded structural geometry preflight after verifying current, version-bound consent. It validates the actual digest, GLB 2.0 container, triangle indices, finite positions, degeneracy and non-manifold edges. It rejects explicit glTF images/textures, custom extension/extra payloads, external/data URIs and common embedded image signatures.

This is intentionally not full body validation. The service issues no Registry receipt or HMAC and does not claim anatomical coverage, calibrated scale, exact source-photo non-embedding or full privacy validation. Those remain independently evidenced release gates. The Virtual Twin orchestration helper no longer accepts the shared HMAC secret; it can only attach a validator-issued signature that the Registry independently verifies.
