# DermalSight Intelligence: evidence-led improvement roadmap

**Date:** 15 November 2026  
**Status:** Research synthesis and engineering decision proposal  
**Scope:** DermalSight (DSI) skin/colour intelligence, capture calibration, body-region assessment and the hand-off to Virtual Twin. This document does not approve a model, change runtime readiness, or authorize clinical claims.

## 1. Executive decision

DSI should become a **calibrated, uncertainty-aware skin and appearance measurement system**, not a broad “AI skin scanner” that assigns attractive but unsupported scores.

The strongest defensible sequence is:

1. Make capture quality, colour calibration and repeatability trustworthy.
2. Replace coarse face/body skin coverage with validated anatomical-region segmentation.
3. Add non-diagnostic cosmetic skin attributes as separate, task-specific models.
4. Keep objective skin colour measurement distinct from subjective personal-colour/styling advice.
5. Keep full-body reconstruction and the canonical body representation with Virtual Twin; DSI supplies only validated, purpose-authorized measurements.
6. Add multispectral or other sensors only when a defined use case demonstrates material benefit over calibrated RGB.

**Do not expand the feature list before the measurement pipeline is defensible.** A larger model trained on inconsistent phone images will not solve the central problem.

## 2. Evidence that materially changes the design

### 2.1 Skin colour requires a measurement protocol, not just a camera model

CIE 256:2025, *Measurement of Human Skin Colour*, is the primary standard reference for this work. It emphasizes measurement uncertainty, instruments, illumination geometry, body location and population variability. The companion CIE Human Skin Colour Database contains more than 10,000 sets of spectral measurements across nine measurement sets and multiple body locations, instruments and population descriptors. DSI should map its protocol and evaluation schema to this standard; the database is a research/reference source, not automatically a licensed training corpus.

A camera photograph is not intrinsically a colourimeter. Camera model, illumination spectrum, white balance, exposure, image processing and compression all affect the RGB values. A 2024 review of skin-tone assessment notes that reference charts and cross-polarization can improve reproducibility and reduce specular reflection, while warning that retrospectively captured uncontrolled images are not equivalent to standardized captures. A 2026 clinical study of two full-face imaging systems reported that in-frame ColorChecker calibration with a polynomial regression approach improved colour accuracy and stability, while also finding differences between devices.

**Implication for DSI:** retain the current experimental ColorChecker path, but do not promote it on the basis of a successful chart fit. The release target is agreement with independently measured skin references on held-out people, cameras, lighting and anatomical regions.

### 2.2 Skin-tone categories and dermatology datasets are not sufficient ground truth

Fitzpatrick Skin Phototype was developed to characterize UV response, not as a universal skin-colour coordinate system. It is too coarse to describe within-category pigmentation, undertone or site-to-site variation. Use objective colour measurements for colour work and retain Fitzpatrick only as an optional, separately collected clinical-context descriptor when genuinely needed; do not infer race, ethnicity or ancestry from appearance.

A 2025 audit of Fitzpatrick17k and related dermatology datasets identified duplicate images and benchmark leakage. In Fitzpatrick17k, 1,425 highly similar pairs were manually reviewed and 1,402 were confirmed duplicates. The audited training and test partitions became substantially smaller after cleaning. DSI must not treat an open dataset as clean ground truth simply because it is widely cited.

A 2025 systematic review/meta-analysis of skin-lesion AI reported pooled AUROC around 0.88 across included studies, but pooled specificity was only 0.64 and performance was lower in darker phototypes (AUROC 0.82 for IV–VI versus 0.89 for I–III). These are diagnostic-system results, not DSI cosmetic-model benchmarks. Their relevance is the warning: overall averages can hide material subgroup and deployment-setting failures.

**Implication for DSI:** dataset provenance, deduplication, subject-disjoint splitting, out-of-time evaluation and subgroup reporting are release requirements, not optional research hygiene.

### 2.3 Smartphone body scanning is promising but metric-specific

