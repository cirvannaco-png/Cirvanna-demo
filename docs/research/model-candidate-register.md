# Cirvanna model and dataset candidate register

- **Status:** Research inventory; no candidate selected
- **Last reviewed:** 2026-11-20
- **Owner:** Cirvanna architecture / AI evaluation

This register is a diligence queue, not an endorsement list. Every candidate must pass the governing [AI model competition and logic-transfer programme](ai-model-competition-and-logic-transfer.md). A permissive model-weight licence does not automatically clear training data, custom code, processor files, dependencies, images, or the commercial use of evaluation assets.

## 1. Model candidates

| Workstream | Candidate | Current classification | What to investigate | Hard blockers / cautions |
|---|---|---|---|---|
| Visual retrieval | patrickjohncyh/fashion-clip | **Current Cirvanna baseline** | Reproduce pinned revision afacf5e5851d5979ab030e228eab60e2c95a912c; measure image→catalog-text and text→catalog-text | Model card says Farfetch-derived training data over 800K products and notes distribution/long-caption limitations; provenance of training data and current runtime quality remain unverified |
| Visual retrieval | Marqo/marqo-fashionCLIP | Challenger | Compare its GCL multi-attribute training approach; inspect exact files, processor, OpenCLIP path and runtime | Apache-2.0 model-card metadata is not complete rights review; repository advertises custom code and some loading examples require remote code. Prefer a reviewed non-remote-code route where supported |
| Visual retrieval | Marqo/marqo-fashionSigLIP | Challenger | Compare SigLIP backbone and GCL attribute supervision under the same benchmark | Its reported up-to-57% MRR/recall improvement over FashionCLIP is a model-card/vendor claim on its protocol, not a Cirvanna result; exact revision and file hashes must be pinned |
| Visual retrieval | srpone/zooclaw-fashionsiglip2 | Challenger | Test SigLIP2 384px representation; understand full fine-tuning, distillation and WiSE-FT claims | Larger runtime footprint; training-data chain still needs review. Do not use the associated CC BY-NC evaluation dataset for commercial development without separate written rights |
| Visual retrieval | Marqo FashionSigLIP 2 hosted offering | Vendor/API diligence only | Request API/model version, service SLA, data-processing terms, retention, training-use policy, region and pricing | Do not assume an openly downloadable checkpoint or equivalent rights from the earlier FashionSigLIP model card |
| Virtual Try-On | FASHN VTON 1.5 | **Already in Cirvanna private worker** | Benchmark actual pinned end-to-end render pipeline only after assets/GPU are provisioned and input/output quality protocol is ready | ADR-0011 blocks commercial production while the Human Parser/SegFormer dependency is not commercially cleared; complete parser revision/hash and transitive rights are unresolved |
| Virtual Try-On | CatVTON | Research architecture | Study spatial concatenation, attention-efficient garment/person conditioning, memory and preprocessing reduction as public research ideas | Referenced model repository is non-commercial; do not use weights/code for commercial deployment or adaptation absent changed permission |
| Virtual Try-On | IDM-VTON | Research architecture | Study garment conditioning and high-fidelity try-on evaluation methods | Referenced repository licence is CC-BY-NC-SA-4.0; not commercial-ready by default |
| Virtual Twin | facebook/sam-3d-body-dinov3 | Research / gated diligence | Test 3D body reconstruction separately from pose keypoints; measure geometry, body coverage, scale, repeatability and rig compatibility | Gated weights and Meta licence conditions need legal review. It is not a proven body-measurement or fit model |
| Pose estimation | qualcomm/MediaPipe-Pose-Estimation | Challenger | Compare keypoint completeness, confidence, occlusion and runtime to Cirvanna's current MediaPipe pose path | Must pin exact revision/artifact and check model card, runtime and commercial terms |
| Click It privacy | Current MediaPipe BlazeFace full-range TFLite asset | **Current detector baseline** | Evaluate recall/false-negative rate and masking-boundary quality on a representative consented set | Existing synthetic no-face smoke test is not recall evidence; detector's published limits mean it cannot independently authorize publication |
| Click It privacy | qualcomm/MediaPipe-Face-Detection | Challenger | Compare face-region recall and false negatives against current pinned detector under privacy-first thresholds | Masking-only task; no identity or demographic inference; uncertain detection must reject |
| Segmentation | facebook/sam2.1-hiera-* family | Research challenger | Compare object/garment segmentation boundaries, occlusion and runtime on a human-annotated garment dataset | General segmentation is not automatically fashion/garment understanding; pin exact checkpoint and commercial provenance |

### Candidate decision vocabulary

- BASELINE: exact current Cirvanna implementation being challenged.
- CHALLENGER: eligible for controlled evaluation after revision and rights pinning.
- RESEARCH_ONLY: public technique may be studied, but assets/weights/code are not cleared for commercial use.
- GATED_DILIGENCE: access, licence, provenance, contracts or model artifacts are not sufficiently reviewed.
- REJECTED: failed a declared technical, rights, safety or operational gate.
- SELECTED_FOR_SCOPED_PILOT: passed a named, scoped benchmark and all pilot approvals.
- PRODUCTION_ELIGIBLE: full production release gates passed; does not follow from benchmark performance alone.

