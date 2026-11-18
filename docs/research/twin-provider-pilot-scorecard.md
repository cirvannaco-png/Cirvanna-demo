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

## 8. Public provider diligence — checked 18 November 2026

This section records what the providers publicly document. It is a screening record, not legal review, vendor assurance, a signed contract, a pilot, or approval. Public web pages can change. Before procurement, archive the exact proposal, DPA, security pack, subprocessor list, model/API version, technical documentation and signed terms.

### A. 3DLOOK FitXpress — geometry / measurement candidate

**Documented technical fit**
- The public API creates scans from front and side photos and profile fields. Its documented request contract makes gender required with male or female values, height required from 145–220 cm, age optional from 16–85, and weight optional from 40–200 kg.
- The public response example exposes a model_3d_url ending in .obj. That is not the GLB 2.0 binary expected by Cirvanna's current private Twin mesh upload route. Any conversion must be tested and validated independently; a format conversion is not evidence of rigging, calibrated scale or garment-fit quality.
- The product page describes 80+ measurements, body-composition estimates and a 3D model from two smartphone photos. FitXpress is therefore a potentially useful geometry/measurement workstream, not a complete persistent avatar experience.

**Published data-lifecycle and assurance statements**
- The FitXpress FAQ (updated 29 October 2026) says photos are deleted immediately or within 30 days depending on customer-specific settings; retained photos are automatically blurred. It says measurements and 3D model outputs are kept on an ongoing basis unless the customer agreement or a deletion request changes that.
- The same FAQ describes AWS hosting primarily in US-West-2 and partly US-East-1; deletion requests use scan identifiers. It states production customer data is not used for model training unless the customer explicitly authorizes it, while aggregated/anonymized data may be used for permitted analytics and service improvement.
- The FAQ says 3DLOOK is working toward a SOC 2 attestation report and has completed an initial readiness assessment. Treat this as a published vendor statement, not a completed independent SOC 2 report.

**Cirvanna decision**
- **REVIEW_REQUIRED — do not send media.** Obtain the actual enterprise agreement and DPA, confirm exact data region and subprocessors, make immediate source-photo deletion contractual and technically test it, define deletion of measurements/3D meshes/logs/backups, and confirm the right to retain, transform, redistribute and render customer outputs.
- Validate whether its two-photo workflow, demographic input constraints and documented OBJ output are acceptable for Cirvanna's supported user population and markets. Establish accuracy against an independent reference dataset and pre-registered subgroup thresholds. The public FAQ's face-obfuscation statement must be verified in the exact SDK/API path selected; do not assume it covers Cirvanna's own capture or stored copies.

### B. Bodygram Platform — combined measurement / avatar candidate

**Documented technical fit**
- The public platform says each scan returns measurements and a 3D avatar. Stats-only scans accept height, weight, age and gender; the photo path accepts front and right-side photos and also returns body-composition and posture outputs.
- The endpoint reference specifies male or female gender values for both scan modes. Its avatar response is documented as base64-encoded Wavefront OBJ (format: obj), not GLB. Cirvanna would need a controlled conversion and independent runtime/geometry validation before considering it for the current GLB persistence contract.
- Bodygram's deletion endpoint is server-side and irreversible. Its current endpoint documentation says it deletes the scan and its derived measurements, body composition, posture, avatar, custom scan ID and original scan input. The endpoint returns 404 for an already deleted scan, so Cirvanna must design its deletion worker around the provider's actual retry semantics rather than treating a repeated delete as a successful replay.

**Published data-lifecycle statements**
- The Bodygram Platform Privacy Policy, last updated 28 April 2026, says scan images are automatically deleted within a maximum of 30 days; body-scan information such as height, weight, age, gender, estimated measurements and 3D avatars may be retained for the duration of the contract.
- The policy describes storage on licensed servers located globally. It also says anonymized data such as body statistics and estimated measurements may be used to enhance technology and business development. This is a material issue for Cirvanna's no-training-by-default position: anonymization and model-development use must be specifically defined and contractually constrained, including treatment of derived data and aggregated datasets.
- The endpoint documentation requires the organization API key to remain server-side and describes scan tokens for client-side scanner flows. A client must never receive the organization API key.

**Cirvanna decision**
- **REVIEW_REQUIRED — do not send media.** Request a signed DPA, exact regional/subprocessor schedule, explicit no-training/no-model-improvement terms covering raw and derived data unless a separate optional consent is obtained, deletion and backup evidence, age policy, output ownership/redistribution rights, and security evidence.
- Confirm that deletion of all vendor-side records and derivatives is independently observable. Test a scan, read the authorized outputs, delete it, verify every retrieval path returns deleted/not-found, and obtain the contractual backup-erasure SLA. The public deletion endpoint is promising, but it does not itself prove backup or downstream copy deletion.

### C. Avatar SDK / MetaPerson — appearance/avatar candidate