A systematic review of smartphone/tablet 3D anthropometry screened 2,172 records and retained 13 studies. It found promising reliability and validity for selected outcomes, but accuracy and evidence strength varied by measurement; the review explicitly cautions against treating all anthropometric outputs as equally established. It found no included 4D studies. The published ICC, R² and RMSE figures must be read at the outcome level, not advertised as universal body-scan accuracy.

**Implication for DSI:** do not infer body circumference, body composition, posture or fit from a generic full-body selfie. Validate each measurement separately against an appropriate reference. Virtual Twin owns the body representation; DSI may provide a versioned measurement-evidence contract only after validation.

### 2.4 Personal colour analysis is a different problem from skin colour measurement

CIELAB/CIELCh can describe measured appearance under a stated illuminant/observer and capture protocol. They do not, by themselves, prove that a person belongs to a single “season”, that a warm/cool label is objectively correct, or that a palette is aesthetically best.

Treat personal colour analysis as a **consumer styling hypothesis** layered over measured colour, user preferences and optional virtual draping—not as diagnosis or a beauty rule. Allow multiple plausible palettes, show what evidence is driving each suggestion, ask for user feedback, and make user direction authoritative. A user must be able to explore colours outside the suggested profile without penalty.

## 3. Target capability architecture

Keep the existing service boundaries. No new DSI service, user-profile store, raw-media store or global intelligence registry is justified by this research.

| Capability | Canonical owner | Required DSI role |
|---|---|---|
| Capture planning and skin/colour analysis | `services/dermalsight` | Purpose-authorized orchestration, measurement contracts, provenance and uncertainty |
| Model inference and image segmentation | `services/vision-intelligence` | Private, pinned model execution; no public identity/recognition surface |
| Consent and subject binding | Identity Learning | Verify exact purpose, subject, resource, expiry and revocation before media access |
| Shared evidence/rights governance | Cirvanna Intelligence Layer | Source-rights and evidence provenance; no duplicate registry |
| Body mesh and persistent body representation | Virtual Twin | Owns reconstruction and body assets; consumes only validated DSI measurements |
| Fit prediction | FCI | Owns garment-fit predictions; must not treat DSI colour or geometry as fit evidence |
| Product display authorization | CaTaCaCi / CAL | Sole SHOW/BLOCK/REVIEW authority; DSI never authorizes products or purchases |
| Style preference persistence | USI/TAL | DSI never silently writes inferred attributes into durable preferences |

### 3.1 Keep three separate output layers

1. **Measured appearance:** calibrated CIELAB/CIELCh values with named region, illuminant/observer, camera/profile, chart/instrument references, timestamp, quality state and uncertainty.
2. **Model-inferred cosmetic attributes:** separate task outputs such as visible pigmentation distribution, texture/roughness proxy, pore appearance or visible redness. Every task has its own model evidence and validation scope.
3. **Styling interpretation:** optional warm/cool/neutral hypotheses, palette families, cosmetics/shade suggestions and draping comparisons. This is advisory and user-correctable, not a measured medical or biological truth.

Never collapse these layers into one opaque “skin score”.

## 4. Capture and colour-calibration specification

### P0 — controlled capture

The capture flow should record only metadata necessary to determine comparability and quality:

- Camera/device model, OS/capture pipeline version, image dimensions, file format and available colour profile.
- Capture distance/pose guidance, selected anatomical region, lighting protocol and whether exposure/white balance were locked.
- Whether the chart is present, chart profile/version, production edition and chart-condition result.
- Quality measurements: clipping, blur, glare/specular reflection, shadow, uneven illumination, occlusion and segmentation coverage.

Disable or detect beauty filters, portrait relighting, night mode, HDR/tone mapping and other computational changes where possible. When they cannot be disabled or reliably detected, downgrade to relative-only or review-required. Do not silently convert an uncontrolled image into an absolute measurement.

Use a repeatable diffuse light source and fixed capture geometry for the calibrated path. Cross-polarized capture is a valuable second mode for reducing surface glare, but it needs its own camera/light calibration and validation. It should not be assumed interchangeable with diffuse-light images.

### P0 — calibrated colour

