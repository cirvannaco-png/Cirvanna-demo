# DSI P0 capture protocol and provenance

**Status:** P0 implementation foundation; contract-only. No route consumes this schema yet, and it does not enable image processing or absolute colour measurement.

## Why this increment exists

The current Vision Intelligence decoder normalizes embedded ICC images to sRGB but assumes sRGB when no profile exists, clears image metadata after decoding, and applies generic brightness/contrast/sharpness/clipping gates. Those checks are useful input guards, but they do not prove controlled illumination, locked exposure/white balance, valid chart condition, cross-polarizer geometry or camera colour accuracy.

The current ColorChecker path fits an affine RGB-to-XYZ transform and computes leave-one-patch-out chart diagnostics. This measures how well the chart patches fit that transform; it is not independent validation of skin colour. A chart fit can look good while skin-region estimates remain inaccurate because of sensor spectral response, illumination mismatch, camera processing, glare, chart wear or skin-region segmentation error.

This P0 increment introduces a strict, non-identifying provenance contract before any capture route starts accepting additional metadata. It explicitly treats all client/device fields as declarations, never as proof.

## Capture modes

| Mode | Intended use | Measurement state |
|---|---|---|
| Controlled diffuse | Baseline colour protocol with documented, stable diffuse illumination | Candidate for controlled evaluation only |
| Cross-polarized | Optional research capture with a polarizer on the illumination path and an analyzer on the camera path | Separate optical protocol; must be calibrated and evaluated independently |
| Ambient relative | User-facing exploration under uncontrolled ambient conditions | Relative-only/review; never absolute colour |

Cross-polarization can reduce specular reflections, but it changes the optical capture path and must not be mixed with diffuse captures as though they were interchangeable. Use a stable light source, document source/analyzer components and orientation, and evaluate both modes against the same independent reference protocol. This contract records declared component references only; it does not verify the physical filters or their alignment.

## Required capture procedure for the calibrated research path

1. Use a supported camera/device profile and a documented capture app/runtime version.
2. Place the physical colour reference and the selected skin region in the same frame and under the same illumination.
3. Use a controlled diffuse source with measured illuminance, documented illuminant/spectral characteristics and a calibrated meter record.
4. Lock exposure and white balance through the capture runtime where supported; preserve the capture pipeline and embedded ICC/camera profile provenance.
5. Disable beauty filters, portrait relighting, HDR/tone mapping and automatic enhancement for measurement captures. If status is unknown, do not call the capture calibrated.
6. Keep chart, sensor and skin region within the validated geometry; reject glare, clipped patches, deep shadow, chart wear, occlusion, insufficient resolution or out-of-scope camera/lighting.
7. Capture repeat measurements to quantify repeatability. Preserve separate uncertainty for the reference instrument and the camera/model result.
8. Process images in memory; persist only purpose-authorized, minimized evaluation metadata. Raw media remains out of Git and ordinary application containers.

The exposure/white-balance controls and illumination metadata in the new schema are self-reported or device-reported inputs. A future trusted capture runtime must attest which controls it actually applied. Until then, the assessment helper always returns absolute_colour_measurement_approved=false and inference_authorized=false.

## Data contract

The new app.dsi_capture.DSICaptureProvenance model records:
- pseudonymous capture reference;
- reported camera vendor/model, OS and capture-app version;
- capture mode and declared illumination setup;
- optional illuminance reading and calibrated-meter certificate reference;
- white-balance and exposure control states;
- image colour-profile state and profile digest;
- physical chart presence, pinned chart profile, condition and edition;
- HDR/beauty-filter states;
- optional cross-polarizer/analyzer component references and orientation.

It rejects inconsistent combinations (e.g., chart marked present without a pinned profile, cross-polarized mode without both optical components, or embedded ICC without a digest). It intentionally excludes name, account ID, serial number, geolocation, raw EXIF, image bytes, face templates and subject identity.

## Validation protocol

Use CIE 256:2025 as the governing skin-colour measurement reference. Use the CIE Human Skin Colour Database only after reviewing its access/usage terms and confirming that its measurements match the chosen ground-truth task. For the DSI device cohort, acquire same-session independent spectrophotometer measurements with calibration certificate, measurement geometry, reference illuminant/observer and uncertainty.

Freeze the validation plan before collecting the final holdout:
- subjects and anatomical regions; repeated captures per subject;
- camera vendor/model, operating system and image pipeline;
- light source, illumination spectrum/geometry and illuminance;
- chart edition/condition and cross-polarization setup;
- subject-disjoint and out-of-time split definitions;
- duplicate/leakage audit and annotation/ground-truth SOP;
- subgroup slices by measured L* range, region, camera and lighting;
- metrics: CIEDE2000 median/p95/max, Lab-axis bias, repeatability, capture failure/abstention rate, chart-fit error and subject-clustered confidence intervals;
- independent, predeclared release thresholds and reviewer sign-off.

Never set an overall threshold that can conceal an underperforming camera, lighting or measured-colour subgroup. An underpowered or missing required slice remains REVIEW_REQUIRED. No universal ΔE threshold is hard-coded by this P0 contract.

## P0 acceptance

- [x] Strict metadata schema and rejection of contradictory fields.
- [x] Declaration assessment that cannot authorize inference or absolute colour claims.
- [ ] Integrate with a trusted mobile capture runtime and signed capture attestation.
- [ ] Confirm device-level control of exposure/white balance and capture-processing pipeline.
- [ ] Establish calibrated illumination and physical reference handling SOP.
- [ ] Acquire the diverse, consented, subject-disjoint spectrophotometer cohort.
- [ ] Run signed held-out evaluator with independently approved policy.
- [ ] Compare diffuse vs cross-polarized modes on the same cohort.

## Primary references

- CIE, [CIE 256:2025 — Measurement of Human Skin Colour](https://www.cie.co.at/publications/measurement-human-skin-colour-0), DOI 10.25039/TR.256.2025.
- CIE, [Human Skin Colour Database (version 2025)](https://www.cie.co.at/publications/measuring-skin-colour/dataset1-humanskincolourdatabase), DOI 10.25039/TR.256.2025.DS1.
- [A survey of skin tone assessment in prospective research](https://www.nature.com/articles/s41746-024-01176-8), npj Digital Medicine (2024).
- [Consistent Cutaneous Imaging With Commercial Digital Cameras](https://jamanetwork.com/journals/jamadermatology/fullarticle/402500), JAMA Dermatology (2005).
