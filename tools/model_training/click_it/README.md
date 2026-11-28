# Click It proprietary image-retrieval training foundation

This is Cirvanna's first candidate fashion-image embedding trainer. It uses a ResNet-50 feature extractor with a Cirvanna projection head, initialized entirely from random weights, and supervised contrastive learning over exact canonical product IDs. TorchVision supplies the architecture implementation; Cirvanna owns the category taxonomy, approved catalogue corpus, training procedure, checkpoint provenance and evaluation.

## Dataset contract

Each JSONL row contains sample_id, product_id, product_family_id, split, image_path, image_sha256, width, height and category. Every product must have multiple distinct image views. Product-family clusters and image digests cannot cross train/validation/test splits. Dataset manifests bind the annotation bytes, split assignment and rights-manifest digest.

The required rights scope is click_it_retrieval_evaluation. The rights manifest must record commercial evaluation and human review permission, provenance, retention expiry, and verified depicted-person consent when personal images are included. Training should begin with rights-cleared catalogue product photography, not arbitrary user uploads.

## Validate

    python tools/model_training/click_it/validate_dataset.py \
      --manifest /restricted/click-it/dataset.manifest.json \
      --annotations /restricted/click-it/annotations.jsonl \
      --media-root /restricted/click-it/media \
      --rights-manifest /restricted/click-it/data-rights.manifest.json

## Train

Use an approved CUDA image with a complete hash-locked PyTorch/TorchVision environment. The current development environment has neither PyTorch/TorchVision nor an attached GPU; no training or inference has been run.

    python tools/model_training/click_it/train_retrieval.py \
      --manifest /restricted/click-it/dataset.manifest.json \
      --annotations /restricted/click-it/annotations.jsonl \
      --media-root /restricted/click-it/media \
      --rights-manifest /restricted/click-it/data-rights.manifest.json \
      --output-dir /restricted/click-it/run-001 \
      --device cuda --epochs 40 --products-per-batch 8 --images-per-product 2

The balanced batch sampler ensures each product contributes positive views while other products provide negatives. The supervised contrastive objective learns a shared image embedding space. The trainer fails if CUDA is requested but unavailable and writes private checkpoint/report artifacts with SHA-256 provenance.

## Evaluation and limits

Use tools/model_evaluation/click_it_image_retrieval/run.py for the separate image-to-image benchmark. It loads the local CVI checkpoint, verifies its training report and exact source revision, embeds query and candidate catalogue images, and scores the fixed candidate pool. The final test must be product-family/source-cluster disjoint, human-labelled, preregistered and never used for training or model selection. Report Recall@K, Precision@K, nDCG@K, MRR, top-1 hit rate, subgroup metrics and operational costs. The first runner does not yet compute cluster-bootstrap intervals or calibrated abstention.

This model is not facial recognition, identity matching or cross-user search. It does not emit calibrated match probabilities. A good contrastive training loss is not proof of retrieval quality; no Click It production route may be enabled from this training scaffold alone.

## Dataset template

- dataset-manifest.example.json shows the immutable dataset fields.
- annotation-sample.example.jsonl shows the per-image product/view record.
- data-rights.template.json is deliberately pending and cannot pass validation. Obtain approval for the exact source corpus and intended commercial evaluation before replacing placeholders.
