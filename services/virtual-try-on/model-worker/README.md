# Private Virtual Try-On GPU worker

**Status:** private inference boundary implemented; real GPU inference is not yet provisioned, quality-validated or deployed.

This service is an internal inference worker, not a consent authority or public API. It accepts multipart image bytes only from the trusted orchestration layer, requires a worker bearer token, validates decodable image content/dimensions, maps categories explicitly, invokes the pinned FASHN VTON pipeline, validates the encoded output, and returns PNG bytes with `Cache-Control: no-store`. It never accepts URLs and does not persist input/output images.

**Consent boundary:** the worker does not independently verify user consent. The authenticated orchestration service must verify an active, purpose-specific, revocable server-side consent receipt and asset ownership before calling the worker. The worker deliberately does not accept client-submitted consent booleans; those are not proof of consent. Network policy must make the worker reachable only from the orchestration service. The orchestration API remains disabled until its real consent, asset authorization, idempotency and output-storage adapters are integrated.

## Category mapping

| Cirvanna category | FASHN category |
| --- | --- |
| `upper_body`, `outerwear` | `tops` |
| `lower_body` | `bottoms` |
| `dress`, `full_outfit` | `one-pieces` |

The worker accepts `garment_photo_type=model` or `flat-lay`; it defaults to `flat-lay` because marketplace product photography is commonly flat-lay or isolated product imagery. The orchestrator should send the correct type when it knows the source is a model-worn garment image. Unsupported categories are rejected.

## Pinned source

The reviewed upstream source commit is:

`7c0f10af3f91ad4048fe9729c470a13ef905d25a`

The container clones this exact commit, checks out detached HEAD, verifies `git rev-parse HEAD`, and installs the package from that checkout. Runtime readiness repeats the SHA comparison against the actual checkout; a syntactically valid but different SHA is not accepted.

## Configuration and readiness

- `VTON_WORKER_TOKEN`: internal bearer token of at least 32 bytes.
- `FASHN_VTON_SOURCE_REF`: exact 40-character upstream Git commit SHA.
- `FASHN_VTON_SOURCE_DIR`: checkout path; the container sets this to `/opt/fashn-vton`.
- `FASHN_VTON_WEIGHTS_DIR`: mounted model-weight directory; the container sets this to `/models/fashn-vton-1.5`.
- `HF_HOME`: persistent, access-controlled Hugging Face cache; the container sets this to `/models/hf-cache`.

Readiness now requires:
1. worker authentication configured;
2. actual Git checkout HEAD equal to the configured source SHA;
3. non-empty `model.safetensors`, `dwpose/yolox_l.onnx`, and `dwpose/dw-ll_ucoco_384.onnx` files;
4. CUDA available with at least 8 GiB reported device memory; and
5. successful construction of the full upstream pipeline, which loads the TryOn model, DWPose and FASHN Human Parser.

A model directory existing is not enough. The model files must be provisioned before readiness can pass. The current upstream provisioning script downloads model files from Hugging Face; do not use an unpinned `main` revision for production. Model and DWPose artifact revisions/checksums still need a separately reviewed immutable artifact manifest before production release.

## Build

Build from the repository root with the reviewed upstream source pin:

```sh
docker build -f services/virtual-try-on/model-worker/Dockerfile \
  --build-arg FASHN_VTON_GIT_REF=7c0f10af3f91ad4048fe9729c470a13ef905d25a \
  -t cirvanna-vton-gpu-worker .
```

The image contains the pinned inference code but does not download or bake the approximately 2 GB model weights into the image. Provision model artifacts into a persistent, private volume from a controlled artifact workflow. Do not commit model weights or user assets to Git.

## API

- `GET /health`: process liveness only.
- `GET /ready`: 503 until the exact source checkout, required weights, CUDA and all pipeline components load successfully.
- `GET /capabilities`: reports categories, no-persistence behavior and the fact that consent is an upstream orchestration responsibility.
- `POST /v1/render`: authenticated multipart person/garment images, category and garment photo type; returns validated `image/png`.

The worker must not be exposed to the public internet. Deploy it on a private network with bounded GPU concurrency (the worker serializes inference), request-size limits at ingress, rate limits, timeouts, ephemeral processing, and no image-payload logging. The output is not persisted here; the orchestrator must validate and store it under an opaque asset ID before returning a completed try-on to a user.

## Licensing and model quality gates

The FASHN VTON v1.5 source/model repository is Apache-2.0. The upstream dependency list also includes `fashn-human-parser`; Hugging Face metadata currently labels that model license as `other`, not Apache-2.0. Commercial use must remain blocked pending review of the parser's actual license and terms, plus a complete third-party license inventory. Do not infer that the whole dependency stack is Apache-2.0 because the primary model is.

The upstream model is a visual preview generator, not a fit engine. It supports `tops`, `bottoms`, and `one-pieces`; upstream materials disclose failure modes such as garment traces during bulky-to-slim transformations and imperfect body-shape preservation. Do not describe the output as a fit guarantee, accurate measurement, fabric simulation or purchase-certainty score.

## Validation

```sh
python -m pip install -r services/virtual-try-on/model-worker/requirements.txt
cd services/virtual-try-on/model-worker
python -m pytest -q
```

CI uses a mock pipeline and does not install PyTorch, download weights, or establish image quality. Passing tests validate the API contract only. Before enabling real user traffic, complete:
- immutable revisions and checksums for model, DWPose and parser artifacts;
- parser and full dependency license review;
- actual GPU inference using consented, rights-cleared evaluation images;
- quality evaluation across body shapes, skin tones, poses, occlusions and garment types;
- output artifact leakage and privacy testing;
- latency, VRAM, cost, failure-rate and concurrency benchmarks;
- orchestration integration for server-side consent, cross-user asset authorization, idempotent jobs, output persistence and revocation/deletion;
- end-to-end staging verification and security review.
