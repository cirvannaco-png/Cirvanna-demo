# CVI private Virtual Try-On GPU worker

This is the private inference worker for Cirvanna's own warp-and-refine U-Net candidate. It does not download or load FASHN, IDM-VTON, CatVTON or any other third-party Try-On checkpoint.

## Release-gated readiness

The worker intentionally remains unready unless all of these are present and valid:
- A model bundle containing the exact checkpoint, training report, independent evaluation report, dataset manifest and separate person/garment rights manifests.
- SHA-256 matches for every artifact.
- A full 40-character source revision and a pinned runtime container image digest.
- A valid Ed25519 qualification signature from the independently controlled qualification key. The signed payload binds model ID, architecture, weights, training/evaluation evidence, rights, runtime image, input contract and GPU resource limits.
- A valid CUDA device with at least the signed minimum GPU memory.
- Worker bearer token and separate privacy-governance Ed25519 public key.

build_artifact_manifest.py only assembles an unsigned, digest-bound bundle. It does not qualify or enable a model. An independent reviewer must verify the held-out quality report, licensing/rights, privacy, resource and deletion evidence, then sign the canonical manifest payload using a key that is not stored in this repository. The signed qualification attestation is time-bounded to a maximum of 90 days. The worker rejects missing, expired, altered or unqualified manifests.

## Build the immutable GPU image

The build script requires a CUDA base image pinned by digest and creates a minimal temporary context containing only the worker code and the exact shared model definition:

    CUDA_BASE_IMAGE='nvidia/cuda@sha256:REPLACE_WITH_VERIFIED_DIGEST' \
    IMAGE_TAG='registry.example/cirvanna/cvi-tryon-worker:research' \
    bash services/virtual-try-on/cvi-worker/scripts/build_image.sh

After pushing, use the registry's immutable image digest as CVI_VTON_RUNTIME_IMAGE_DIGEST and include it in the signed model manifest. The Docker image pins PyTorch 2.6.0 for CUDA 12.4 and the Python runtime dependencies. Docker is not available in the current development environment, so no container build has been run.

## Assemble a model bundle

The expected bundle directory contains:
- model.pt
- training-report.json
- evaluation-report.json
- dataset.manifest.json
- person-rights.manifest.json
- garment-rights.manifest.json
- manifest.json

    python services/virtual-try-on/cvi-worker/scripts/build_artifact_manifest.py \
      --bundle-dir /restricted/cvi-tryon/bundle \
      --checkpoint /restricted/cvi-tryon/run/cvi-tryon-warp-net-state.pt \
      --training-report /restricted/cvi-tryon/run/training-report.json \
      --evaluation-report /restricted/cvi-tryon/independent-evaluation.json \
      --dataset-manifest /restricted/cvi-tryon/dataset.manifest.json \
      --person-rights-manifest /restricted/cvi-tryon/person-rights.manifest.json \
      --garment-rights-manifest /restricted/cvi-tryon/garment-rights.manifest.json \
      --source-revision REPLACE_WITH_FULL_40_CHAR_COMMIT \
      --runtime-image-digest REPLACE_WITH_REGISTRY_IMAGE_DIGEST

The resulting manifest has qualification_attestation: null; /ready remains HTTP 503 until an independent reviewer signs the exact payload.

## Inference contract

POST /v1/render is internal-only and requires:
- bearer authentication;
- source person and catalogue garment images;
- corresponding grayscale person and garment masks;
- 17-channel 64x64 pose heatmap;
- preprocessing manifest digest;
- one-time Ed25519 privacy attestation signed by consent/CAL governance.

The privacy receipt binds the exact SHA-256 of all submitted assets, a user-binding digest, consent scope/policy version, active consent state, revocation epoch, face-masking declarations and a short expiry (maximum 30 seconds). Receipt IDs are one-time and replay is rejected. The orchestrator must recheck current CAL consent/revocation immediately before issuing the receipt; the worker validates the signed snapshot and its short lifetime.

The worker accepts no remote image URLs and performs no face recognition. It does not decide consent itself.

## Resource and deletion controls

- One inference at a time; no batching.
- 256x256 model input; 60 MiB request-body limit, per-file byte limits and image-pixel limits.
- Signed GPU minimum memory and allocator fraction (maximum 80%).
- No CPU fallback, no network model downloads, no worker egress in the deployment policy.
- Non-root process, read-only root filesystem, read-only model bundle mount, memory-backed /tmp, internal ClusterIP service only.
- Upload spools are closed; in-memory input bytearrays and inference tensors are overwritten/cleared in finally; CUDA cache is released; output is returned with Cache-Control: no-store and is not written to disk.
- The worker does not persist source or output images. The orchestrator owns any separately consented persistence and must propagate revocation/deletion through its own asset registry and caches.

Memory overwriting and torch.cuda.empty_cache() are best-effort process hygiene, not a forensic guarantee that every allocator/driver copy has been physically erased. Independent privacy testing must verify the actual deployment and deletion path.

## Deployment

deploy/gpu-worker.yaml is a Kubernetes deployment template for one private NVIDIA GPU worker, 16–24 GiB RAM, 4–8 CPU cores, a read-only model bundle volume, in-memory temporary uploads, a single-replica replay ledger and ingress restricted to the Virtual Try-On orchestrator. Replace all image digests, PVC names, namespace and Kubernetes Secrets with approved values before deployment.

No GPU provider has been selected or paid provisioning authorized. No GPU worker has been deployed, no trained checkpoint exists, and no real inference or image-quality evaluation has been performed. The worker cannot become ready without the independent signed qualification bundle.