- Use CIE 256:2025 as the protocol reference and record the exact illuminant, observer, reference profile, camera pipeline and body site.
- Preserve the current explicit chart requirement for absolute colour. Lock exposure and white balance; retain RAW where the device and workflow support it. A processed JPEG may be usable only for a device/profile combination that has been specifically validated.
- Maintain explicit transforms and provenance: encoded RGB → linearized camera values → camera/profile correction → XYZ under the declared conditions → CIELAB/CIELCh. Do not mix D50 and D65 references or silently change white-point adaptation.
- Continue CIEDE2000 diagnostics, but report calibration-target fit error separately from skin-reference error. A good fit to chart patches is not proof of accurate skin measurement.
- Where feasible, compare camera outputs with independently calibrated spectrophotometer readings from the same anatomical region and capture session. Record instrument model, calibration certificate, geometry and instrument uncertainty.
- Store per-region lightness, chromatic axes and derived chroma/hue only when the model and capture gate pass. Do not turn an ITA/Fitzpatrick label into the canonical colour truth.
- If the chart is absent, damaged, clipped, poorly detected or outside the validated device/light profile, return relative-only or REVIEW_REQUIRED. Never invent an absolute value.

**Important limitation:** a colour chart cannot fully correct every sensor/illuminant spectral mismatch. Device-specific and lighting-specific validation is still required; the calibration algorithm cannot be assumed to generalize to any phone.

### P0 — colour measurement acceptance

The existing offline evaluator is the right foundation. Keep its signed dataset manifest, signed release policy, independent spectrophotometer references, pseudonymous subject clustering and fail-closed result states.

For every release, report at least:
- CIEDE2000 median, mean, p95 and maximum by region and subgroup;
- L*, a* and b* signed/absolute bias;
- repeat-capture variation separated from reference-instrument uncertainty;
- failure/review rate and chart-fit error;
- results by camera, OS, lighting, chart condition, geometry, body region and measured colour range;
- subject-clustered confidence intervals and subgroup sample counts.

Thresholds must be fixed by independent reviewers before final holdout evaluation. This document intentionally does not invent a universal ΔE00 cutoff or a minimum sample count. Any underpowered slice, missing ground truth, unsigned evidence or changed model digest remains REVIEW_REQUIRED. A PASS is scoped only to the exact model, segmenter, camera/profile scope, chart profile, dataset, policy and capture protocol.

## 5. Body calibration and anatomical-region intelligence

### 5.1 DSI must distinguish region detection from body reconstruction

The current face/body masks are coarse. They are not independent masks for neck, chest, arms, hands, thighs or lower legs. The next model increment should provide anatomical-region segmentation and an explicit uncertain/occluded state. Do not estimate a region from a neighbouring region when the target is covered or outside the frame.

Recommended segmentation outputs:
- face, neck, upper chest, left/right upper arm, left/right forearm, left/right hand, left/right thigh and left/right lower leg;
- clothing, hair, background and non-skin classes;
- occluded, out-of-frame and uncertain labels with calibrated coverage/confidence semantics.

These labels are a proposal for the next model contract, not a claim that the current segmenter supports them. Evaluate mask quality per region and measured skin-colour range; report Dice/IoU and boundary quality, not just overall pixel accuracy.

### 5.2 Regional tone alignment

Measure each selected region independently. Do not assume face, neck, chest, hands and legs should have identical pigmentation. Compare regions only when the user selects that comparison and the captures meet a common calibration protocol. Expose:
- measured value and uncertainty for each region;
- capture comparability status;
- observed difference between selected regions;
- an explanation when comparison is not valid.

The platform should support the user's purpose: matching foundation to face/neck, choosing body makeup, or exploring colour differences. A natural region difference is not a flaw and must not be automatically “corrected”.

### 5.3 Body measurement belongs with Virtual Twin

When body calibration is requested for sizing, fit or avatar reconstruction, use the Virtual Twin ownership boundary. Prefer multi-view photogrammetry or supported depth/ToF sensing over a single RGB frame. Control pose, distance, camera height, scale, garment fit, hair obstruction and view coverage.

