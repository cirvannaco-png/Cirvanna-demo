# Persistent Twin provider pilot scorecard

**Status:** evaluation template only — no provider selected, approved, or connected  
**Applies to:** body-geometry providers, appearance/avatar providers, and self-hosted research baselines  
**Owner:** Cirvanna product, engineering, privacy and legal reviewers

This scorecard prevents a visually convincing demo from being mistaken for a safe, measurable, production-ready Twin. Complete one copy per provider and model release. Attach primary evidence; vendor claims alone are not acceptance evidence.

## 1. Candidate identity and reproducibility

| Field | Required evidence | Result |
|---|---|---|
| Provider and legal entity | Contracting entity, support contact, subprocessors | REVIEW_REQUIRED |
| Product / API plan | Exact SKU, API version and enabled features | REVIEW_REQUIRED |
| Model identifier | Canonical model ID | REVIEW_REQUIRED |
| Model revision | Immutable source commit or vendor release identifier | REVIEW_REQUIRED |
| Model release digest | SHA-256 of complete weights/runtime release where available | REVIEW_REQUIRED |
| Pre/post-processing | Pinned code, libraries, container and configuration | REVIEW_REQUIRED |
| Output format | Actual GLB/glTF version, units, skeleton/rig and coordinate convention | REVIEW_REQUIRED |
| Change control | Vendor notice, compatibility and requalification process | REVIEW_REQUIRED |

## 2. Non-negotiable commercial and privacy gates

A failure or missing primary evidence in this section blocks all real-user media processing.

| Gate | Evidence to obtain | Decision |
|---|---|---|
| Commercial rights | Written rights for production, redistribution, derivative assets and user-facing rendering | REVIEW_REQUIRED |
| Data processing | Signed DPA, controller/processor roles, subprocessors and breach terms | REVIEW_REQUIRED |
| Training restriction | Contractual prohibition on training with Cirvanna media unless separate, optional, explicit consent exists | REVIEW_REQUIRED |
| Processing location | Exact regions, transfer mechanism and regional failover behavior | REVIEW_REQUIRED |
| Source retention | Configured immediate deletion after processing; documented exceptions | REVIEW_REQUIRED |
| Derived-output deletion | API/contract path and completion evidence for meshes, textures, thumbnails and caches | REVIEW_REQUIRED |
| Security | Encryption, access controls, tenant isolation, audit logs and incident response | REVIEW_REQUIRED |
| Subprocessor chain | Complete list, locations, purposes and change notification | REVIEW_REQUIRED |
| Age policy | Minimum age, guardian workflow where applicable, and child-data restrictions | REVIEW_REQUIRED |
| Exit / portability | Export, termination, deletion certificate and transition assistance | REVIEW_REQUIRED |

Do not send source photos, videos or body measurements to a candidate until every applicable gate has a documented approval.

## 3. Technical capability — score separately

Do not combine these dimensions into one “avatar quality” score.

### A. Body geometry and measurement

| Metric | Protocol / reference | Result |
|---|---|---|
| Capture completion rate | Pre-registered capture protocol, stratified by device and cohort | NOT_MEASURED |
| Surface coverage | Independent reference scan; per-region coverage and error | NOT_MEASURED |
| Measurement accuracy | Named landmarks and trained reference measurements; report bias and error distribution | NOT_MEASURED |
| Repeatability | Repeated capture under controlled conditions | NOT_MEASURED |
| Scale accuracy | Calibrated reference, not glTF unit declarations | NOT_MEASURED |
| Pose / occlusion robustness | Pre-registered clothing, pose, lighting and occlusion slices | NOT_MEASURED |
| Topology | Independent checks for invalid indices, degeneracy, non-manifold edges and declared watertightness criteria | NOT_MEASURED |
| Failure behavior | Explicit rejection codes; no fabricated or silently substituted body mesh | NOT_MEASURED |

### B. Appearance and renderable avatar

