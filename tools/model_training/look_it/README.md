# Look It detector training foundation

The first Cirvanna-owned Look It model candidate is a bounding-box component detector built with a TorchVision Faster R-CNN ResNet-50 FPN architecture. It initializes all weights randomly: it does not download pretrained weights or use a third-party trained detector. The TorchVision library supplies architecture primitives; Cirvanna must own the rights-cleared training data, category taxonomy, training run, checkpoint provenance and evaluation.

## Dataset contract

Each annotation JSONL row contains sample_id, pseudonymous cluster_id, split, relative image_path, image_sha256, width, height, and up to 12 components. Each component has category and normalized bbox [x1,y1,x2,y2]. The dataset manifest binds the exact annotation file digest, rights-manifest digest, sample count, category list and canonical split-manifest digest.

Use train, validation and test splits that are disjoint by person/source cluster and image digest. The validator rejects traversal, symlinks, digest/dimension mismatch, missing splits and cluster leakage. A Look It data-rights manifest must have scope look_it_decomposition_evaluation, explicit commercial-evaluation/human-review permission, retention and verified depicted-person consent where applicable.

## Validate data before training

    python tools/model_training/look_it/validate_dataset.py \
      --manifest /restricted/look-it/dataset.manifest.json \
      --annotations /restricted/look-it/annotations.jsonl \
      --media-root /restricted/look-it/media \
      --rights-manifest /restricted/look-it/data-rights.manifest.json

## Train a research candidate

Use an approved, isolated CUDA training image with a pinned PyTorch/TorchVision lock. This development environment currently has no PyTorch/TorchVision and no visible NVIDIA GPU, so no training run has been executed.

    python tools/model_training/look_it/train_detector.py \
      --manifest /restricted/look-it/dataset.manifest.json \
      --annotations /restricted/look-it/annotations.jsonl \
      --media-root /restricted/look-it/media \
      --rights-manifest /restricted/look-it/data-rights.manifest.json \
      --output-dir /restricted/look-it/run-001 \
      --device cuda --epochs 30 --batch-size 4

The trainer fails rather than silently falling back from CUDA to CPU. It writes a checkpoint and private report with dataset/model/code provenance and loss history. It deliberately does not open held-out test images; it records only the reserved test sample count. The model remains a research candidate until independent held-out evaluation, subgroup analysis, resource profiling, privacy review and signed release attestation pass.

## Run held-out inference and score component extraction

Run the frozen checkpoint on the test split in the exact clean source revision used for training:

    python tools/model_evaluation/look_it_decomposition/predict.py \
      --checkpoint /restricted/look-it/run-001/lookit-detector-state.pt \
      --training-report /restricted/look-it/run-001/training-report.json \
      --manifest /restricted/look-it/dataset.manifest.json \
      --annotations /restricted/look-it/annotations.jsonl \
      --media-root /restricted/look-it/media \
      --rights-manifest /restricted/look-it/data-rights.manifest.json \
      --output /restricted/look-it/run-001/held-out-predictions.jsonl \
      --device cuda

Then score predictions against independently labelled components:

    python tools/model_evaluation/look_it_decomposition/evaluate.py \
      --input /restricted/look-it/run-001/held-out-predictions.jsonl \
      --rights-manifest /restricted/look-it/evaluation-rights.manifest.json \
      --output /restricted/look-it/run-001/held-out-evaluation.json

The evaluator reports per-category precision/recall/F1, IoU-0.5 average precision and mAP, subgroup metrics, and product Recall@K/MRR only when component-to-product ground truth and ranked retrieval evidence are present. Prediction rows bind the checkpoint, training report and source revision. Localization scores do not prove product matching or pixel-mask quality.

## Non-goals

This detector is not a full Look It product by itself. It does not parse garment texture, distinguish all attributes, decompose pixel masks, retrieve marketplace products or establish CAL display authorization. It must abstain when component extraction is ambiguous. Never treat training loss or validation loss as proof of production quality.


## Example templates

- dataset-manifest.example.json shows the required immutable dataset manifest fields.
- annotation-sample.example.jsonl shows the per-image annotation contract.
- data-rights.template.json is deliberately unapproved and cannot pass the rights gate. Replace it only after a responsible data-rights owner has reviewed the source and evidence.

Do not put participant names, emails, faces, raw consent receipts, absolute media paths or image bytes into source control. Use opaque participant/source cluster keys in the restricted evaluation workspace.
