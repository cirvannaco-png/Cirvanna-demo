# DSI MediaPipe model and task notices

DSI uses MediaPipe Tasks APIs for two optional still-image inference tasks:

- Face Landmarker: 478-point normalized facial landmarks. The DSI worker does not enable blendshapes or transformation matrices and does not compute face embeddings, recognition or age.
- Multiclass Selfie Image Segmenter: background, hair, body-skin, face-skin, clothes and others masks. It does not measure skin colour or distinguish individual body regions.

The official Face Landmarker V2 and Multiclass Selfie Segmenter model cards state Apache License 2.0 for the corresponding model artifacts. See the official documentation and model cards linked in the Vision Intelligence README.

No binary model assets are stored in this repository. Before an asset is provisioned, record its exact source, version, SHA-256 digest, license, model-card revision, preprocessing/output contract and evaluation evidence in the deployment release record. Do not infer the license of an arbitrary third-party or modified model merely from its MediaPipe task family.

The official 256×256 multiclass selfie segmenter model card reports limited evaluation coverage for Monk tones 9–10 (31 images, approximately 1.6% of the evaluation set). This must be treated as a material evaluation limitation. Cirvanna must independently evaluate subgroup error, image quality and regional segmentation before enabling tone-related product claims.
