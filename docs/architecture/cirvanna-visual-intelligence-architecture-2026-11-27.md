# Cirvanna Visual Intelligence (CVI)

**Date:** 27 November 2026  
**Status:** programme architecture and release-control foundation; no visual model is newly production-qualified by this document.

## Strategic decision

Cirvanna will own the visual product architecture, data governance, task-specific training/evaluation, orchestration, release qualification and customer-facing quality contracts. Third-party models may be used as temporary research baselines or replaceable components. A third-party model is never an implicit production approval.

"Build our own" means building Cirvanna-specific models and systems on rights-cleared data, with reproducible training and independently qualified releases. It does not require reimplementing general-purpose vision foundations from random initialization. Training a foundation vision model from scratch is a separate capital decision requiring a large, legally usable corpus and substantial compute; it is not a prerequisite for proprietary product differentiation.

## System boundaries

- **Visual Intelligence Core:** canonical image decoding, safety/capture-quality gates, private asset references, task routing, model registry, inference quotas, provenance, observability and release policy.
- **Twin Geometry:** full-body surface reconstruction, topology, coordinate conventions, anatomical plausibility and calibrated anthropometry. Geometry and measurement are separate claims.
- **Twin Appearance:** identity-consistent appearance, texture/material reconstruction and persistent render representation. Appearance quality does not establish anatomical or measurement accuracy.
- **Virtual Try-On:** person/garment parsing, garment representation, pose/occlusion reasoning, deformation, synthesis and output validation. A generated image is not proof of fit.
- **Click It:** image-region extraction, fashion-specific embeddings, candidate retrieval and calibrated ranking against approved catalogue snapshots.
- **Look It:** outfit component detection/decomposition, category/attribute extraction, region provenance and per-component catalogue matching.

## Data and trust model

1. Source images remain private and purpose-bound. Dataset creation requires a documented rights basis, consent where applicable, allowed purposes, retention policy and exact content digest.
2. Training, validation and test splits are leakage-aware by subject and capture session. Subject images must not leak across splits. Test sets are held out from model selection.
3. Dataset manifests and model releases are immutable and digest-pinned. No raw user imagery, credentials or private catalogue exports enter Git.
4. Model inference runs behind authenticated private service boundaries with bounded payload size, timeouts, concurrency, memory/VRAM, retries and ephemeral input storage.
5. Every result records model ID/revision, weights digest, runtime image digest, preprocessing revision, dataset lineage, request contract and output digest.
6. Consent is rechecked before processing and before persistence/display. Revocation blocks new access immediately and propagates deletion to source, derived assets, caches, registries and backups according to the approved retention policy.
7. Independent validation inspects actual stored output bytes. Provider self-attestation is not a validation receipt.

## Initial Cirvanna-owned model candidates

The first implementation candidates are intentionally trained from random initialization; PyTorch/TorchVision are architecture/runtime libraries, not sources of pretrained weights:
- **Look It:** Faster R-CNN ResNet-50 FPN detector for outfit-component bounding boxes. Pixel-mask segmentation and attribute recognition remain future work.
- **Click It:** ResNet-50 image encoder plus Cirvanna projection head, trained with supervised contrastive learning over canonical product variants. The approved catalogue image-to-image benchmark remains the release quality gate.
- **Virtual Try-On:** custom U-Net garment warp-and-refine network predicting sampling flow, blend alpha and image residual, with garment-region and warped-mask losses. Initial training resolution is 256x256.
- **Virtual Twin:** registered-scan PCA shape basis, tape-measure ridge calibration and calibrated multi-view landmark/silhouette fitting, with mesh-only GLB export.

These are training and geometry foundations, not trained production models. The current workspace has no approved image/scan corpora, no PyTorch/TorchVision runtime or NVIDIA GPU. Synthetic tests validate contracts and algorithms only. No model quality or production readiness is claimed.

## Release qualification

The package at packages/cirvanna_visual_intelligence defines the initial fail-closed model/dataset/evaluation evidence contract, including pinned inference resource budgets. A model is not qualified unless the exact capability scope, source revision, weights digest, runtime digest, bounded resource profile, commercial rights evidence, dataset provenance, evaluation report, independent review, privacy review and resource/deletion evidence bind together.

The first Look It component-localization evaluator now computes category-aware bounding-box IoU matching, per-category precision/recall/F1, exact component-count accuracy and subgroup metrics. It requires a dedicated look_it_decomposition_evaluation rights scope and writes private, digest-bound reports. It is intentionally not a pixel-segmentation benchmark and has not been run on an approved catalogue/outfit corpus.\n\nThis contract validates evidence shape and cross-binding only. It intentionally cannot return qualified: even a complete metadata set remains evidence_complete_pending_trusted_attestation. Production adoption requires a trusted cryptographic signature verifier, immutable evidence storage, role-separated approver identities, and deployment-policy integration.

## Capability-specific evidence

### Twin Geometry and Appearance
- Reference 3D scans or suitable ground truth, with acquisition protocol and uncertainty.
- Per-region surface distance, coverage, topology, scale and anatomical plausibility.
- Named anthropometric landmarks and measurement definitions; mean/median absolute error, percentile error, repeatability and subgroup confidence intervals.
- Appearance likeness, skin/hair/material fidelity and temporal consistency reported separately.
- Human-reviewed failure analysis; no sizing/fit use until calibrated measurement gates pass.

### Virtual Try-On
- Pinned model/code/weights and full transitive license/SBOM review.
- Real GPU load/inference, deterministic input/output validation and resource saturation tests.
- Garment identity/pattern/logo/colour preservation, body/face identity preservation, occlusion plausibility and artifact rate.
- Human review stratified by body shape, skin tone, garment type, pose, occlusion and capture conditions.
- Deletion and retry/replay drills; no source or result payloads in logs.

### Click It
- Approved catalogue image corpus with rights manifest and immutable snapshot.
- Image-to-image Recall@K, mAP/nDCG, top-1 precision, duplicate/near-duplicate handling, calibration and abstention quality.
- Leakage-aware product/style/brand splits; hard negatives and visually similar variants.
- Independent end-to-end consent, masking, publication-attestation, revocation and deletion review.

### Look It
- Independently annotated outfit regions and component labels.
- Detection/segmentation IoU, per-class precision/recall, component count accuracy and attribute F1. The initial offline evaluator is tools/model_evaluation/look_it_decomposition/evaluate.py; it currently scores normalized bounding-box localization only, not pixel masks.
- Per-component retrieval Recall@K/mAP and end-to-end outfit-to-product success.
- Stratification by overlap, occlusion, pose, image quality, garment category and population coverage.
- Abstain on ambiguous or incomplete decomposition; retrieval-only results are not successful Look It.

## Programme sequence

1. Establish shared governance, immutable manifests, model registry, benchmark protocols and GPU execution limits.
2. Build and evaluate Look It decomposition and Click It image retrieval on separately approved catalogue data.
3. Develop Twin geometry and measurement calibration against an independently acquired reference cohort; develop appearance as a separate track.
4. Build Try-On on the stable body/garment representation and qualify actual GPU rendering.
5. Integrate production consent/asset/registry/deletion controls and conduct independent red-team/privacy review.
6. Enable capabilities individually only after the exact model, data, runtime and evidence digests are approved.

## Explicit non-goals

- No facial recognition, identity search or cross-user image matching.
- No use of unlicensed or unconsented images for training.
- No claim that pose landmarks are a Twin or measurements.
- No claim that generated imagery proves physical fit.
- No automatic activation based on a mock test, provider demo, model-card license alone or self-reported quality.
- No paid GPU or external provider provisioning without explicit budget approval.

