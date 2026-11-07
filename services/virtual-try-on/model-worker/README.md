# Private Virtual Try-On GPU worker

**Status:** inference boundary and mock-tested rendering contract implemented. Real model inference is not yet verified or deployed.

This is a private service. It accepts multipart image bytes only from the trusted orchestration layer, requires a worker bearer token and two consent assertion flags, validates decodable image content/dimensions, maps categories explicitly, invokes the pinned FASHN VTON pipeline, validates the encoded output, and returns PNG bytes with `Cache-Control: no-store`. It never accepts URLs and does not persist input/output images. The worker does not verify a consent receipt: its multipart flags are assertions from the trusted orchestrator, not proof of consent. The orchestrator must verify current, resource-bound consent and asset ownership before calling this worker, then persist the result under an opaque asset ID after validating it. Revocation must block new renders and access to prior outputs.

## Category mapping

| Cirvanna category | FASHN category |
| --- | --- |
| `upper_body`, `outerwear` | `tops` |
| `lower_body` | `bottoms` |
| `dress`, `full_outfit` | `one-pieces` |

Unsupported values are rejected by the request schema; no silent category fallback is used.

## Configuration and release requirements

- `VTON_WORKER_TOKEN`: internal bearer token of at least 32 bytes.
- `FASHN_VTON_SOURCE_REF`: must equal the reviewed upstream commit `7c0f10af3f91ad4048fe9729c470a13ef905d25a`.
- `FASHN_VTON_WEIGHTS_DIR`: mounted model-weight directory containing non-empty `model.safetensors`, `dwpose/yolox_l.onnx`, and `dwpose/dw-ll_ucoco_384.onnx`.
- `HF_HOME`: pre-provisioned cache containing the FASHN Human Parser model; the worker forces Hugging Face/Transformers offline mode.
- NVIDIA CUDA, PyTorch CUDA, ONNX Runtime CUDA provider, parser cache, all required model files and successful full model initialization must be present before readiness succeeds.

Build from the repository root only after verifying the upstream source commit and dependency licenses:

```sh
docker build -f services/virtual-try-on/model-worker/Dockerfile \
  --build-arg FASHN_VTON_GIT_REF=<verified-40-character-commit> \
  -t cirvanna-vton-gpu-worker .
```

Mount weights from a controlled model artifact store; do not bake private/user assets or model weights into source control. The build intentionally fails if the source revision is missing or mutable. Review the upstream model and every transitive dependency's licensing, including the human-parser package, before distribution or commercial deployment.

## API

- `GET /health`: process liveness only.
- `GET /ready`: 503 unless token, exact allowlisted source pin, all core model files, CUDA + ONNX CUDA provider, parser cache and successful model initialization are available.
- `GET /capabilities`: describes supported categories, no-persistence behavior, and explicitly states that consent is not independently verified by the worker.
- `POST /v1/render`: authenticated multipart person/garment images, category and both explicit consent flags; returns validated `image/png`.

This worker is not exposed to the public internet. It must be deployed on a private network with bounded concurrency, request-size limits at ingress, rate limits, timeouts, ephemeral storage, and no image-payload logging. Do not treat worker consent booleans as the authoritative consent record.

## Validation

```sh
python -m pip install -r services/virtual-try-on/model-worker/requirements.txt
cd services/virtual-try-on/model-worker
python -m pytest -q
```

CI uses a mock pipeline and does not install PyTorch, download weights, or claim image quality. The FASHN Human Parser package states that its model inherits the NVIDIA Source Code License for SegFormer; legal review is a hard commercial-release gate. Do not assume the whole pipeline is Apache-2.0 because the primary VTON model and DWPose are. Before commercial rendering, clear every dependency license, test the actual pinned pipeline against a consented evaluation set covering diverse body types, skin tones, garment categories, occlusions and difficult poses; inspect artifact leakage; measure latency, VRAM, cost, failure rate and output quality; then connect the orchestrator's real consent/asset/storage adapters. A successful mock test is not evidence of real inference quality.
