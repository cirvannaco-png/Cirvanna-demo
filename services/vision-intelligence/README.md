# Vision Intelligence service

## Status and release boundary

This service implements guarded inference APIs for image-to-live-offer retrieval and a partial MediaPipe 3D pose skeleton. It is **not production-validated**. The repository does not prove that the pinned CLIP weights have been downloaded, that a checksummed Pose Landmarker asset is provisioned, or that a CUDA-compatible GPU is attached to a live deployment. Unit tests mock model inference; they do not demonstrate live model quality, throughput, or GPU execution.

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

## Live catalog contracts

The service reads `GET {COMMERCE_API_URL}/marketplace/offers?offset=0&limit=100`. Commerce returns `items`, `total`, `offset`, `limit`; offer rows include `variant_id`, `catalog_product_id`, `product_name`, `category`, `options`, `available_stock`. Commerce itself filters inactive offers/variants, unapproved merchants and zero available stock.

The service enriches canonical product IDs with authenticated `GET {CATALOG_API_URL}/products/batch?ids=<uuid>&ids=<uuid>`, using `CATALOG_API_TOKEN` or `CATALOG_READ_TOKEN`. The catalog response is `{ "items": [ProductOut, ...] }`; active products include `product_id`, `name`, `description`, `category`, `brand`, `attributes`, `image_urls`, and `status`. Unknown/archived catalog products are omitted. The batch limit is 100 UUIDs per request. The adapter fails closed on missing/malformed enrichment rather than silently degrading to title-only search.

## Required validation before production

1. Run service unit/contract tests and repository CI.
2. Run integration tests against the real Commerce and Catalog APIs, including pagination, empty catalog, archived product omission, inventory depletion, upstream timeouts, invalid UUIDs, and malformed responses.
3. Provision and verify the exact model assets and runtime; record weight hashes, model revisions, device/runtime versions and inference smoke-test output.
4. Evaluate image-quality thresholds on labeled images and retrieval using top-k recall, precision, score/margin distributions, and subgroup error rates. Do not present a match threshold as confidence until calibrated and independently validated.
5. Keep durable consent verification, Twin ownership, no-store response headers, and CAL/NPL/cultural hard-veto integration as release gates.


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
