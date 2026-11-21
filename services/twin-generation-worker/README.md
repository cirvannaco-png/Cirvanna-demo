# SAM 3D Body generation worker (research spike)

**Status: research-only. Not production-ready. Not connected to the Twin Registry.**

This worker is a self-hosted inference spike for the SAM 3D Body model. It is deliberately separate from the public Virtual Twin API. It accepts one private full-body image, runs the pinned model in memory, and returns a mesh-only GLB. It does not store the input image, call a hosted inference provider, upload the mesh to Asset Service, or register a Twin.

## Pinned source and model

- Upstream code: `facebookresearch/sam-3d-body`
- Upstream code commit: `b5c765a0d89d789985e186d396315e7590887b94`
- Initial model ID: `facebook/sam-3d-body-dinov3`
- Model weights: gated Hugging Face artifact; the exact 40-character model revision must be supplied at provisioning time.
- Model release: every downloaded file is SHA-256 inventoried in `manifest.json`; the canonical release digest binds the model ID, model revision, source commit and file hashes.
- Model license: the upstream model uses the SAM License. Access and commercial-use terms must be reviewed and accepted before setting the runtime license flags. The worker requires both `SAM3D_BODY_LICENSE_ACCEPTED=true` and a non-empty `SAM3D_BODY_LICENSE_EVIDENCE_ID`.

The source commit and model-weight revision are separate identifiers. Do not substitute a floating `main` branch or unpinned Hugging Face revision.

## Provision gated model artifacts

1. Review the current model card and license terms, request gated model access, and record the approved license evidence.
2. Create an isolated provisioning environment and install `scripts/requirements-provision.txt`.
3. Set `HF_TOKEN` as a secret environment variable. Never commit it or print it.
4. Run:

```bash
export SAM3D_BODY_MODEL_ID=facebook/sam-3d-body-dinov3
export SAM3D_BODY_MODEL_REVISION=<full-40-character-hugging-face-commit>
export SAM3D_BODY_LICENSE_ACCEPTED=true
export SAM3D_BODY_LICENSE_EVIDENCE_ID=<approved-evidence-reference>
python scripts/provision_model.py --output /secure/model-volume/sam3d-body
```

The provisioning script downloads only the exact requested model revision, verifies the required checkpoint/config/MHR files exist, hashes every downloaded file, and writes a canonical manifest. Mount the resulting directory read-only at `/models/sam3d-body` in the worker.

The default file names are `model.ckpt`, `model_config.yaml`, and `assets/mhr_model.pt`. If the gated repository uses different paths, pass the corresponding `--checkpoint-file`, `--config-file` and `--mhr-file` arguments and set the same environment variables at runtime.

## Runtime configuration

Required:
- `TWIN_GENERATION_WORKER_TOKEN`: internal bearer token, at least 32 characters.
- `SAM3D_BODY_SOURCE_REF`: must equal the pinned upstream code commit above.
- `SAM3D_BODY_MODEL_ID`: must equal the selected model ID.
- `SAM3D_BODY_MODEL_REVISION`: exact 40-character model revision.
- `SAM3D_BODY_MODEL_RELEASE_SHA256`: canonical release digest printed by the provisioning script.
- `SAM3D_BODY_ARTIFACT_DIR`: mounted model artifact directory.
- `SAM3D_BODY_LICENSE_ACCEPTED=true` and `SAM3D_BODY_LICENSE_EVIDENCE_ID`: only after documented review/acceptance.
- CUDA-enabled GPU. Default minimum VRAM is 16 GiB; set `SAM3D_BODY_MIN_GPU_VRAM_GIB` only after measured capacity testing.

The worker hashes the complete model artifact manifest during readiness evaluation. Configuration changes require a worker restart.

## Internal API

- `GET /health`: liveness only; does not imply model readiness.
- `GET /ready`: returns 200 only after source pin, license evidence, model manifest, CUDA/VRAM and model initialization pass.
- `GET /capabilities`: reports generation availability and explicitly reports `measurement_calibrated=false` and `registry_persistence_enabled=false`.
- `POST /internal/v1/reconstruct`: internal bearer-authenticated multipart request with `source_asset_id`, `consent_id`, `single_person_confirmed=true` and one image.

The worker does not independently verify consent or asset ownership. Only the trusted Virtual Twin orchestrator may call it after verifying the canonical consent receipt and private source asset authorization. The source asset and consent IDs are opaque correlation values; they are not written into model artifacts or logs.

The input must be a single-person full-body JPEG, PNG or WebP image. The first spike uses the upstream estimator without an external person detector, segmentor or FOV provider. The caller therefore has to attest that one person is present; this is not an automated multi-person safety detector.

## Output and limitations

The response is a mesh-only GLB with no source-photo texture. It includes model/code revisions, release digest, artifact digest and job metadata in response headers.

**The worker never claims calibrated body measurements.** SAM 3D Body's single-view output and default FOV are not an independent measurement reference. The output is marked `X-Twin-Measurement-Status: not_calibrated` and `X-Twin-Registry-Eligible: false`.

Do not use this mesh for size recommendations, fit guarantees, body measurements, public sharing or persistent Twin registration. Do not connect this worker to Twin Registry until all of the following have independently passed:

1. Real GPU inference smoke test on the pinned source and model artifacts.
2. GLB validation through the independent Twin Mesh Validator, including full-body coverage, coordinate scale, topology, non-finite geometry and no embedded source imagery.
3. Consent/revocation and private Asset Service integration, with deletion verified end-to-end.
4. Human-reviewed real-person evaluation against manual measurements across representative body shapes and capture conditions. Measurement acceptance thresholds must be pre-registered; model output must not be treated as ground truth.
5. Privacy review and model/dependency SBOM/license approval.

## Research image

`Dockerfile.research` is intentionally not part of the standard production image build matrix. It is an experimental GPU build recipe and must not be deployed as a production service without a fully locked dependency/SBOM review, reproducible build, GPU smoke test and the gates above.
