#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
if ! printenv CUDA_BASE_IMAGE >/dev/null || ! printenv IMAGE_TAG >/dev/null; then
  echo "Set CUDA_BASE_IMAGE and IMAGE_TAG" >&2
  exit 2
fi
if [[ -z "$CUDA_BASE_IMAGE" || -z "$IMAGE_TAG" ]]; then
  echo "CUDA_BASE_IMAGE and IMAGE_TAG cannot be empty" >&2
  exit 2
fi
if [[ ! "$CUDA_BASE_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]]; then
  echo "CUDA_BASE_IMAGE must be pinned by sha256 digest" >&2
  exit 2
fi
docker build --build-arg "CUDA_BASE_IMAGE=$CUDA_BASE_IMAGE" --tag "$IMAGE_TAG" "$ROOT/services/visual-model-training-runtime"
docker run --rm --entrypoint python3.10 "$IMAGE_TAG" -c 'import torch,torchvision; assert torch.version.cuda=="12.4"; print(torch.__version__,torchvision.__version__,torch.version.cuda)'
docker image inspect "$IMAGE_TAG" --format '{{.Id}}'