| Metric | Protocol / reference | Result |
|---|---|---|
| Face/head fidelity | Consented human review against source under a documented rubric | NOT_MEASURED |
| Skin-tone preservation | Color-managed capture and subgroup evaluation | NOT_MEASURED |
| Hair representation | Coverage across relevant hair types, styles and occlusion | NOT_MEASURED |
| Rig / animation | Independent skeletal, blendshape and deformation QA | NOT_MEASURED |
| Garment interaction | Intersections, clipping and pose stability; not a fit guarantee | NOT_MEASURED |
| Runtime compatibility | Web/mobile renderer, memory, load time and device matrix | NOT_MEASURED |
| Output portability | Private GLB/glTF export with documented textures, extensions and rights | NOT_MEASURED |

### C. Privacy and artifact integrity

| Metric | Protocol / reference | Result |
|---|---|---|
| Source-photo non-embedding | Compare output bytes and decoded resources against exact authorized source set | NOT_MEASURED |
| Sensitive-data scan | Independent scan with labelled corpus and false-negative analysis | NOT_MEASURED |
| Private asset provenance | Asset Service owner, purpose, Twin parent and digest re-verification | NOT_MEASURED |
| Consent binding | Subject, Twin, consent ID, exact version and required scopes | NOT_MEASURED |
| Deletion propagation | Exercise provider, Asset Service, Registry, cache and backup lifecycle | NOT_MEASURED |
| Reproducibility | Same pinned release/configuration; record expected nondeterminism | NOT_MEASURED |

## 4. Evaluation cohort and analysis plan

Before recruitment or capture, approve the protocol, lawful basis, consent language, retention schedule, reference measurement method and safety review. Collect the minimum media required.

Pre-register cohort slices relevant to Cirvanna's launch markets and supported product population, including:

- Skin tone and lighting conditions where appearance rendering is evaluated.
- Height, body shape and relevant body-region variation for geometry.
- Hair type/style, garment occlusion, pose and mobility variation.
- Android device class, camera capability and OS version.
- Age only within the product's approved age policy; do not include children by default.

Report sample counts, confidence intervals, missingness, rejection rates and subgroup performance. Do not hide poor slices behind a global average. Human reviewers should be blinded to provider identity where feasible.

## 5. Decision rules

- PASS: primary evidence exists, the pre-registered threshold is met, and the named reviewer signs off.
- FAIL: evidence shows a threshold is not met or a prohibited behavior occurs.
- REVIEW_REQUIRED: evidence is missing, ambiguous, vendor-only or not independently reproducible.
- NOT_APPLICABLE: only with a written rationale and reviewer approval.

No weighted average can override a failed commercial/privacy gate. A candidate may pass the geometry layer and fail the appearance layer, or vice versa. Keep those decisions separate.

Thresholds must be agreed before the pilot begins. Do not invent acceptance thresholds after seeing results.

## 6. Required sign-offs

| Review | Reviewer | Evidence / decision |
|---|---|---|
| Product fit and user value | Named reviewer | PENDING |
| Geometry / measurement | Independent technical reviewer | PENDING |
| Appearance / rendering | Design and technical reviewer | PENDING |
| Privacy / security | Privacy and security reviewer | PENDING |
| Commercial rights / DPA | Legal / procurement reviewer | PENDING |
| Operations / deletion / restore | Platform owner | PENDING |

## 7. Current decision

**No provider is approved.** The existing shortlist (3DLOOK FitXpress, Bodygram, Avatar SDK MetaPerson and SAM 3D Body) remains a diligence shortlist only. Body geometry and recognizable appearance must be evaluated independently; combining separate providers creates additional data-transfer, consent, deletion and provenance obligations.

The independent mesh service currently performs structural preflight only. It does not establish body coverage, calibrated scale, source-photo non-embedding or complete privacy clearance, and it issues no Registry attestation. Keep capture, persistent generation, registration, preview and Virtual Try-On disabled until all required gates are independently evidenced.
