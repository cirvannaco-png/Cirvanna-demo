# Cirvanna Visual Model Training Runtime

A first-party CUDA-enabled training/evaluation environment for Cirvanna-owned Twin geometry, Try-On, Click It and Look It pipelines. It contains PyTorch/TorchVision CUDA wheels and pinned image/data libraries; it contains no pretrained model weights or datasets.

## Build

The base is the NVIDIA CUDA 12.4.1 cuDNN runtime image pinned to its multi-platform OCI index digest. The build script rejects mutable tags.

    CUDA_BASE_IMAGE=nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04@sha256:2fcc4280646484290cc50dce5e65f388dd04352b07cbe89a635703bd1f9aedb6 \
    IMAGE_TAG=cirvanna-visual-model-training:ci \
    bash services/visual-model-training-runtime/build_image.sh

## Run a controlled training job

Mount the repository read-only at /workspace/source, approved dataset media/manifests read-only at /data, and a private owner-writable results volume at /output. Keep the repository .git directory mounted so each report binds the exact clean source revision. The entrypoint marks only this mount as a Git safe directory.

    docker run --rm --gpus all --network none --read-only \
      --tmpfs /tmp:rw,noexec,nosuid,size=1g \
      -v /path/to/Cirvanna-demo:/workspace/source:ro \
      -v /restricted/cvi-datasets:/data:ro \
      -v /restricted/cvi-runs/run-001:/output:rw \
      cirvanna-visual-model-training:approved \
      python3.10 tools/model_training/virtual_try_on/train_warp_net.py \
        --manifest /data/try-on/dataset.manifest.json \
        --annotations /data/try-on/annotations.jsonl \
        --media-root /data/try-on/media \
        --person-rights-manifest /data/try-on/person-rights.manifest.json \
        --garment-rights-manifest /data/try-on/garment-rights.manifest.json \
        --output-dir /output --device cuda

The same image can run Twin shape-model training, Click It retrieval training, Look It detector training and the independent evaluation CLIs. Never place private source images, annotations, rights evidence, checkpoints or evaluation outputs in Git. Use a separate run directory for each immutable experiment.

This is a reproducible runtime foundation only. No approved training corpora or attached NVIDIA GPU are available in the current execution environment, so no model has been trained or qualified. GPU provisioning and paid compute require explicit budget approval.
