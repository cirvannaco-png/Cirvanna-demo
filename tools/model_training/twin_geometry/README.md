# Cirvanna-owned parametric Twin geometry foundation

This is the first proprietary geometry track for Virtual Twin. It does not select an external body model. It learns a Cirvanna parametric shape basis from consented, registered 3D body scans and fits a separate linear calibration from shape coefficients to trained-anthropometrist tape measurements.

The current implementation is deliberately narrower than a complete Twin:
- PCA shape basis over a common registered mesh topology.
- Mesh reconstruction from shape coefficients.
- Ridge calibration of five anthropometric outputs from those coefficients.
- Held-out surface and tape-measure error reporting.
- Strict rights, subject-disjoint split, topology, anatomical landmark and mesh integrity checks.

It does not infer shape coefficients from photographs, solve camera/pose ambiguity, reconstruct appearance or hair, generate a persistent user avatar, or prove independent anatomical validity.

## Measurement acceptance threshold

The held-out test report now applies a pre-registered maximum of **4.0% MAPE for each of the five measurements independently** (height, chest, waist, hip and inseam). Missing evidence, an empty test sample for any measurement, or any one measurement above 4.0% fails this accuracy gate. Passing this numeric gate is necessary but not sufficient: it does not replace anthropometrist-led independent validation, subgroup error/confidence intervals, repeatability testing, scan-to-photo generalization testing, or calibration drift analysis. The current model remains research-only until those independent gates pass.

## Dataset requirements

Use a 3D scan cohort collected under explicit, revocable consent for commercial model training and human review. The data-rights manifest scope is twin_geometry_training, and the rights validator requires verified depicted-person consent.

Every mesh must:
- be in millimetres using right_handed_x_right_y_up_z_forward;
- be registered to one template topology and one documented alignment protocol;
- preserve real-world scale (do not normalize each body to unit height);
- have valid triangular faces and finite, bounded coordinates;
- be split by pseudonymous subject cluster, with no participant crossing train/validation/test;
- include independently annotated anatomical landmarks and tape measurements using one documented measurement protocol.

The mesh archive is an NPZ with arrays named vertices (N x 3 float) and faces (M x 3 integer). Annotation JSONL contains sample_id, subject_cluster_id, split, mesh_path, mesh_sha256, alignment_protocol_id, landmarks_mm, measurements_mm and non-identifying subgroup labels.

## Validate the cohort

    python tools/model_training/twin_geometry/validate_dataset.py \
      --manifest /restricted/twin-geometry/dataset.manifest.json \
      --annotations /restricted/twin-geometry/annotations.jsonl \
      --mesh-root /restricted/twin-geometry/meshes \
      --rights-manifest /restricted/twin-geometry/data-rights.manifest.json

## Fit the shape basis and measurement calibration

    python tools/model_training/twin_geometry/train_shape_model.py \
      --manifest /restricted/twin-geometry/dataset.manifest.json \
      --annotations /restricted/twin-geometry/annotations.jsonl \
      --mesh-root /restricted/twin-geometry/meshes \
      --rights-manifest /restricted/twin-geometry/data-rights.manifest.json \
      --output-dir /restricted/twin-geometry/run-001 \
      --components 20 --ridge-alpha 1.0

PCA and measurement regression fit on the train split only. Validation and held-out test splits are reported separately. The checkpoint and report are written owner-only with digests. The test split must remain sealed until the shape dimension and ridge alpha are preregistered.

## Production measurement acceptance gate

The production target is no more than 4% relative error for each supported body measurement on a subject-disjoint, independently measured holdout cohort. Before opening the sealed test split, preregister the exact error statistic (for example, MAPE), supported measurement set, acceptable missingness, capture protocol, repeatability criteria and subgroup minimums. Report per-measurement MAE, median absolute error, P95, signed bias, relative error, confidence intervals and subgroup results; do not average away a failed measurement or subgroup. The current PCA/Ridge reports are research diagnostics only and do not demonstrate this target. No fit, size recommendation or body-measurement claim may be enabled until independent anthropometrists verify the holdout results and repeated-capture stability.

## Interpretation

- Surface vertex errors measure reconstruction of registered scans using a low-dimensional shape basis. They do not measure photo-to-3D accuracy.
- Tape-measure MAE, median error, P95 and bias are compared with independent tape measurements. The report is not a pass/fail calibration certificate.
- Subgroup-specific confidence intervals and minimum cohort counts must be preregistered before the final test.
- The shape basis is a research geometry asset. It is not a persistent Twin and must not be used for sizing or fit claims until photo reconstruction, independent anatomical validation, repeated-capture calibration, and privacy/deletion qualification pass.

## Multi-view reconstruction solver

The first inverse-geometry solver is fit_multiview_capture.py. It fits the learned shape coefficients to supplied front/side 2D body landmarks and silhouette bounding boxes using calibrated 3x4 camera projection matrices. The capture protocol must hold a consistent canonical pose and known camera calibration; every view is bound to its image digest and segmentation-mask digest. The solver requires a separate twin_geometry_inference rights manifest with verified subject consent. Capture records pin the keypoint and silhouette model revisions/weights, require face masking before inference, and bind the preprocessing manifest.

    python tools/model_training/twin_geometry/fit_multiview_capture.py       --model /restricted/twin-geometry/run-001/cvi-parametric-body-model.npz       --capture /restricted/twin-geometry/captures/capture-001.json       --rights-manifest /restricted/twin-geometry/captures/consent.manifest.json       --output-dir /restricted/twin-geometry/captures/capture-001-fit

This is a multi-view parametric fitting prototype, not an end-to-end photograph model. It consumes keypoints and silhouette bounds produced by upstream vision components; it does not itself inspect raw pixels, infer pose, segment the person, solve arbitrary pose changes or reconstruct appearance. The silhouette bounding-box constraint is coarse and cannot replace a dense mask/surface objective. The preprocessing and face-masking fields are declared evidence bindings in this prototype; they are not independently cryptographically attested by the solver. The solver exports a private texture-free GLB candidate as well as its NPZ geometry. The GLB is checked for finite geometry, degenerate triangles, boundary edges and non-manifold edges using the existing Twin Mesh Validator in the test suite. This is structural mesh validation, not anatomical validation. The resulting mesh and measurement estimates remain research candidates and are not yet persisted in Twin Registry.

No SMPL, SAM 3D Body or commercial avatar provider is required for this parametric shape-basis track. The model is still dependent on a high-quality, rights-cleared 3D scan cohort and independent measurement expertise.
