# Cirvanna Virtual Try-On warp-and-refine training foundation

This is the first Cirvanna-owned Try-On neural candidate. It is a custom U-Net conditioned on the source person image, target garment image, person/garment masks and 17-channel pose heatmaps. It predicts a garment sampling flow, garment blend mask and a small image-refinement residual. The garment is warped with grid sampling before the final compositing step.

The network is randomly initialized. It does not use a third-party trained Try-On model, diffusion checkpoint or pretrained perceptual backbone. PyTorch supplies tensor/optimization primitives only.

## Dataset contract

Each JSONL sample binds:
- source person image and a distinct target-worn image;
- catalogue garment image;
- person, garment and target garment masks;
- 17-channel 64x64 pose heatmap;
- subject cluster, garment product/family, split, subgroup labels and preprocessing digest.

The dataset requires separate person/target rights and garment catalogue rights manifests, both under virtual_try_on_training. Person imagery requires verified subject consent. Catalogue images depicting people also require verified model consent. Every sample must declare face masking before training for both person and garment images. Subject clusters and garment-family clusters must be disjoint across train/validation/test.

## Validate the corpus

    python tools/model_training/virtual_try_on/validate_dataset.py \
      --manifest /restricted/try-on/dataset.manifest.json \
      --annotations /restricted/try-on/annotations.jsonl \
      --media-root /restricted/try-on/media \
      --person-rights-manifest /restricted/try-on/person-rights.manifest.json \
      --garment-rights-manifest /restricted/try-on/garment-rights.manifest.json

## Train

Use a pinned CUDA image and an approved isolated GPU worker. The current development environment has no PyTorch or visible NVIDIA GPU, so no neural training or inference has been run.

    python tools/model_training/virtual_try_on/train_warp_net.py \
      --manifest /restricted/try-on/dataset.manifest.json \
      --annotations /restricted/try-on/annotations.jsonl \
      --media-root /restricted/try-on/media \
      --person-rights-manifest /restricted/try-on/person-rights.manifest.json \
      --garment-rights-manifest /restricted/try-on/garment-rights.manifest.json \
      --output-dir /restricted/try-on/run-001 \
      --device cuda --epochs 50 --batch-size 2

The trainer evaluates validation data only. It does not open held-out test images; it records the reserved test sample count and exact dataset/rights digests, code revision, runtime, GPU and peak allocated/reserved training memory. The PyTorch allocator fraction is a soft process limit, not a substitute for container-level GPU isolation.

## Independent held-out evaluation

After the trainer has frozen the checkpoint, evaluate the held-out test split in the exact same clean source revision:

    python tools/model_evaluation/virtual_try_on/evaluate.py \
      --checkpoint /restricted/try-on/run-001/cvi-tryon-warp-net-state.pt \
      --training-report /restricted/try-on/run-001/training-report.json \
      --manifest /restricted/try-on/dataset.manifest.json \
      --annotations /restricted/try-on/annotations.jsonl \
      --media-root /restricted/try-on/media \
      --person-rights-manifest /restricted/try-on/person-rights.manifest.json \
      --garment-rights-manifest /restricted/try-on/garment-rights.manifest.json \
      --output /restricted/try-on/run-001/independent-evaluation.json \
      --device cuda --batch-size 1

The evaluator verifies the checkpoint, source revision, dataset manifest, split and both rights digests before loading only the held-out test samples. It reports image MAE, PSNR, global SSIM, garment-region MAE, alpha-mask IoU, warped-garment-mask IoU, latency, peak GPU memory and subgroup slices. These pixel and mask metrics do not prove garment identity, logo/pattern preservation, realistic drape, occlusion or human preference; those require blinded human review and additional perceptual/garment-specific metrics.

## Important limitations

- This v0 candidate operates at 256x256 and has no diffusion prior, high-resolution refinement or pretrained perceptual representation.
- It does not yet prove garment pattern/logo preservation, garment identity, body-shape fidelity, realistic occlusion, lighting, drape or user-perceived quality.
- Validation losses and pixel metrics are not enough for acceptance. Add garment-specific human review, LPIPS/SSIM, colour/pattern preservation, subgroup confidence intervals, latency, VRAM and failure-rate benchmarks before considering production.
- The model does not implement consent revocation, temporary asset deletion or CDN/cache invalidation. Those remain separate runtime security gates.
- No customer-facing Try-On capability is enabled by this training scaffold.

## Template files

- dataset-manifest.example.json: digest-bound corpus manifest.
- annotation-sample.example.jsonl: one paired person/garment/target record.
- person-rights.template.json: pending subject-consent evidence.
- garment-rights.template.json: pending catalogue-image commercial rights and any depicted-model consent.

The templates are intentionally unapproved and cannot pass the dataset validator until the real source rights and consent have been reviewed.
