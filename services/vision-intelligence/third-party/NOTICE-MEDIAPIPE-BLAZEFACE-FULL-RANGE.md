# Third-party notice: MediaPipe BlazeFace full-range

Cirvanna Vision Intelligence provisions this model into its Docker image from Google's versioned MediaPipe model distribution.

- Model: MediaPipe BlazeFace (full-range)
- Upstream URL: https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_full_range/float16/1/blaze_face_full_range.tflite
- Model SHA-256: 3698b18f063835bc609069ef052228fbe86d9c9a6dc8dcb7c7c2d69aed2b181b
- Expected size: 1,083,786 bytes
- Authors: Valentin Bazarevsky, Google
- Model card: https://storage.googleapis.com/mediapipe-assets/MediaPipe%20BlazeFace%20Model%20Card%20%28Full%20Range%29.pdf
- Licence: Apache License, Version 2.0

The model is used only to detect face bounding boxes and confidence scores for privacy masking. Cirvanna does not use it for face recognition, identity matching, naming, age estimation, demographic inference or person search.

The upstream model card documents important limitations: sensitivity to face scale, orientation, lighting and image conditions; no guarantee for turned-away or strongly inclined faces, faces beyond approximately five metres, or crowds exceeding the detector's output limit. The model is not a substitute for human review or a representative Cirvanna false-negative evaluation.

Copyright and licence terms remain with the upstream authors/rightsholders. See the upstream model card and the Apache License 2.0.
