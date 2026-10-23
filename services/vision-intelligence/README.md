# Cirvanna Vision Intelligence

Status: model-backed inference code implemented; real models and live service integrations are deployment-gated.

## What this service does

- Uses a pinned OpenAI CLIP image/text encoder to rank current, active, approved, in-stock marketplace offers against a photograph or natural-language description.
- Evaluates capture quality (decode, dimensions, brightness, contrast, blur proxy, clipped pixels) before image retrieval. Quality checks are deterministic guardrails, not a learned image-quality score.
- Uses MediaPipe Pose Landmarker to infer normalized 2D and approximate 3D pose landmarks for a Virtual Twin skeleton representation.
- Returns opaque, structured outcomes and sanitized failures. Submitted photos are decoded in memory and are not written to disk or logged.
- Enriches offers from the canonical Catalog service in bounded batches. It does not fetch arbitrary product-image URLs.

A photo scan ranks catalog text/metadata against an image embedding in CLIP's shared image/text space; it does not yet compare the submitted photo with every merchant product photograph. Match scores are cosine similarities, not calibrated probabilities. Exact visual SKU identification and purchase decisions require independent evaluation. The 3D pose skeleton is not a body-surface mesh, and it does not provide calibrated circumference or fit measurements.

## API

- GET /health — process liveness only.
- GET /ready — confirms configuration and pinned model asset presence; it stays unavailable until worker auth, model revisions/assets and trusted marketplace APIs are configured.
- GET /capabilities — exact feature boundaries.
- POST /v1/click-it/scan — in-memory image scan and live marketplace retrieval; requires explicit image-processing and Click It consent flags.
- POST /v1/search/text — product/garment retrieval from a natural-language description.
- POST /v1/twin/infer — in-memory MediaPipe 3D pose landmark inference; requires explicit image-processing and body-measurement consent flags.

All POST routes require an internal bearer token. Never expose VISION_WORKER_TOKEN in browser code. The public-facing service must verify durable server-side consent and user/asset authorization before it invokes this worker. The form consent flags are a secondary guard, not proof of a stored consent record.

## Required deployment configuration

- VISION_WORKER_TOKEN: at least 32 bytes, stored as a secret.
- CLIP_MODEL_ID: defaults to openai/clip-vit-base-patch32.
- CLIP_MODEL_REVISION: exact 40-character Hugging Face commit SHA, not main or another mutable ref.
- POSE_LANDMARKER_MODEL_PATH: path to a provisioned MediaPipe Pose Landmarker model bundle.
- POSE_LANDMARKER_MODEL_SHA256: expected SHA-256 of that exact bundle.
- COMMERCE_API_URL: trusted HTTPS base URL for the Cirvanna Commerce service.
- CATALOG_API_URL and CATALOG_API_TOKEN (or CATALOG_READ_TOKEN): trusted Catalog URL and read-only token. The batch-read endpoint returns active product descriptions and attributes for retrieval.
- Provide a persistent HF model cache/volume or pre-fetch the exact CLIP model revision during the image build. Do not silently fall back to mutable model revisions.

Build using services/vision-intelligence/Dockerfile. The service should remain on a private network with bounded concurrency, rate limiting, timeouts, request-size limits, GPU/CPU resource limits and redacted operational logs. No user images, private assets, or model weights belong in the source repository.

## Model and quality boundaries

CLIP is used for relative retrieval only. Scores are not probabilities, and output ordering is not a CAL/CaTaCaCi display authorization. A downstream consumer must still enforce NPL, explicit cultural requirements and CAL. A lack of catalog metadata or a model error fails closed rather than inventing a hit.

MediaPipe Pose Landmarker returns approximate body landmarks. This initial Virtual Twin inference result is explicitly typed as 3D pose skeleton; it is not a reconstructed body surface. Do not infer body circumference, clothing fit, health status, ethnicity, religion or other sensitive characteristics from it.

Before enabling public use, pin and verify the CLIP commit and pose asset checksum, review licenses, configure the real identity/consent integration, and evaluate retrieval precision/recall, no-match behavior, capture-quality thresholds, diverse lighting/skin tones/body types, end-to-end latency and service recovery against a labeled holdout. Automated mock tests do not establish model accuracy or production readiness.