Validate every requested metric separately:
- circumferences and lengths against trained anthropometrists using a documented tape-measure protocol;
- 3D surface/shape repeatability against a calibrated scanner or reference mesh;
- body composition only against an appropriate validated reference method, and do not infer it from surface geometry alone.

Report absolute error, mean bias, 95% limits of agreement, repeatability/ICC and technical error of measurement for each metric. ICC alone is insufficient: high rank-order reliability does not guarantee small absolute error. Keep DSI output as a signed, versioned measurement observation; Virtual Twin owns persistent mesh/assets and FCI owns garment-fit prediction.

## 6. Skin analysis: task-specific, cosmetic and non-diagnostic

Define separate targets and ground truth for every attribute before selecting or training a model.

| Candidate attribute | Possible evidence | Guardrail |
|---|---|---|
| Visible pigmentation distribution | Calibrated image, region mask, dermatologist/cosmetic-expert annotation where appropriate | Describe visible distribution; do not infer cause or diagnose melasma/other disease |
| Visible redness/erythema appearance | Controlled visible/cross-polarized images; instrument comparison if making quantitative claims | Colour appearance is not a diagnosis of inflammation or vascular disease |
| Texture/roughness proxy | Controlled macro/close-up image and repeatable segmentation | Do not claim hydration, collagen, elasticity or microscopic structure from RGB alone |
| Pore appearance | Standardized close-up capture and expert/annotator agreement | Surface appearance only; avoid permanent or stigmatizing ratings |
| Blemish/acne-like visible count | Clearly defined annotation protocol and stratified evaluation | Do not label acne severity or prescribe treatment without clinical validation/regulatory review |
| Cosmetic product response | User-entered product and reaction history, consented longitudinal data | Self-report is not proof of causality or diagnosis |

Do not market inferred hydration, sebum, collagen, skin barrier function, UV damage depth or disease risk unless the relevant physical sensor/model and reference study support that specific claim. RGB appearance alone is not a substitute for corneometry, sebumetry, spectroscopy, dermoscopy or clinical examination.

Use task-specific model cards, annotation manuals, model hashes, data rights, calibration and subgroup evidence. A single signed report for the existing `cosmetic_skin_attributes` ONNX task does not validate skin tone, body segmentation, facial geometry or other tasks.

## 7. Personal colour analysis

Build this after colour capture is stable; it is a styling capability, not a clinical measurement.

1. Generate measured colour features only from an approved calibrated capture, otherwise label inputs as approximate.
2. Offer candidate palette directions using value/lightness, chroma, hue relationships and user-selected aesthetic goals. Avoid one definitive seasonal label.
3. Provide a digital draping experience with controlled garment swatches and stable rendering conditions. Mark simulated colour as a rendering, not a real-world fabric guarantee.
4. Let the user choose, correct, reject or explore outside recommendations. User choice must override inferred colour profile and historic preferences.
5. Learn only from explicit, consented approvals/edits/rejections through the canonical USI/TAL workflow; a single rejected palette is not a permanent exclusion.
6. Evaluate recommendations through blinded pairwise reviews by trained colour consultants plus user preference studies. Report inter-rater agreement and preference outcomes; do not present subjective agreement as an objective colour-science accuracy score.

Separate shade matching (product colour vs measured skin/reference region) from palette styling (which clothing colours the user likes or finds harmonious). They are different ranking problems and need different datasets and metrics.

## 8. Multimodal roadmap: add complexity only when proven useful

| Modality | Recommendation | Rationale / gate |
|---|---|---|
| Calibrated RGB + physical reference | Build first | Low-cost, accessible baseline; requires device/light validation |
| Cross-polarized visible light | Evaluate next | Reduces specular glare; separate calibration and user/device validation required |
| Depth/ToF or multi-view photogrammetry | Use for Twin/body geometry | Better suited to geometric reconstruction than skin chemistry |
| Narrow-band multispectral | Research/pilot only | Add only for a defined pigment/vascular feature where it materially improves ground-truth performance |
| UV/Wood's lamp | Do not add to consumer capture by default | Safety, device, clinical and intended-use questions require specialist review |
| Thermal imaging | Defer | Temperature patterns are not direct diagnoses and consumer-camera thermal capability is uncommon |
| Hyperspectral/Raman/fluorescence | Research partnership only | Potentially informative but expensive, difficult to standardize and not justified for the first consumer release |

