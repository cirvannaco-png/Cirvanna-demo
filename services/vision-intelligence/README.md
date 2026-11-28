# Vision Intelligence service

## Status and release boundary

This service implements guarded inference APIs for text-to-live-offer retrieval, ephemeral PNELLY Look It image-to-live-offer retrieval, and a partial MediaPipe 3D pose skeleton. It is **not production-validated**. The repository does not prove that the pinned CLIP weights have been downloaded, that a checksummed Pose Landmarker asset is provisioned, or that a CUDA-compatible GPU is attached to a live deployment. Unit tests mock model inference; they do not demonstrate live model quality, throughput, or GPU execution.

Readiness is deliberately fail-closed. Configure the exact reviewed CLIP revision, the pose model path and SHA-256, a worker token of at least 32 bytes, trusted Commerce/Catalog URLs, and a Catalog read token. The service loads model weights at startup and reports model-load failures via sanitized readiness fields. The Dockerfile is based on CPU-oriented `python:3.12-slim`; it does not install CUDA or prove GPU availability. For GPU deployment, use a separately qualified CUDA base/runtime, compatible NVIDIA driver and pinned PyTorch build, and run a smoke test that asserts `torch.cuda.is_available()` and exercises both image/text embeddings and pose inference.

## Image acceptance criteria (version 1)

Input contract:
- JPEG, PNG or WebP only; declared content type and decoded file format must agree with the supported set.
- At most 10 MiB and 25,000,000 decoded pixels; minimum width and height are each 128 px.
- Reject empty, malformed, truncated, decompression-bomb, or oversized images before model inference.
- Decode to RGB and do not persist source image bytes.

Deterministic capture-quality gate:
- Mean grayscale intensity must be in [18, 238] on the 0–255 scale.
- Grayscale standard deviation must be at least 8.0.
- Laplacian-variance sharpness proxy must be at least 20.0.
- Fraction of pixels at intensity <=3 or >=252 must not exceed 0.55.
- Any failed condition returns HTTP 422 with `IMAGE_QUALITY_REJECTED`, stable failure codes, and metrics; model inference must not run.

These are conservative initial engineering thresholds, not clinically or scientifically validated universal cutoffs. Camera pipelines, image resizing, texture and compression affect them. Calibrate thresholds against a consented, labeled capture set spanning devices, lighting, skin tones, poses, garment types and product photography; publish false-reject/false-accept rates before relaxing them. The sharpness metric is a proxy, not a calibrated focus score.

Pose-specific rejection:
- Reject if no normalized or world landmarks are returned.
- Require 33 landmarks in each representation and visibility >=0.45 for both shoulders, both hips, and both ankles.
- Even accepted landmarks are not calibrated anthropometric measurements. No surface mesh, clothing fit grade, or purchase approval is inferred.

Retrieval reliability:
- CLIP cosine similarities are ranking scores, **not probabilities**. The current service does not apply a validated absolute-match threshold or calibrated top-1/top-2 margin because no labeled retrieval evaluation has established one. Therefore results are candidates only; downstream UI must clearly ask the user to confirm the item, and NPL, explicit cultural requirements, and CAL must run before display or action.
- If embeddings are non-finite/zero-norm, model loading/inference fails, marketplace contracts are malformed, or upstream dependencies are unavailable, return a bounded error rather than fabricated results.
- Click It currently compares the photographed product embedding with textual offer metadata, not the actual catalog product images. This is approximate cross-modal retrieval, not exact visual duplicate detection.

## PNELLY Look It image search

`POST /v1/search/image` is a separate route from Click It. It requires `image_processing` + `look_it` consent and a declaration-specific photographed-person scope from the private PNELLY service. Only the `no_people` user attestation is accepted; all other or missing declarations are rejected. This is not automated person detection or age verification. The detector is not general person detection or age verification. If it detects any face despite the no_people attestation, the request is rejected before quality scoring, embedding or Catalog retrieval. A zero-face result still cannot prove that no people are present. The face detector runs before downstream processing. Any detected face causes rejection; only a zero-face result proceeds, and that result is not proof that no people are present. The unmasked buffer is closed immediately after the detector step. It enforces the same 10 MiB and decoded-image quality gates, loads only current active Commerce offers enriched with active Catalog product descriptions, and ranks the masked outfit reference against product text using the pinned CLIP model. The source image is not written to disk or persisted by this service. The no_people declaration does not bypass face detection; a face-positive image is rejected rather than masked and searched. 

