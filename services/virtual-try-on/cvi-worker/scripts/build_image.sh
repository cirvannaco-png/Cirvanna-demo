#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
CUDA_BASE_IMAGE="\${CUDA_BASE_IMAGE:?Set CUDA_BASE_IMAGE to an immutable nvidia/cuda@sha256 digest}"
IMAGE_TAG="\${IMAGE_TAG:?Set IMAGE_TAG to the intended image tag}"

if [[ ! "$CUDA_BASE_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]]; then
  echo "CUDA_BASE_IMAGE must be pinned by sha256 digest" >&2
  exit 2
fi

CONTEXT="$(mktemp -d)"
trap 'rm -rf "$CONTEXT"' EXIT
cp -R "$ROOT/services/virtual-try-on/cvi-worker/app" "$CONTEXT/app"
cp "$ROOT/services/virtual-try-on/cvi-worker/requirements.txt" "$CONTEXT/requirements.txt"
cp "$ROOT/services/virtual-try-on/cvi-worker/Dockerfile" "$CONTEXT/Dockerfile"
cp "$ROOT/tools/model_training/virtual_try_on/model.py" "$CONTEXT/model.py"

docker build \
  --build-arg "CUDA_BASE_IMAGE=$CUDA_BASE_IMAGE" \
  --tag "$IMAGE_TAG" \
  "$CONTEXT"

docker image inspect "$IMAGE_TAG" --format '{{.Id}}'
