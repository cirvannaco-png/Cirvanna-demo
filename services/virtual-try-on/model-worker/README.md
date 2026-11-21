# Private Virtual Try-On GPU worker

**Status:** private worker contract and source/artifact/GPU-readiness gates are implemented and mock-tested. The first commercially safer inference mode is restricted to segmentation-free person images plus flat-lay garment images. The separately licensed FASHN Human Parser dependency is removed from the production image and replaced with a local no-op interface shim; the supported preprocessing path does not use parser masks. Real weights/GPU inference, image-quality validation and deployment remain unverified. Model-worn garment photos remain disabled until a separately licensed parser and its weights are cleared.

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
- `FASHN_VTON_PARSER_MODE=maskless_flat_lay`: the only supported production parser mode. The worker does not install `fashn-human-parser`; a local no-op compatibility shim is used only because both person and garment preprocessing are explicitly maskless. `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` prevent runtime model downloads.
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

The worker verifies SHA-256 for all three core model/DWPose files and binds the manifest to the reviewed source commit. Readiness also verifies the actual detached checkout, the CUDA provider, at least 8 GiB device memory and successful initialization of the full pipeline. The model/DWPose artifacts must be provisioned into the private weights volume and verified against the source-bound SHA-256 manifest. No human-parser weights or cache are loaded in `maskless_flat_lay` mode. This mode is safe only because the worker forces `segmentation_free=True` and rejects every garment photo type except `flat-lay`.

**Input-mode limitation:** this release path supports flat-lay garment images only. The FASHN Human Parser package and its restricted SegFormer weights are not installed or invoked. Do not enable `garment_photo_type=model` or segmentation-based preprocessing with the local shim. A separate parser with verified commercial code, checkpoint and dataset provenance is required before on-model product photos can be supported. See ADR-0011.

## API

- `GET /health`: process liveness only.
- `GET /ready`: 503 unless token, exact built/runtime/source checkout pins, source-bound artifact manifest, required model/DWPose files, CUDA + CUDA ONNX provider, at least 8 GiB VRAM, pre-provisioned offline parser cache, successful full pipeline load and source pin, source-bound artifact manifest, CUDA + CUDA ONNX provider, at least 8 GiB VRAM and successful full pipeline load are satisfied.
- `GET /capabilities`: describes supported categories and no-persistence behavior.
- `POST /v1/render`: authenticated multipart person/garment images, category and `garment_photo_type=flat-lay` only; `model` is rejected with `UNSUPPORTED_GARMENT_PHOTO_TYPE`; no consent booleans are accepted or trusted. The worker serializes GPU inference and returns retryable `429 GPU_WORKER_BUSY` when occupied.

The worker must never be exposed to the public internet. Deploy it on a private network reachable only from the trusted orchestrator, with request-size limits at ingress, rate limits, timeouts, one active render per worker, ephemeral storage and no image-payload logging. Consent is verified by the orchestrator, not by worker form fields.

## Validation

```sh
python -m pip install -r services/virtual-try-on/model-worker/requirements.txt
cd services/virtual-try-on/model-worker
python -m pytest -q
```

CI uses a mock pipeline and does not install PyTorch, download weights, or claim image quality. Artifact-manifest unit tests verify missing, tampered and mismatched artifacts; only a real GPU load and inference test proves actual model operation. Before enabling rendering, test the actual pinned pipeline against a consented evaluation set covering diverse body types, skin tones, garment categories, occlusions and difficult poses; inspect artifact leakage; measure latency, VRAM, cost, failure rate and output quality; then connect the orchestrator's real consent/asset/storage adapters. A successful mock test is not evidence of real inference quality.


## Commercial-safe maskless flat-lay mode

The upstream FASHN VTON pipeline supports `segmentation_free=True` and `garment_photo_type="flat-lay"`. In that combination, its preprocessing helpers pass the person and garment images through without parser masks. This worker therefore removes the restricted `fashn-human-parser` dependency at image build time and supplies a small local interface shim that returns zero masks; the shim is never used to segment an image. The worker forces both flags server-side and rejects model-worn garment photos before inference. This is real FASHN model inference when the pinned model/DWPose artifacts and GPU are present, not a mock renderer.

The current CI tests validate request contracts and mock pipeline behavior only. A real GPU smoke test and human-reviewed quality evaluation are still required. Model-worn product imagery remains unavailable until a commercially licensed parser is selected, pinned, and validated.
