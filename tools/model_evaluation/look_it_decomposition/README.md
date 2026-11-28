# Look It component-extraction evaluation

This offline evaluator scores independently annotated outfit-component bounding boxes against model predictions. It is a first localization benchmark, not a full pixel-mask segmentation benchmark and not product-retrieval evaluation.

## Input and rights

One JSONL record per image with sample_id, cluster_id, split, non-empty subgroups, ground_truth_components and predicted_components. Each component has a unique local component_id, normalized category, and normalized [x1,y1,x2,y2] bounding box. Each sample is limited to 12 components. Keep underlying images and annotation records in the approved restricted workspace.

Split by person/source session before annotation and evaluation. Do not allow near-duplicate images or the same photographed person to cross train, calibration and test splits. Use two independent annotators and adjudication for held-out labels.

Use a data-rights manifest with scope look_it_decomposition_evaluation, commercial-evaluation and human-review permission, explicit provenance, unexpired retention, and verified depicted-person consent when personal images are present.

## Run

    python tools/model_evaluation/look_it_decomposition/evaluate.py \
      --input /restricted/look-it/test-predictions.jsonl \
      --rights-manifest /restricted/look-it/data-rights.manifest.json \
      --output /restricted/look-it/component-report.json \
      --iou-threshold 0.5

Outputs are written atomically with owner-only permissions. The report records input and rights-manifest digests, sample and cluster counts, overall and per-category precision/recall/F1, macro F1, exact component-count accuracy, matched IoU and subgroup metrics. When each ground-truth component includes product_id and each spatially matched prediction includes retrieved_product_ids, it also scores end-to-end component product Recall@1/5/10, MRR, top-1 accuracy and detected-component coverage. Missed detections count as failed product matches. If the evidence is incomplete, product matching is explicitly reported as not scored. It never stores image bytes or absolute image paths.

## Limitations

- Bounding-box IoU cannot assess overlapping garment masks, garment boundaries or pixel-level segmentation. A future mask benchmark must be added before claiming segmentation quality.
- This tool does not evaluate garment attributes, product retrieval, Try-On quality, anatomical correctness or privacy safety.
- A pilot report is not independent certification. Final thresholds, subgroup minimums and statistical analysis must be preregistered before opening the held-out test set.
- The rights manifest validator checks recorded evidence integrity and scope, not legal sufficiency or signature authenticity.