Do not let “more sensors” become a substitute for a validated task. A single additional modality should enter the roadmap only with a preregistered hypothesis, reference measurement, cost/UX assessment and demonstrable performance gain.

## 9. Data, evaluation and fairness

### Dataset design

Build a purpose-specific dataset; do not combine clinical lesions, cosmetic selfies, colour-calibration captures and body scans as interchangeable examples.

For each record, preserve only what is needed:
- pseudonymous subject key for clustered analysis;
- exact consent/rights provenance and allowed purpose;
- capture protocol, device/OS, lighting and chart/instrument metadata;
- selected body region and occlusion/quality status;
- exact model/segmenter/profile versions and hashes;
- independently measured reference and reference uncertainty;
- annotation provenance and adjudication state.

Keep raw media in controlled storage outside Git and ordinary application containers. DSI image-processing paths should remain ephemeral by default. Global model training requires its own explicit opt-in and a separately approved data/rights pipeline; analysis consent is not training consent.

### Evaluation protocol

- Split by person, not by image. Keep repeat captures and near-duplicates inside one partition.
- Use subject-disjoint and out-of-time test partitions; hold out complete camera models and lighting setups where possible.
- Deduplicate exact and perceptual near-duplicates before any split. Audit label quality and data leakage.
- Predeclare all primary tasks, metrics, thresholds, required slices and subgroup sample-size rules before accessing final test results.
- Report confidence intervals, failures and abstentions, not just the best aggregate score.
- Include African skin-tone diversity and relevant local device/lighting conditions in the actual validation cohort. Do not treat geography or ancestry as a proxy for measured skin colour.
- Report performance by objectively measured colour ranges, region, device, light source, capture quality and relevant demographic strata that are ethically and legally collected.
- Use independent clinical/measurement reviewers for ground truth and independent sign-off for release policy.
- Re-run evaluation whenever model weights, preprocessing, camera scope, sensor, chart profile or post-processing changes.

### Core KPIs

| Domain | KPI set |
|---|---|
| Capture | accepted/review/rejected rates; false-accept/false-reject by device and skin-colour range; missing-chart and glare rates |
| Colour | ΔE00 distribution vs spectrophotometer; Lab-axis bias; repeatability; instrument uncertainty; device/light generalization |
| Segmentation | per-region Dice/IoU, boundary score, coverage and abstention rate |
| Body measurement | per-metric MAE/RMSE, bias, 95% limits of agreement, ICC and technical error of measurement |
| Cosmetic attributes | per-task precision/recall or agreement against the declared reference, subgroup calibration and confidence-stratified error |
| Personal colour | blinded pairwise preference, consultant inter-rater agreement, user edits/acceptance and palette diversity |
| Privacy/autonomy | 100% purpose-consent verification before processing; no raw-media persistence by default; no unapproved training; no DSI veto of user aesthetic choices |

Do not set arbitrary universal numerical pass thresholds in code. The independent evaluation policy must define thresholds for a particular intended use and reference method.

## 10. Build-versus-buy and partnerships

**Buy or license:** physical ColorChecker/reference targets, calibrated spectrophotometer access, controlled illumination components, and mature depth-camera SDKs where they reduce engineering risk. Obtain licenses and exact artifact/model cards for any third-party face/skin model.

**Build and own:** DSI capture-quality policy, camera/profile registry, region-specific measurement schema, consent/provenance orchestration, held-out evaluation process, uncertainty reporting and user-facing explanation. These are core to the trust proposition and cannot be outsourced as a black box.