The Vision response contains only an aggregate candidate count, image-quality diagnostics, and optional outfit-component descriptions/counts. It does **not** return product IDs, merchant names, prices, stock, product photos, or product descriptions. Merchant comparison remains pending CAL; after CAL SHOW, the BFF/Commerce offer-comparison route must produce an exact product/variant and destination-specific landed-cost comparison. CLIP scores remain ranking scores, never probabilities or fit evidence.

Optional outfit decomposition calls an external provider only when its trusted URL/token, exact model ID/revision, validation-report digest, and separate `OUTFIT_DECOMPOSITION_PRIVACY_APPROVAL_SHA256` digest are configured. The privacy-approval digest is a release control, not proof by itself that a provider is deployed, licensed, contractually approved, or enforcing the required retention policy. Without all pins, decomposition returns unavailable and no image is sent to that provider.

## Live catalog contracts

The service reads `GET {COMMERCE_API_URL}/marketplace/offers?offset=0&limit=100`. Commerce returns `items`, `total`, `offset`, `limit`; offer rows include `variant_id`, `catalog_product_id`, `product_name`, `category`, `options`, `available_stock`. Commerce itself filters inactive offers/variants, unapproved merchants and zero available stock.

The service enriches canonical product IDs with authenticated `GET {CATALOG_API_URL}/products/batch?ids=<uuid>&ids=<uuid>`, using `CATALOG_API_TOKEN` or `CATALOG_READ_TOKEN`. The catalog response is `{ "items": [ProductOut, ...] }`; active products include `product_id`, `name`, `description`, `category`, `brand`, `attributes`, `image_urls`, and `status`. Unknown/archived catalog products are omitted. The batch limit is 100 UUIDs per request. The adapter fails closed on missing/malformed enrichment rather than silently degrading to title-only search.

## Required validation before production

1. Run service unit/contract tests and repository CI.
2. Run integration tests against the real Commerce and Catalog APIs, including pagination, empty catalog, archived product omission, inventory depletion, upstream timeouts, invalid UUIDs, and malformed responses.
3. Provision and verify the exact model assets and runtime; record weight hashes, model revisions, device/runtime versions and inference smoke-test output.
4. Evaluate image-quality thresholds on labeled images and retrieval using top-k recall, precision, score/margin distributions, and subgroup error rates. Do not present a match threshold as confidence until calibrated and independently validated.
5. Keep durable resource-bound consent verification/expiry/revocation, Twin ownership, no-store response headers, and CAL/NPL/cultural hard-veto integration as release gates.
6. For Look It, verify the BFF-created consent bundle lifecycle and Xari re-verification against real Identity in staging; keep optional decomposition disabled until its privacy approval and provider operation are independently reviewed.


## Measurable capture rejection criteria

The current deterministic gate is intentionally conservative and is **not a validated accuracy score**. It rejects a capture before inference if any of these checks fail:

- Encoded payload exceeds 10 MiB; image is empty, corrupt, or not a JPEG/PNG/WebP payload matching the supported MIME family.
- Decoded width or height is below 128 pixels, or total pixels exceed 25,000,000.
- Mean grayscale brightness is below 18 or above 238 on the 0–255 scale.
- Grayscale contrast standard deviation is below 8.
- The sharpness proxy (mean variance of horizontal and vertical adjacent-pixel differences) is below 1.5.
- More than 55% of pixels are clipped near black (≤3) or white (≥252).

For pose inference, reject if a pose/world-landmark group is absent, fewer than 33 landmarks are returned, or any critical shoulder/hip/ankle landmark visibility is below 0.45. This is a visibility gate, not a guarantee that the person is fully framed or that body geometry is accurate.

These numeric thresholds are versioned heuristics chosen to block obvious failures; they must be re-tuned on a consented, labeled capture set before production. Current Click It does not have a validated semantic “this is a product” classifier or a calibrated no-match threshold. It therefore cannot honestly guarantee rejection of every irrelevant scene or reliable SKU identification. It returns candidate-only results, never display authorization. Before any UI is allowed to surface candidates, CAL must receive the ranking evidence and may abstain; do not interpret cosine scores as probabilities.

## Click It face-detector asset

The Vision Docker image now provisions the **versioned MediaPipe BlazeFace full-range detector** during build and verifies both its exact byte count and SHA-256 before the image can be built:

