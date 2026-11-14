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

`POST /v1/search/image` is a separate route from Click It. It requires both `image_processing` and `look_it` consent assertions from the private PNELLY service. It enforces the same 10 MiB and decoded-image quality gates, loads only current active Commerce offers enriched with active Catalog product descriptions, and ranks the uploaded outfit reference against product text using the pinned CLIP model. The source image is not written to disk or persisted by this service.

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