**Partner:** dermatology/cosmetic-science researchers, accredited measurement laboratories, anthropometrists, local clinics and universities for diverse capture cohorts and independent reference measurements. Use a clinical advisor for cosmetic-vs-clinical boundary review. Do not collect images from the public without reviewed consent, rights, retention and safeguarding procedures.

**Dataset cautions:**
- CIE Human Skin Colour Database is a valuable spectral reference; inspect access terms and permitted use before redistribution or model training.
- Fitzpatrick17k is a dermatology-condition image resource, not a calibrated cosmetic colour/texture dataset. Use only after license, label, duplicate and partition audits.
- ISIC/dermoscopy resources are relevant to lesion research, not generic personal colour analysis or full-body skin-tone calibration.

## 11. Regulatory and safety boundary

The current Cirvanna service description defines DermalSight as non-diagnostic cosmetic skin-attribute inference. Preserve that intended purpose unless there is a deliberate, separately funded medical-device program.

The Kenya Pharmacy and Poisons Board published a *Guideline on Regulation of Medical Device Software in Kenya (MDSW)* on 16 April 2026. It covers software risk classification, cybersecurity/data protection, AI/ML, documentation/approval and lifecycle oversight. Before making clinical claims, screening claims or treatment recommendations in Kenya, perform a documented intended-purpose and classification assessment with qualified regulatory counsel and the PPB. Other markets require their own pathway review.

Safety invariants remain:
- no diagnosis, disease-risk score, lesion cancer screen or treatment instruction in the cosmetic DSI flow;
- no face recognition, identity search, age estimation or sensitive-trait inference;
- no raw-image retention or global training by default;
- no unauthorized processing after consent revocation;
- no silent user-profile writes, body correction or public image output;
- unavailable, uncertain or unvalidated capabilities remain unavailable or REVIEW_REQUIRED;
- optional DSI failure or refusal must never block style exploration, discovery or user-selected looks.

## 12. Prioritized delivery roadmap

### 0–3 months: establish trustworthy measurement

- Freeze intended-purpose statements and task definitions for cosmetic analysis, colour measurement and body-region observations.
- Review the current ColorChecker preview implementation against CIE 256:2025; document transform, illuminant, observer, ICC/RAW handling, chart-profile provenance and known device limits.
- Define the supported capture-device/light matrix and the guided capture protocol.
- Acquire spectrophotometer reference access and pilot a repeated-measures capture dataset spanning measured skin-colour ranges, anatomical sites, local phone models and realistic lighting.
- Audit any candidate data for license, consent, duplicates, subject overlap and label quality.
- Keep readiness blocked; do not change user-facing capability state during this research increment.

### 3–6 months: region and calibration proof

- Build the anatomical-region segmentation candidate in the Vision Intelligence owner path.
- Add capture and region quality tests, including occlusion, motion, glare, hair/clothing contamination and low-coverage abstention.
- Run the signed offline colour evaluator on a real, independent held-out cohort.
- Compare calibrated RGB and cross-polarized capture on the same subjects to establish whether the added capture burden is justified.
- Define and validate the first two or three cosmetic attribute tasks; defer unmeasurable skin-health claims.

### 6–12 months: validated consumer utility

- Promote only the exact colour/segmentation model releases that pass independently signed evaluation.
- Implement per-region tone comparisons with provenance and uncertainty; keep all unsupported regions unavailable.
- Pilot advisory personal-colour palettes and controlled digital draping as a separate styling layer.
- Conduct a Virtual Twin body-measurement pilot against anthropometrist/reference scans; publish per-measurement errors and supported device scope.
- Complete security, privacy, retention/deletion and consumer-claims review before enabling wider image processing.

### 12–24 months: selective multimodal expansion

- Add multispectral or other sensing only when it measurably improves a defined task and the cost/UX is justified.
- Consider regulated clinical features only as a separate intended-purpose and regulatory program with clinician-led studies.
- Expand supported cameras/markets through exact-scope validation, not assumptions that a model generalizes to every device.
- Establish post-release drift monitoring, incident handling, dataset withdrawal/retraining and model rollback.

## 13. Immediate engineering backlog