- Source: https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_full_range/float16/1/blaze_face_full_range.tflite
- Size: 1,083,786 bytes
- SHA-256: `3698b18f063835bc609069ef052228fbe86d9c9a6dc8dcb7c7c2d69aed2b181b`
- Runtime: MediaPipe Tasks FaceDetector, IMAGE mode, detector-only output (bounding boxes and confidence scores).
- Licence: Apache License 2.0; attribution and model-card link are in `third-party/NOTICE-MEDIAPIPE-BLAZEFACE-FULL-RANGE.md`.

The Docker build performs a real model-load and inference smoke test on a synthetic no-face image. This proves the pinned asset can load and execute in the container; it does **not** prove face recall, subgroup parity, or safe publication.

**Known model limits:** the Google model card says this model is intended for prominent faces in smartphone images, is sensitive to face scale/orientation/position and lighting, and is out of scope for faces turned away, strongly inclined, beyond roughly 5 metres, or crowds beyond its detection limit. The model card reports 89.3% average recall across its 17 geographic subregions and explicitly lists faces turned away, strongly inclined faces and people beyond roughly five metres as out of scope. That is not a sufficient false-negative rate for public privacy protection. The model card's reported evaluation is not a substitute for Cirvanna's own consented representative-image evaluation. Therefore:
- Click It still blocks on missing, low-confidence, malformed or uncertain detector output.
- Every detected face must be masked before downstream quality scoring, embedding or retrieval.
- Any public image still requires an asset-digest-bound, independently human-reviewed attestation; the detector alone never authorizes publication.
- Keep public image URLs withheld until the attestation and Content Lifecycle providers are live and every publisher is wired to the gate.

For non-Docker deployments, configure `CLICK_IT_FACE_DETECTOR_MODEL_PATH` and `CLICK_IT_FACE_DETECTOR_MODEL_SHA256` to the same verified bytes. Never point the service at a floating `latest` model URL or disable checksum verification.


## DSI-specific visual inference

The DSI visual worker is a separate private route set in the existing Vision Intelligence service. It does not depend on CLIP, Commerce or Catalog readiness.

- GET /v1/dsi/ready loads and verifies both DSI model assets, including the segmenter's metadata label order. It returns 503 until both tasks load successfully.
- POST /v1/dsi/face-landmarks accepts one still image and returns 478 normalized face landmarks only when exactly one face is found. It does not compute blendshapes, facial transformation matrices, embeddings, identity, age or recognition.
- POST /v1/dsi/skin-segmentation accepts one still image and returns face-skin/body-skin masks, coverage fractions and model-specific non-calibrated segmentation diagnostics. The required label order is background, hair, body-skin, face-skin, clothes, others.

Every DSI endpoint requires DSI_VISION_WORKER_TOKEN (at least 32 bytes), emits no-store/private responses, decodes uploads in memory, and retains no source media. Put these routes behind private service networking in addition to bearer authentication. The DSI token must be separate from VISION_WORKER_TOKEN.

### Out-of-band model provisioning

No DSI model weights are committed or downloaded at application startup. Supply these settings through the deployment environment and a managed asset mount:

- DSI_FACE_LANDMARKER_MODEL_PATH
- DSI_FACE_LANDMARKER_MODEL_SHA256
- DSI_FACE_LANDMARKER_MODEL_VERSION
- DSI_SKIN_SEGMENTER_MODEL_PATH
- DSI_SKIN_SEGMENTER_MODEL_SHA256
- DSI_SKIN_SEGMENTER_MODEL_VERSION

A path, immutable version and 64-character SHA-256 must be present for each task; the running worker hashes the file before loading it. Missing or mismatched assets fail closed. Use `dsi-model-assets.example.env` only as a variable-name template; never put real credentials or model weights in Git.

### Model capability and limitations

The ColorChecker Classic post-November-2014 profile is used only when the user confirms the printed chart edition on the back of the physical target. X-Rite states that the production date is printed there and that post-November-2014 targets require revised reference data. The reference file contains generic averaged colour values; custom measurements of the user's individual target are preferable for highest accuracy. Chart age and visible condition are recorded as user declarations, not hard eligibility cutoffs or proof of reflectance stability. Worn condition produces an advisory warning; the preview remains optional.

