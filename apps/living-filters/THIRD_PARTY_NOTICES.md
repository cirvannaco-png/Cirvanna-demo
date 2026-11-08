# Third-party notices — Living Filters local vision assets

This application downloads the following files only during the explicit asset-preparation/build step. The running browser app references same-origin files and is configured to block network requests outside its own origin.

## MediaPipe Tasks Vision Web runtime

- Package: `@mediapipe/tasks-vision@0.10.21`
- Registry tarball: https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-0.10.21.tgz
- Integrity: `sha512-TuhKH+credq4zLksGbYrnvJ1aLIWMc5r0UHwzxzql4BHECJwIAoBR61ZrqwGOW6ZmSBIzU1t4VtKj8hbxFaKeA==`
- Source/licence: https://github.com/google-ai-edge/mediapipe/tree/v0.10.21
- Licence: Apache License 2.0. The complete licence text is included in `third-party/mediapipe-LICENSE` and copied into the generated vendor directory.
- The version is pinned rather than using `latest`. Do not upgrade it without reviewing API compatibility, licence/notice changes, metrics behaviour, CSP, and offline requests.

## Face Landmarker model

- Version: `face_landmarker/face_landmarker/float16/1`
- Source: https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
- SHA-256: `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`
- Model card: https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf
- Licence stated by the model card: Apache License 2.0.
- Intended use: visual landmark geometry for local makeup/accessory overlays. Not for identity recognition, diagnosis, or other sensitive decisions.

## Hair segmentation model

- Version: `image_segmenter/hair_segmenter/float32/1`
- Source: https://storage.googleapis.com/mediapipe-models/image_segmenter/hair_segmenter/float32/1/hair_segmenter.tflite
- SHA-256: `2628cf3ce5f695f604cbea2841e00befcaa3624bf80caf3664bef2656d59bf84`
- Model card: https://storage.googleapis.com/mediapipe-assets/Model%20Card%20-%20Hair%20Segmentation.pdf
- Licence stated by the model card: Apache License 2.0.
- Intended use: a hair/background mask for hair-colour effects. It does not generate or replace a hairstyle. Thin braids, head coverings, occlusion, motion and poor lighting may reduce quality.

## Integrity and distribution policy

- The asset-preparation script verifies the npm tarball SRI and SHA-256 of both model files before installing any staged assets.
- Generated `vendor/` and `models/` directories are ignored by Git; binaries are prepared in the deployment/build workspace, then published with the static app. Build logs should retain the generated `vendor/mediapipe/assets-lock.json` as evidence.
- Model/runtime updates must pin immutable versions and hashes, update this notice, and pass local/offline smoke tests before release.
- This notice and the upstream model cards are attribution references, not a substitute for project-specific legal review.
