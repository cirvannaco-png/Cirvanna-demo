# Private Virtual Try-On GPU worker

**Status:** inference boundary and mock-tested rendering contract implemented. Artifact provenance and model-load readiness are now enforced. Real model inference is not yet verified or deployed. Commercial release is blocked by the human-parser model license until NVIDIA grants suitable written rights or the parser is replaced.

This is a private service. It accepts multipart image bytes only from the trusted orchestration layer, requires a worker bearer token and both consent scopes, validates decodable image content/dimensions, maps categories explicitly, invokes the pinned FASHN VTON pipeline, validates the encoded output, and returns PNG bytes with `Cache-Control: no-store`. It never accepts URLs, does not persist input/output images, and does not decide whether the subject is authorized to use either asset. The orchestrator must verify server-side consent and asset ownership before calling this worker and must persist the result under an opaque asset ID after validating it.

## Category mapping

| Cirvanna category | FASHN category |
| --- | --- |
| `upper_body`, `outerwear` | `tops` |
| `lower_body` | `bottoms` |
| `dress`, `full_outfit` | `one-pieces` |

Unsupported values are rejected by the request schema; no silent category fallback is used.

## Configuration and release requirements

- `VTON_WORKER_TOKEN`: internal bearer token of at least 32 bytes.
- `FASHN_VTON_SOURCE_REF`: exact 40-character upstream Git commit SHA.
- `FASHN_VTON_WEIGHTS_DIR`: mounted model-weight directory.
- NVIDIA CUDA runtime, compatible GPU, pinned model code and required weights must all be present before readiness succeeds.

Build from the repository root only after verifying the upstream source commit and dependency licenses:

```sh
docker build -f services/virtual-try-on/model-worker/Dockerfile \
  --build-arg FASHN_VTON_GIT_REF=<verified-40-character-commit> \
  -t cirvanna-vton-gpu-worker .
```

Mount weights from a controlled model artifact store; do not bake private/user assets or model weights into source control. After downloading the pinned FASHN and DWPose artifacts into the mounted directory, generate the manifest:

```sh
python services/virtual-try-on/model-worker/scripts/build_artifact_manifest.py \\
  --weights-dir /path/to/fashn-vton-1.5 \\
  --source-commit 7c0f10af3f91ad4048fe9729c470a13ef905d25a
```

The worker verifies SHA-256 for all three core files, requires the manifest to name the same source commit as the built image, and loads the actual pipeline during readiness. This does not yet pin or checksum the human-parser's auto-downloaded Hugging Face cache; that remains a separate release gate. The build intentionally fails if the source revision is missing or mutable.

**Commercial license blocker:** the FASHN human-parser README states that its model inherits the NVIDIA SegFormer license and is for non-commercial research/evaluation only. Cirvanna is a commercial product, so do not deploy this stack for production or customer-facing inference without written NVIDIA commercial permission or a replacement parser whose model weights and code are cleared for commercial use. The readiness gate defaults to blocking production. See ADR-0011.

## API

- `GET /health`: process liveness only.
- `GET /ready`: 503 unless token, matching built/runtime source pins, source-bound artifact manifest, verified model weights, CUDA, successful model load, and production license gate are satisfied.
- `GET /capabilities`: describes supported categories and no-persistence behavior.
- `POST /v1/render`: authenticated multipart person/garment images, category and both explicit consent flags; returns validated `image/png`.

This worker is not exposed to the public internet. It must be deployed on a private network with bounded concurrency, request-size limits at ingress, rate limits, timeouts, ephemeral storage, and no image-payload logging. Do not treat worker consent booleans as the authoritative consent record.

## Validation

```sh
python -m pip install -r services/virtual-try-on/model-worker/requirements.txt
cd services/virtual-try-on/model-worker
python -m pytest -q
```

CI uses a mock pipeline and does not install PyTorch, download weights, or claim image quality. Artifact-manifest unit tests verify missing, tampered and mismatched artifacts; only a real GPU load and inference test proves actual model operation. Before enabling rendering, test the actual pinned pipeline against a consented evaluation set covering diverse body types, skin tones, garment categories, occlusions and difficult poses; inspect artifact leakage; measure latency, VRAM, cost, failure rate and output quality; then connect the orchestrator's real consent/asset/storage adapters. A successful mock test is not evidence of real inference quality.