The Face Landmarker task produces 478 normalized 3D landmarks. DSI currently derives only three provisional geometric ratios from selected landmark anchors; it does not classify face shape or hairline. These ratios are explicitly marked unvalidated until compared with an independently annotated, representative face-geometry dataset.

The multiclass selfie segmenter provides six coarse semantic regions. It distinguishes face skin from body skin, but it does not identify individual neck, chest, arm, hand or leg regions. It is not a skin-tone or colour-calibration model. DSI currently returns region coverage only and computes no sRGB or CIELAB tone value.

**Population coverage warning:** the official MediaPipe model card for the 256×256 multiclass selfie segmenter reports only 31 evaluation images for Monk skin tones 9–10 (about 1.6% of the evaluation set). This is not sufficient evidence of robust performance for every global population, lighting condition or camera. DSI must run its own held-out, subgroup-balanced evaluations before making accuracy claims or enabling tone recommendations.

Official upstream references:
- Face Landmarker task documentation: https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker
- Face Landmarker model card: https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Face%20Landmarker%20V2.pdf
- Image Segmenter task documentation: https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter
- Multiclass selfie segmenter model card: https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Selfie%20Multiclass.pdf

The referenced model cards specify Apache License 2.0 for their model artifacts. Verify the exact provisioned artifact, version, license notice and model-card provenance before deployment. Record the actual digest in the deployment manifest; do not assume that a model family name pins a particular asset.

No DSI model asset, subgroup evaluation or calibration result is implied by the mocked worker tests. The DSI service remains unready when assets are not provisioned, and DermalSight must continue to label geometry and segmentation previews as unvalidated.


## Experimental ColorChecker calibration worker

The private POST /v1/dsi/colorchecker-tone-preview worker fits a 3×4 affine transform from linearized sRGB input to D50 XYZ using the 24 post-November-2014 X-Rite ColorChecker Classic reference patches. The user confirms the chart edition and selects its 6-column × 4-row patch-grid corners in TL/TR/BR/BL order. The request also selects face_skin, body_skin or both; the worker summarizes only the requested region(s).

The output carries a profile SHA-256, all 24 leave-one-patch-out CIEDE2000 errors, patch clipping/dispersion diagnostics, and candidate D50 CIELAB summaries. It is explicitly experimental and unvalidated. The chart age and condition are declared by the user and are not hard eligibility gates; patches with more than 5% clipped sample pixels are excluded from the fit, and at least 18 usable patches plus four neutral patches are required. The DSI worker does not persist the original image, profile or training data and cannot authorize CAL or persistent personalization.

The X-Rite reference values are generic averages. X-Rite notes that post-November-2014 charts require revised reference data and that custom measurement of an individual chart is preferable for highest accuracy. The chart's manufacture date is printed on its back. See the upstream source and reference-profile hash in app/colorchecker_profile.py.

The camera transform, chart fit, colour calibration, local illumination behaviour and coarse segmentation remain unvalidated across phones, lighting setups and skin-tone groups. The emitted values must not be described as exact or used for shade ranking until independently validated. Synthetic numerical tests establish implementation consistency only; they are not a substitute for physical chart captures and spectrophotometer ground truth.


## Offline DSI colour validation

The `validation/dsi_color` package is an offline evaluation harness, not a live endpoint. It compares candidate DSI colour previews with independent CIE Lab D50 reference measurements and emits overall and subgroup performance reports.

The CLI requires:
- a manifest signed over its exact JSON bytes by a trusted dataset custodian;
- a sample JSONL whose exact SHA-256 matches the signed manifest;
- a release policy signed over its exact JSON bytes by an independently authorized policy approver;
- detached Ed25519 signatures and public PEM files whose DER SHA-256 fingerprints match out-of-band environment pins.

Required trust pins:
- `DSI_EVALUATION_TRUSTED_MANIFEST_PUBLIC_KEY_SHA256`
- `DSI_EVALUATION_TRUSTED_POLICY_PUBLIC_KEY_SHA256`

The evaluator reports CIEDE2000 error, signed Lab bias, reference-instrument uncertainty, chart-fit error, failure rate, repeatability and subject-clustered confidence intervals. It slices results by skin region, camera, lighting, reference L* range, OS family, chart condition and measurement geometry. A failing camera or lighting subgroup cannot be hidden by an acceptable aggregate.