**Documented technical fit**
- The public Cloud API documentation describes generation from a single photo and export of rigged GLB, glTF or FBX models, including textures, haircuts, outfits and blendshapes. The documented pipeline supports appearance and renderable-avatar use cases.
- That is not evidence of calibrated body measurements, anatomically accurate body-surface coverage, known physical scale or garment-fit accuracy. Treat MetaPerson as an appearance/avatar candidate only unless separate validated measurement evidence is produced.
- The API documentation recommends Client access mode for production. That mode scopes access to a PlayerUID and restricts list/delete operations to that user's avatars; it is a useful isolation control, not a substitute for Cirvanna-side authorization, consent binding or deletion reconciliation.
- Public materials are inconsistent about commercial access: the Cloud API docs describe Pro access for companies below stated revenue/funding thresholds and Enterprise for others, while the newer Avatar API product page describes Enterprise access. Obtain a written quote and exact SKU, API entitlement, volume limits and rights; do not infer that the founder's current company stage guarantees eligibility.

**Published privacy position**
- The public privacy policy says customer data is retained according to customer instructions, customer agreements and law. That policy alone does not settle exact processing regions, derived-output retention, model-training exclusions, subprocessors, backup deletion or redistribution rights for this integration.
- The provider's current API pages describe cloud processing and also market a Local Compute option. Do not assume Local Compute is part of a cloud API contract; evaluate and license it separately if deployment within Cirvanna-controlled infrastructure is required.

**Cirvanna decision**
- **REVIEW_REQUIRED — do not send media.** Obtain a current DPA and security pack; verify regions, subprocessors and retention; confirm whether source photos, thumbnails, generated meshes, textures and logs are retained; secure explicit no-training terms; confirm output commercial/redistribution rights and whether textures, hair/outfit assets carry separate restrictions.
- Pilot only on consented, governed test media after all commercial/privacy gates pass. Evaluate skin-tone preservation, hair representation, face/head likeness, body proportions, rig/blendshape quality, mobile rendering cost, reproducibility and deletion. A successful avatar demo must not be presented as measured fit.

### D. Meta SAM 3D Body — self-hosted research baseline

- The official repository describes SAM 3D Body as single-image full-body human mesh recovery using the Momentum Human Rig (MHR) representation. It is suitable as an internal research baseline for pose/shape reconstruction experiments, not as an already calibrated measurement system or a production Twin lifecycle.
- Its code and checkpoints are governed by Meta's SAM License, not a default MIT/Apache assumption. The official installation guide says checkpoint access requires requesting access to the Hugging Face repositories. License review, model-weight access, dependency/security review, infrastructure cost, model version pinning and applicable use restrictions remain prerequisites.
- Self-hosting may avoid sending user media to an inference vendor, but it does not remove Cirvanna's obligations for lawful capture, consent, storage, access, deletion, model-output privacy, bias evaluation or licensing.
- **REVIEW_REQUIRED — research only.** No production deployment, redistribution or real-user capture until legal review and the full independent geometry/scale/privacy evaluation passes.

### E. Cross-provider technical conclusion

No candidate is publicly evidenced as a complete, production-ready answer to all of Cirvanna's requirements. The most plausible architecture to test is still a **separated pipeline**: geometry/measurement candidate (FitXpress or Bodygram) and, only if needed, a distinct appearance/avatar candidate (MetaPerson), with SAM 3D Body as a self-hosted research comparator. This increases integration complexity and multiplies consent, data-transfer, deletion, subprocessor and provenance obligations. It must not be selected merely because two vendor outputs can be combined into one screen.

A future candidate evaluation must test, at minimum:
1. Whether an individual can participate without being forced into an unsupported demographic input or excluded height/age range; collect only fields demonstrably necessary.
2. Whether the same source media can be processed under an explicit, versioned, resource-bound consent and a no-training-by-default contract.
3. Whether generated artifacts can be normalized to a documented, pinned GLB profile without losing scale, topology, skeletal rig, blendshapes, texture fidelity or provenance.
4. Whether geometry, physical scale and named measurements pass against independent reference scans/measurements, with confidence intervals and subgroup reporting.
5. Whether appearance, skin tone, hair and face/head fidelity pass a separate blinded review.
6. Whether source media, generated meshes, derived measurements, thumbnails, caches, vendor records and backup copies are deleted and deletion is evidenced.
7. Whether user revocation, account deletion, provider deletion failure, timeout, retry, partial failure and disaster recovery all converge to a safe, auditable state.

## 9. Cirvanna implementation audit — release gates that remain open

The repository contains meaningful foundations, but the following are not yet production evidence:

