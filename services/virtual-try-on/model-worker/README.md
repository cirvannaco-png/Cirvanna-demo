# Private Virtual Try-On GPU worker

**Status:** private worker contract and source/artifact/GPU-readiness gates are implemented and mock-tested. The exact upstream checkout, required weight manifest, CUDA/VRAM and ONNX CUDA provider are checked before the full model pipeline is loaded. Real weights/GPU inference, image-quality validation and deployment remain unverified. Commercial use remains blocked until the human-parser and all transitive model licenses are cleared.

This is a private inference worker, not a consent authority or public API. It accepts multipart image bytes only from the authenticated orchestration service, requires a worker bearer token, validates image content/dimensions, maps categories explicitly, invokes the pinned FASHN VTON pipeline and returns validated PNG bytes with `Cache-Control: no-store`. It does not accept URLs or persist input/output images. The worker deliberately does not accept browser-supplied consent booleans: the orchestrator must verify active, purpose-specific, resource-bound consent and asset ownership before calling it, then persist the validated output under an opaque asset ID. Private-network policy must restrict access to the orchestrator.

## Category mapping

| Cirvanna category | FASHN category |
| --- | --- |
| `upper_body`, `outerwear` | `tops` |
| `lower_body` | `bottoms` |
| `dress`, `full_outfit` | `one-pieces` |

Unsupported values are rejected by the request schema; no silent category fallback is used.

## Configuration and release requirements

- `VTON_WORKER_TOKEN`: internal bearer token of at least 32 bytes.
- `FASHN_VTON_SOURCE_REF`: exact reviewed upstream commit `7c0f10af3f91ad4048fe9729c470a13ef905d25a`.
- `FASHN_VTON_BUILT_SOURCE_REF`: source commit embedded at image build time; must equal the reviewed pin.
- `FASHN_VTON_SOURCE_DIR`: actual detached Git checkout; runtime verifies `git rev-parse HEAD` equals the pin.
- `FASHN_VTON_WEIGHTS_DIR`: mounted model-weight directory with the source-bound SHA-256 manifest.
- `HF_HOME`: private persistent parser/model cache. `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` prevent runtime model downloads.
- NVIDIA CUDA runtime, CUDA execution provider for ONNX Runtime, at least 8 GiB VRAM, exact source checkout and non-empty model/DWPose artifacts are required.

Build from the repository root only after verifying the upstream source commit and dependency licenses:

```sh
docker build -f services/virtual-try-on/model-worker/Dockerfile \
  --build-arg FASHN_VTON_GIT_REF=7c0f10af3f91ad4048fe9729c470a13ef905d25a \
  -t cirvanna-vton-gpu-worker .
```

Mount weights from a controlled model artifact store; do not bake private/user assets or model weights into source control. After downloading the pinned FASHN and DWPose artifacts into the mounted directory, generate the manifest:

```sh
python services/virtual-try-on/model-worker/scripts/build_artifact_manifest.py \
  --weights-dir /path/to/fashn-vton-1.5 \
  --source-commit 7c0f10af3f91ad4048fe9729c470a13ef905d25a
```

The worker verifies SHA-256 for all three core model/DWPose files and binds the manifest to the reviewed source commit. Readiness also verifies the actual detached checkout, the CUDA provider, at least 8 GiB device memory and successful initialization of the full pipeline. The human-parser cache must be provisioned into the private `HF_HOME` volume before launch; offline mode makes missing cache files fail readiness rather than download mutable artifacts at runtime. The parser/model cache itself still needs an immutable revision/hash inventory.

**Commercial license blocker:** the FASHN human-parser README states that its model inherits the NVIDIA SegFormer license and is for non-commercial research/evaluation only. Cirvanna is a commercial product, so do not deploy this stack for production or customer-facing inference without written NVIDIA commercial permission or a replacement parser whose model weights and code are cleared for commercial use. The readiness gate defaults to blocking production. See ADR-0011.

## API

- `GET /health`: process liveness only.
- `GET /ready`: 503 unless token, exact built/runtime/source checkout pins, source-bound artifact manifest, required model/DWPose files, CUDA + CUDA ONNX provider, at least 8 GiB VRAM, pre-provisioned offline parser cache, successful full pipeline load and production license gate are satisfied.
- `GET /capabilities`: describes supported categories and no-persistence behavior.
- `POST /v1/render`: authenticated multipart person/garment images, category and `garment_photo_type` (`model` or `flat-lay`, default `flat-lay`); no consent booleans are accepted or trusted. The worker serializes GPU inference and returns retryable `429 GPU_WORKER_BUSY` when occupied.

The worker must never be exposed to the public internet. Deploy it on a private network reachable only from the trusted orchestrator, with request-size limits at ingress, rate limits, timeouts, one active render per worker, ephemeral storage and no image-payload logging. Consent is verified by the orchestrator, not by worker form fields.

## Validation

```sh
python -m pip install -r services/virtual-try-on/model-worker/requirements.txt
cd services/virtual-try-on/model-worker
python -m pytest -q
```

CI uses a mock pipeline and does not install PyTorch, download weights, or claim image quality. Artifact-manifest unit tests verify missing, tampered and mismatched artifacts; only a real GPU load and inference test proves actual model operation. Before enabling rendering, test the actual pinned pipeline against a consented evaluation set covering diverse body types, skin tones, garment categories, occlusions and difficult poses; inspect artifact leakage; measure latency, VRAM, cost, failure rate and output quality; then connect the orchestrator's real consent/asset/storage adapters. A successful mock test is not evidence of real inference quality.