| Priority | Work item | Owner | Acceptance evidence |
|---|---|---|---|
| P0 | Audit ColorChecker transform and capture metadata against CIE 256:2025 | DermalSight + Vision | Written transform/protocol review, device limitations and regression tests |
| P0 | Define and acquire consented spectrophotometer reference cohort | Research/data governance | Signed rights/consent manifest and independent ground-truth protocol |
| P0 | Run real signed colour evaluator; keep synthetic tests labelled synthetic | Vision validation | Complete report; PASS/FAIL/REVIEW_REQUIRED bound to exact hashes |
| P1 | Design anatomical-region segmentation v2 | Vision Intelligence | Label guide, annotation agreement, per-region validation design and fail-closed contract |
| P1 | Define cosmetic attribute task cards | DermalSight | Construct, reference, intended use, claims boundary and model-specific acceptance plan |
| P1 | Define Virtual Twin anthropometry contract boundary | Virtual Twin + DermalSight | Per-metric reference method, measurement uncertainty and signed evidence schema |
| P2 | Prototype advisory palette/draping evaluation | Complementer + DermalSight | Blinded preference protocol, explicit user override and no hard aesthetic gate |
| P3 | Assess cross-polarized/multispectral add-on | Research | Pre-registered hypothesis, cost/UX comparison and independent benefit evidence |

**Do not implement new inference endpoints or change readiness states merely to represent these backlog items.** First obtain the datasets, annotation guide, reference instruments and independent acceptance policy. The existing DSI contract/evaluator architecture is already a suitable base for this research-to-validation path.

## 14. References

1. CIE, [CIE 256:2025 — Measurement of Human Skin Colour](https://www.cie.co.at/publications/measurement-human-skin-colour-0), DOI: 10.25039/TR.256.2025.
2. CIE, [Human Skin Colour Database (version 2025)](https://www.cie.co.at/publications/measuring-skin-colour/dataset1-humanskincolourdatabase), DOI: 10.25039/TR.256.2025.DS1.
3. [A survey of skin tone assessment in prospective research](https://www.nature.com/articles/s41746-024-01176-8), npj Digital Medicine (2024).
4. [Enhancing the reliability of skin tone evaluation: A study of full-face imaging devices with colour calibration](https://doi.org/10.1111/ics.70090), International Journal of Cosmetic Science (2026).
5. [Better understanding of digital photography for skin color measurement: With a special emphasis on light characteristics](https://doi.org/10.1111/j.1600-0846.2010.00468.x), Skin Research and Technology (2011).
6. [Consistent Cutaneous Imaging With Commercial Digital Cameras](https://jamanetwork.com/journals/jamadermatology/fullarticle/402500), JAMA Dermatology (2005).
7. Scataglini et al., [Smartphone and tablet-based 3D scanner for anthropometric assessments in adults: a systematic review of reliability, validity, and accuracy](https://doi.org/10.1186/s12938-025-01480-8), BioMedical Engineering OnLine (published 5 December 2025; version of record 12 January 2026).
8. Tjiu & Lu, [Equity and Generalizability of Artificial Intelligence for Skin-Lesion Diagnosis Using Clinical, Dermoscopic, and Smartphone Images: A Systematic Review and Meta-Analysis](https://doi.org/10.3390/medicina61122186), Medicina (10 December 2025). Diagnostic evidence only; not a DSI cosmetic benchmark.
9. [Investigating the Quality of DermaMNIST and Fitzpatrick17k Dermatological Image Datasets](https://www.nature.com/articles/s41597-025-04382-5), Scientific Data (2025).
10. Kenya Pharmacy and Poisons Board, [Guideline on Regulation of Medical Device Software in Kenya (MDSW)](https://web.pharmacyboardkenya.org/download/guideline-on-regulation-of-medical-device-software-in-kenya-mdsw/), published 16 April 2026.

---
**Decision summary:** prioritize calibration, independent reference data and region-specific validation. Add richer sensing and more impressive scores only after the measurement evidence justifies them. DSI should help users understand and explore their appearance; it must never define what they are allowed to look like.