No candidate in this register has SELECTED_FOR_SCOPED_PILOT or PRODUCTION_ELIGIBLE status.

### Immutable revisions and artifact inventory

The current Hugging Face file inventory reports these primary checkpoint sizes:

| Candidate | Weight file | Current file size | Verified full commit SHA | Current benchmark state |
|---|---|---:|---|---|
| Cirvanna FashionCLIP baseline | `model.safetensors` | 605,157,890 bytes | `afacf5e5851d5979ab030e228eab60e2c95a912c` | Baseline pin already present in Vision Intelligence |
| Marqo FashionCLIP | `open_clip_model.safetensors` | 598,516,980 bytes | `44f4c655124ed71e90cbf528d82f508d69d8a81b` | Hub revision and checkpoint file verified; pinned in runner |
| Marqo FashionSigLIP | `open_clip_model.safetensors` | 812,658,408 bytes | `c56244cc94f92419e8369fa71efdaf403b124ce8` | Hub revision and checkpoint file verified; pinned in runner |
| ZooClaw-FashionSigLIP2 | `model.safetensors` | 1,501,968,264 bytes | **Not yet verified** | Excluded from the first pinned run until its full commit SHA is available |

These are individual checkpoint-file sizes from the Hub file listing, not full download size, peak RAM/VRAM, or deployment requirements. The runner uses an explicit allow-list to avoid downloading duplicate formats and hashes the included weights, processor/tokenizer files and model-card/licence notices after download.

The two Marqo revisions above were checked as explicit `hf://models/OWNER/REPO@SHA` repository references, and each exact revision exposed the expected `open_clip_model.safetensors` file. They are now frozen in the runner's model registry. ZooClaw's full commit SHA is still unresolved; do not replace it with a short hash or moving `main`. The first executable shortlist can proceed with the baseline and the two pinned Marqo challengers, subject to the data-rights and compute gates.

The research dependency source ranges are accompanied by a SHA-256-hashed CPU-only lock for CPython 3.11 on Linux x86_64. That lock supports controlled CPU pilots only; a separate CUDA-specific lock and approved GPU image/driver validation remain required before GPU benchmarking. Record the exact lock digest in each private experiment preregistration.



## 2. Dataset candidates

| Dataset | Intended use | Current classification | Rights / methodology notes |
|---|---|---|---|
| [LookBench](https://huggingface.co/datasets/srpone/look-bench) | Main public research candidate for studio, street-style and multi-item retrieval | REVIEW_REQUIRED | Dataset card advertises Apache-2.0 metadata; independently audit underlying image sources, people/photographer rights, commercial use, consent and redistribution before Cirvanna use |
| [Fashion200K pooled evaluation](https://huggingface.co/datasets/srpone/fashion200k-pooled-eval) | Supplementary retrieval metric | SECONDARY_ONLY | Pooled relevance judgments include LLM-assisted labels; original corpus images are not automatically licensed by the pooled qrels. Audit underlying image rights |
| [Fashionpedia](https://huggingface.co/datasets/detection-datasets/fashionpedia) | Garment attribute/segmentation research | REVIEW_REQUIRED | Dataset metadata describes CC BY 4.0; verify image-level provenance, attribution requirements and permitted commercial derivative use |
| [ZooClaw fashion evaluation](https://huggingface.co/datasets/srpone/zooclaw-fashion-eval) | External paper's evaluation context | NOT_APPROVED_FOR_COMMERCIAL_USE | Hub dataset card displays CC BY-NC 4.0. Do not use for commercial development absent specific written permission |
| DeepFashion2 mirror sahirp/deepfashion2 | Potential garment parsing/retrieval | REJECTED_FOR_CURRENT_RUN | Previously inspected mirror had a broken dataset generation / zero-row state. Do not rely on it without a verified repaired source and immutable snapshot |
| Cirvanna controlled catalogue set | Product-level launch benchmark | REQUIRED_TO_BUILD | Needs approved product images, Catalog metadata, stable product/variant IDs, source rights, exact snapshots and human relevance labels |

## 3. Next review actions

1. Resolve ZooClaw-FashionSigLIP2's immutable revision; capture and verify the SHA-256 hashes generated by the runner for the two pinned Marqo snapshots.
2. Obtain a written data-provenance and commercial-use assessment for every model and dataset before training, fine-tuning, distillation or customer-facing use.
3. Create the rights-cleared Cirvanna catalogue snapshot and human-reviewed query set.
4. Execute the [fashion-retrieval challenger benchmark](fashion-retrieval-challenger-benchmark.md) against the exact baseline before changing the serving model.
5. Add a candidate to a scoped pilot only when the report establishes measurable value and all independent safety, privacy, operational and legal gates pass.