Incomplete policies, absent signatures, missing repeatability or underpowered slices remain `REVIEW_REQUIRED`. Threshold violations return `FAIL`. A `PASS` is scoped only to the exact hashed model, segmenter, chart profile, signed dataset and policy. Synthetic fixtures are not production evidence. This harness does not train or deploy models and cannot change live DSI readiness.

See [validation/dsi_color/README.md](validation/dsi_color/README.md) for dataset schema, signing workflow, CLI use and release decision semantics.


## DSI P0 capture provenance

The first P0 increment adds a strict, non-identifying capture-provenance contract in app.dsi_capture and unit tests for controlled-diffuse, ambient-relative and cross-polarized declarations. It records declared exposure/white-balance states, illumination and meter provenance, image colour-profile digest, chart integrity, HDR/beauty-filter state and optional polarizer/analyzer references.

This is contract groundwork only: no image route consumes it yet, client/device declarations are not trusted evidence, and a complete declaration cannot approve absolute colour measurement or enable inference. A signed trusted capture-runtime attestation, measured lab protocol, independent spectrophotometer cohort and signed held-out evaluation are still required. See validation/dsi_color/capture-protocol.md.


## DSI device baseline registry

DSI now has a private, no-image `POST /v1/dsi/device-baseline` lookup and a versioned registry contract under `app.dsi_device_baselines`. A device baseline is **not** keyed by manufacturer/model alone. Its exact fingerprint includes platform, manufacturer/model, camera module identifier, front/rear and lens role, OS release, camera API, capture runtime/version, pipeline revision, output format and colour-profile digest.

The registry supports three qualification levels:

1. `capture_candidate`: the exact pipeline has passed a capability/interoperability review and meets its profile's minimum capture standard. It is research/capture guidance only; it cannot authorize an absolute colour result.
2. `colour_validated`: the exact pipeline has independent colour validation against a held-out spectrophotometer reference cohort, with dataset/report/calibration digests, validated regions/skin-lightness ranges/lighting slices, instrument traceability, independent review and an expiry.
3. `cross_polarized_validated`: the colour-validation requirements plus a separate optical validation report for the source polarizer/camera analyzer setup. Diffuse and cross-polarized captures remain separate protocols.

The request's device/camera facts and capture controls are client declarations. The lookup endpoint deliberately passes `capture_attestation_verified=false` and therefore returns `relative_only`, even when an exact profile is found and all declarations meet its minimum. The future trusted capture runtime/attestation verifier must be integrated before a profile can be operationally used. A client cannot submit a boolean to override this boundary.

The registry is mounted out-of-band using `DSI_DEVICE_BASELINE_REGISTRY_PATH` and pinned using `DSI_DEVICE_BASELINE_REGISTRY_SHA256`. Both must be configured together. A missing registry means no devices are qualified; an invalid file or digest returns a sanitized 503. The example file `dsi-device-baseline-registry.example.json` is intentionally empty and does not certify any phone model. Do not add a device profile until physical camera samples, independent reference measurements, exact-pipeline scope and reviewer approval exist.

### Per-device minimum standard

Each profile defines its own accepted output formats/resolutions, control requirements, chart profile and supported capture mode. The service checks, at minimum, the profile-specific conditions for locked exposure, locked white balance, HDR/beauty processing disabled, chart presence/condition, output format/resolution and either RAW with available sensor colour-calibration metadata or a pinned colour-managed output profile. There are no invented universal resolution or accuracy thresholds: each profile's thresholds must come from its predeclared evaluation protocol.

The fingerprint is intentionally more granular than a marketing phone name. Android Camera2 exposes device capability flags and optional per-device sensor calibration transforms; RAW capability, manual post-processing and AWB lock support vary by camera. CameraX exposure-compensation support alone is not proof of locked exposure or calibrated colour. iOS uses AVFoundation device-specific configuration locks and exposes explicit support for white-balance locking. A pipeline update, camera-module/lens change, OS release, capture-runtime change, output format or colour-profile change creates a new exact profile lookup and defaults to unqualified until reviewed.

Model-level qualification is a baseline, not proof that every physical unit is identical. The same-frame colour reference remains required by the profile; the release study must measure between-unit variation. Where the study finds material unit variation, add a per-unit calibration step or narrow the profile scope rather than assuming the model label covers it. Never persist hardware serials or IMEIs to achieve this.

The endpoint accepts no image, performs no skin inference and does not create user profiles. It is protected by the dedicated DSI worker credential and emits no-store/private headers. Unknown devices, expired/suspended profiles, unsupported camera settings, missing chart evidence, and unverified runtime attestations all remain relative-only.


