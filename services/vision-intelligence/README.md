# Cirvanna Vision Intelligence

**Status:** model-backed inference code and an immutable CLIP model pin are implemented. Runtime deployment, real-weight inference, retrieval accuracy and operational integration remain unverified.

## What this service does

- Uses OpenAI CLIP image/text embeddings to rank current active, approved, in-stock Commerce offers against a product photo or natural-language description.
- Evaluates capture quality deterministically: valid image format, byte/pixel/dimension bounds, brightness, contrast, sharpness proxy and clipped-pixel fraction.
- Uses MediaPipe Pose Landmarker to infer normalized 2D and approximate 3D landmarks for a **pose-skeleton Virtual Twin**.
- Enriches marketplace offer records with canonical Catalog service active product descriptions and attributes in bounded batches.
- Returns structured, sanitized errors. Submitted photos are decoded in memory and are not written to disk or logged by this service.

The Click It image search compares the uploaded image embedding against text/metadata descriptions in CLIP's shared embedding space. It does **not yet compare the photo against every merchant product photograph**, so output is candidate retrieval, not definitive SKU recognition. Similarity values are cosine scores, not calibrated probabilities.

The Virtual Twin inference is an approximate pose skeleton, not a body surface mesh. It does not estimate calibrated circumference/fit measurements, produce a photorealistic avatar, or persist a Twin record. These are explicit limitations, not successful results hidden behind placeholders.

## Model lock

- Repository: openai/clip-vit-base-patch32
- Immutable revision: d44250afa9f05af7eca021052567539406661018
- CLIP_MODEL_REVISION must be supplied and exactly match this source pin. Any change requires a reviewed code change and renewed evaluation.
- CLIPModel loading explicitly requires safetensors; mutable branches such as main are rejected.
- MediaPipe Pose Landmarker weights are supplied as an external .task file with an exact POSE_LANDMARKER_MODEL_SHA256 checksum. No model weights are committed to this repository.

The upstream CLIP model card warns that it was not intended as a general deployment model and that evaluation is limited across languages, among other limitations. Treat this implementation as a controlled prototype until the upstream model/use restrictions have been reviewed and in-domain accuracy, bias, privacy and commercial-use gates have passed. See the official [CLIP model card](https://huggingface.co/openai/clip-vit-base-patch32).

## API

- GET /health — process liveness only.
- GET /ready — requires worker authentication configuration, a pinned and loaded CLIP model, an exact-checksummed pose model, and trusted Commerce/Catalog settings.
- GET /capabilities — exact feature boundaries and model readiness.
- POST /v1/click-it/scan — in-memory image-quality assessment, image/text similarity and live marketplace-candidate retrieval.
- POST /v1/search/text — product/garment retrieval from natural-language descriptions.
- POST /v1/twin/infer — in-memory pose-landmark inference from one still image.

All POST routes require an internal bearer token. Never expose VISION_WORKER_TOKEN in browser code. The public-facing adapter must verify durable server-side consent and user/Twin authorization before it invokes this worker. Form consent flags are secondary safeguards, not proof of a stored consent record.

## Required environment

- VISION_WORKER_TOKEN: internal bearer secret at least 32 bytes long.
- CLIP_MODEL_REVISION: exactly d44250afa9f05af7eca021052567539406661018.
- POSE_LANDMARKER_MODEL_PATH: path to a provisioned MediaPipe Pose Landmarker .task bundle.
- POSE_LANDMARKER_MODEL_SHA256: exact SHA-256 of that file.
- COMMERCE_API_URL: trusted HTTPS base URL for Cirvanna Commerce.
- CATALOG_API_URL and CATALOG_API_TOKEN (or CATALOG_READ_TOKEN): trusted Catalog URL plus read-only token. The service calls GET /products/batch for active descriptions, categories, brands and product attributes.
- A mounted Hugging Face cache or outbound access to fetch the exact CLIP revision at startup.

Build using services/vision-intelligence/Dockerfile. Keep the service private with bounded concurrency, request-size limits at ingress, per-account rate limits, timeouts, CPU/GPU limits and redacted operational logs. No user images or model weights belong in source control.

## Quality and policy boundaries

- Image-quality guardrails detect clearly unusable captures; they are not trained/calibrated and thresholds need labeled-data validation.
- Model errors, unreadable images, incomplete body landmarks and missing Catalog metadata fail closed instead of inventing a match.
- CLIP scores are not probabilities. A high similarity score does not authorize display or purchase.
- Search candidates must pass NPL hard vetoes, explicit cultural-identity requirements and CAL arbitration before being shown. This worker does not call CAL and cannot mark a result SHOW.
- Never infer body circumference, skin condition, fit, health status, ethnicity, religion or other sensitive traits from the pose skeleton or marketplace-image embedding.

Before enabling user-facing use, evaluate photo-vs-catalog precision/recall, no-match behavior, duplicate and near-duplicate products, lighting, occlusions, garment categories, body/skin-tone coverage, language performance, end-to-end latency and resource costs using a consented labeled holdout. Confirm license/commercial-use posture and audit data/model retention. Passing mock API tests is not evidence of real inference quality.
