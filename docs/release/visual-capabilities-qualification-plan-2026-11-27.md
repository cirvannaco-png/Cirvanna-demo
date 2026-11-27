# Cirvanna visual-capability production qualification plan
**Date:** 2026-11-27  
**Scope:** Persistent Virtual Twin, Virtual Try-On, Click It, and Look It  
**Status:** Qualification plan only. No capability is certified by this document.

This plan separates implementation, operational readiness, model quality, privacy, and release approval. A green unit-test suite is necessary but insufficient. Each gate remains blocked until the required real-provider, independently reviewed evidence is attached to the exact release commit.

## Shared evidence rules

For every evaluation, retain:
- Exact source commit, container digest, dependency lock, model/revision and weight SHA-256 digests.
- Dataset licence, provenance, consent/purpose, retention terms, immutable manifest digest, and subject-disjoint split manifest.
- Frozen candidate/catalog snapshot and human-reviewed labels or qrels.
- Preregistered metrics, subgroup definitions, confidence intervals, failure/abstention counts and evaluation script digest.
- Raw result files, reviewer sign-off and a signed report digest bound to the release commit.
- Staging deployment IDs, runtime configuration evidence, trace IDs, and deletion/revocation verification.

Do not place private user images, secrets, raw consent tokens or biometric data in GitHub artifacts. Use synthetic fixtures for ordinary CI; real participant evaluation belongs in a controlled, consented evaluation environment.

## REL-17 — Persistent Virtual Twin

**Required proof**
1. A licensed, digest-pinned full-body reconstruction provider runs real inference; a pose skeleton, mock GLB or generated placeholder is not a Twin.
2. The generated mesh has anatomically complete, connected and correctly oriented body topology, plausible surface coverage, stable coordinate frame, valid scale and no malformed geometry.
3. Compare anthropometric measurements against reference scans and trained anthropometrist measurements. Report per-measurement MAE, median absolute percentage error, 95th-percentile error, bias, repeatability and subgroup confidence intervals. Any proposed 4% measurement-error target must be preregistered and demonstrated; it is not inferred from landmark confidence.
4. Evaluate surface/landmark error, pose and scale repeatability, capture rejection, occlusion and device/lighting sensitivity across body shapes, skin tones and launch-market subgroups.
5. Evaluate visual appearance/likeness separately from geometric and measurement validity. No face recognition or identity search is permitted.
6. Verify exact owner, Twin ID, consent bundle/version/expiry, source-image and GLB asset ownership, private object storage, authorization, revocation, deletion, restore and source-photo pixel non-leakage.
7. Twin Registry remains the single persistent metadata authority; every asset and provider output has a digest-bound provenance record and signed validation report.

**Release stop conditions:** gated/unlicensed model; mock or pose-only output; validator unable to attest; uncalibrated scale; missing subgroup evidence; any cross-owner access or source-photo leak; incomplete deletion.

## REL-24 — Virtual Try-On

**Initial scope:** person image + flat-lay garment image only. Model-worn garment photos remain disabled until a separately licensed parser and checkpoint are qualified.

**Required proof**
1. Exact FASHN VTON 1.5 source revision, model weight digests, DWPose artifacts, dependency SBOM and complete commercial licence/provenance review.
2. Real inference on the intended CUDA/GPU target; successful full pipeline load, worker readiness, bounded concurrency, latency/VRAM/cost, timeout, retry, overload and recovery evidence.
3. A consented, participant-disjoint, blinded human evaluation measuring garment identity and texture preservation, body/pose preservation, occlusion, seams/edges, anatomy artefacts, background changes, repeatability and failure/abstention.
4. Report results by garment category, body shape, skin tone, device, lighting, pose and occlusion, with confidence intervals and examples of both successes and failures.
5. Exercise the entire consent → Twin/Asset authorization → render → private output asset → short retention → revoke/delete path. Confirm no public CDN/cache/media publication and no persistence of unapproved source inputs.
6. Label results as visual previews only. No fit, size, body-measurement or purchase-fit claim without separately calibrated FCI evidence.

**Release stop conditions:** mock output; no GPU/model weights; model/weights provenance mismatch; uncleared parser dependency; failed deletion; unsupported garment mode; unqualified quality or latency.

## REL-25 — Click It

**Required proof**
1. Evaluate true image-to-catalog-image product/variant matching using immutable, rights-cleared catalog product images. Keep the current image-to-catalog-text FashionCLIP path as a separately labelled baseline; it is not exact visual matching.
2. Freeze query/candidate snapshots and human-reviewed qrels with product-family/source-cluster separation, duplicate and near-duplicate controls, hard negatives and no-match cases.
3. Report Recall@1/5/10, Precision@k, nDCG@k, MRR, exact-variant top-1 hit rate, no-match/abstention, false-positive cost and subgroup confidence intervals.
4. Calibrate scores on a separate split before interpreting them as probabilities. Report ranking quality independently from CAL display authorization and current merchant/landed-cost comparison.
5. Verify consent, photographed-person rights, guardian/child safeguards, jurisdiction policy, detector false-negative confidence intervals, mask-before-embedding ordering, no unmasked-media escape, private storage, retention, revocation, urgent quarantine, deletion, derivative/cache/CDN/merchant/shared-link purge and reporting.
6. A qualified independent assessor inspects the exact deployed route inventory and signs a report whose digest is bound to the release commit.

**Release stop conditions:** BFF remains 503; no real image-to-image benchmark; no image rights; detector uncertainty; any unmasked source exposure; missing deletion or independent assessment.

## REL-18 / REL-26 — Look It

**Required proof**
1. Keep Look It distinct from Click It in consent, route, retrieval task, datasets, qrels and release decision.
2. Use a rights-cleared outfit-reference dataset with independent human labels for each visible garment component. Keep subject/source clusters disjoint across train, calibration and test.
3. Score decomposition separately from component retrieval: component detection/category precision and recall, count/coverage, false-component rate, per-component Recall@k/Precision@k/nDCG, no-match/abstention and subgroup confidence intervals.
4. Include layering, partial occlusion, accessories, overlapping garments, varied body presentation, lighting, devices and launch-market categories.
5. Any external decomposition provider requires pinned model/revision/weights, commercial and image-processing rights, privacy/retention approval, DPA/subprocessor/region evidence and a verified deletion path.
6. Require resource-bound image_processing + look_it + declaration-specific consent; accept only no_people or adults_only in the initial scope; reject minors; mask detected faces before all downstream processing; fail closed when an adult is declared but no face is detected; revoke all receipts and prove no image persistence.
7. Candidate counts/components are not display authorization. Product, merchant, price and media details remain withheld until exact-variant CAL SHOW and current Commerce data succeed.

**Release stop conditions:** unconfigured decomposition provider; no independent component labels; no separate Look It benchmark; detector/consent/revocation failure; product details returned before CAL.

## Deployment and sign-off

The production release owner must verify the exact candidate commit in staging with dedicated credentials, production-like managed Postgres/private object storage, live model providers, real health/readiness probes, telemetry and rollback. Do not use production customer data for qualification. No release gate changes to `passed` without attached evidence artifacts and independent reviewer sign-off.