**Authority boundary:** `colour_validated` and `cross_polarized_validated` identify a validated camera-pipeline scope only. The resolver reports the approved regions/lightness ranges/lighting slices as scope metadata; it does not authorize an individual measurement. `absolute_colour_measurement_allowed` remains false. The downstream task must independently check the requested region, the measured L* range, current chart/capture evidence, image quality, task-specific model release and uncertainty before producing any absolute colour result.


## Native Android Camera2 capture evidence SDK (scaffold)

The monorepo now contains a standalone Android library at `apps/dsi-android-capture`. It is not a complete Android app and is not yet an integrated capture provider.

The SDK:
- inspects Camera2 logical/physical camera IDs, lens/sensor characteristics, RAW/JPEG stream sizes, available request/result keys, per-device calibration transforms, colour transforms, forward matrices and reference illuminants;
- fingerprints the exact camera path using a backend-compatible canonical device-baseline schema that includes platform API/build, camera ID, physical camera IDs, lens role, OS/security patch, runtime/app versions, output format/profile, sensor metadata and available keys;
- begins with unlocked AE/AWB metering, requests locks after convergence and checks lock booleans plus LOCKED states in the actual `TotalCaptureResult`;
- binds the exact image byte digest and output dimensions to the same frame by requiring `Image.timestamp == CaptureResult.SENSOR_TIMESTAMP`;
- embeds a `dsi-device-capture-v1` baseline report inside the canonical signed capture manifest;
- creates a client-side Android Keystore hardware-key-attestation candidate and a Play Integrity Standard API request bound to the manifest hash.

The SDK deliberately reports HDR and beauty-processing state as unknown because Camera2 does not expose a universal attestation of hidden OEM processing. Key attestation and Play Integrity support app/device integrity and request binding; they do not prove physical sensor origin of the signed pixels. The backend challenge, nonce replay protection, Android certificate-chain/root/CRL verification, Play Integrity decode, consent/resource binding and server-issued verification receipt are not implemented yet; track that work in issue #214.

Every SDK envelope remains `pending_server_verification`. No Android device is certified and no absolute colour measurement, inference readiness or CAL authorization is enabled by the native library. See [Android SDK protocol and physical acceptance gates](../../apps/dsi-android-capture/README.md).

## Private retrieval benchmark catalogue snapshot export

The Vision service includes a one-off CLI, `app/retrieval_snapshot_export.py`, for the fashion retrieval research workflow. It calls the same internal `_live_offers()` function used by marketplace retrieval, so active Catalog filtering, current Commerce eligibility, the existing 1,000-offer bound, Commerce order and exact `_offer_description()` text are reused rather than rebuilt by a separate script.

Run it only from an isolated build/checkout of the reviewed research branch, inside a trusted Vision service environment; the exporter is not present in `main` until this PR is merged. Do not deploy this research branch to the customer-facing Vision service just to obtain a snapshot. The environment must already have the existing `COMMERCE_API_URL`, `CATALOG_API_URL` and `CATALOG_API_TOKEN` or `CATALOG_READ_TOKEN` are already configured. Mount or provide a restricted evaluation volume, then run from the service's `/app` working directory:

```sh
python -m app.retrieval_snapshot_export \
  --output /restricted-evaluation/catalog-offers.jsonl
```

The exporter emits only `variant_id` and the exact `search_text` used by the current ranker. It does not export product names separately, image URLs, raw Commerce/Catalog objects, service URLs or credentials. It writes a sibling SHA-256 manifest and creates both files with mode `0600` inside an owner-only POSIX directory; refuses shared destination directories; existing files are never overwritten; choose a new versioned output path for each snapshot.

The manifest records candidate count, source service/model pin, Commerce truncation state, source field semantics, order preservation, file digest and the fact that this is a sequential point-in-time Commerce/Catalog read rather than a cross-service transaction. If the service reports that the Commerce offers list exceeded its 1,000-offer cap, that fact is recorded; the exported candidate set still represents the service's current bounded retrieval universe.

The output contains commercial catalogue text and variant identifiers. Keep it in an approved access-controlled evaluation workspace. Never commit it to GitHub, attach it to a public issue/PR, or send it to an unapproved external model endpoint. The exporter is a research utility, not a new public API or customer-data export endpoint.