| Area | Verified implementation boundary | Unclosed release gate |
|---|---|---|
| Twin generation | Provider-neutral generation contract and registration payload checks exist | No commercially approved generator is connected; no real generation workflow has been proven end-to-end |
| Mesh validation | Separate service reads the private GLB, rechecks consent and digest, and inspects bounded structural geometry | It returns registry_eligible=false and issues no signed validation receipt. Body coverage, calibrated scale, source-photo non-embedding and independent sensitive-data scan remain unverified |
| Registry | Owner-bound immutable Twin records, authorization rechecks and deletion outbox exist | Real production deployment, migration/restore evidence, operational outbox monitoring and a validated generation-to-preview lifecycle remain unproven |
| Asset storage | Private object access, owner/purpose/parent binding, bucket public-access checks, encryption and read digest checks are implemented | No production bucket configuration evidence is attached. Readiness does not currently prove versioning is disabled or historical object versions/delete markers are purged. A delete request is not proof of irreversible deletion |
| Orphan cleanup | Upload code attempts to remove an object when metadata persistence fails | Cleanup is best-effort. An operational orphan-object reconciliation/alert process and test evidence are required |
| Deletion / backup | Registry deletion outbox calls an owner/parent-scoped Asset Service deletion path | Test real object deletion, versioning semantics, provider-side deletion, CDN/cache invalidation, lifecycle expiry, backup retention and a full restore. A successful HTTP response alone is insufficient |
| BFF / onboarding | Authenticated metadata-only saved-Twin discovery and no-store responses are implemented | No mesh readback, preview renderer, production session/device capture flow or complete account-deletion workflow is live |
| Privacy | Capability and consent checks fail closed in the current guarded path | No end-to-end independent proof yet that no unmasked Click It photo can leave any Cirvanna publishing route; no completed deletion/retention audit or child-safety evidence |
| Marketplace | Black/gold/white styling, mobile layouts and interaction tests are implemented | CI proves demo UI contracts, not live multi-market provider data, inventory, payment settlement, shipping/tax/FX or production CAL authorization under live operations |
| Deployment | CI exercises tests and builds container images | No live staging/production parity, managed DB/object-store provisioning, secret injection, restore drill, monitoring, alerting, runbooks or device QA evidence is attached to this PR |

**Hard-delete requirement:** before production Twin data is accepted, either prove that the selected object store has versioning disabled and no prior versions exist, or implement version-aware deletion that removes every version and delete marker. Record object-lock/retention settings, backup copies and recovery-point retention separately. The current Asset Service readiness check validates public-access block, public policy, encryption and ownership controls, but does not establish these versioning/backup conditions.

**Orphan-object requirement:** implement or operate a reconciliation process that finds private objects without active metadata rows and safely removes them after a conservative grace period, with an audit trail and alerting. Never infer orphan status from a transient metadata/database outage.

**Deletion reliability requirement:** monitor pending deletion outbox age, retry counts and last error; alert and escalate repeated failure; demonstrate that consent revocation removes the Twin from all read surfaces immediately while physical deletion completes asynchronously; publish truthful deletion status and completion evidence. A restore test must prove the deletion policy does not accidentally resurrect erased data.

## 10. Final provider and release decision

**Provider selection: NONE. Real-user Twin capture and persistent generation: DISABLED. Registry attestation from the current mesh validator: NOT ISSUED. Virtual Try-On: DISABLED.**

This is the correct current decision, not a failure of the project. It prevents a UI prototype or structural mesh check from being represented as a trustworthy personal Twin. Re-open the selection only after signed vendor terms, independent technical results, privacy/security sign-off and operating evidence are attached to a specific model release.

### Primary public sources checked 18 November 2026

- [3DLOOK FitXpress API reference](https://docs.fitxpress.3dlook.me/) — capture contract, profile fields and model output.
- [3DLOOK FitXpress Data Privacy & Security FAQ](https://3dlook.ai/content-hub/fitxpress-data-privacy-security-regulatory-faq/) — updated 29 October 2026; published retention, location, deletion, training and assurance statements.
- [Bodygram Platform introduction](https://docs.bodygram.com/platform) and [REST endpoints](https://docs.bodygram.com/platform/endpoints) — scan inputs/outputs, server-only credentials and deletion endpoint.
- [Bodygram Platform Privacy Policy](https://www.bodygram.com/en/policies/bodygram-platform-privacy-policy) — updated 28 April 2026; public retention and global hosting disclosures.
- [Avatar SDK Cloud API](https://api.avatarsdk.com/) and [MetaPerson REST API docs](https://docs.metaperson.avatarsdk.com/rest_api/) — single-photo avatar generation, GLB exports and access model.
- [Avatar SDK privacy policy](https://avatarsdk.com/privacy-policy/) — public baseline only; current contract and technical controls still required.
- [Meta SAM 3D Body repository](https://github.com/facebookresearch/sam-3d-body), [installation/checkpoint access](https://github.com/facebookresearch/sam-3d-body/blob/main/INSTALL.md) and [SAM License](https://github.com/facebookresearch/sam-3d-body/blob/main/LICENSE) — model scope, checkpoint access and licensing.
