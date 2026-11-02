# ADR-0002: Living Filters face-landmark provider and renderer boundary

- **Status:** Preferred provider implemented behind an opt-in experimental adapter; release remains gated on successful asset preparation, integrity checks, browser smoke tests and device-quality evidence
- **Date:** 2026-10-27
- **Owners:** Cirvanna architecture / Living Filters
- **Scope:** `apps/living-filters/` only; this ADR does not authorize changes to DermalSight, Virtual Try-On orchestration, or CAL

## Context

Living Filters has deterministic CSS colour treatments plus an opt-in local vision path for face-tracked makeup, hair-mask recolouring, and generic 2D glasses/earrings/headband overlays. The runtime and models are prepared as build artifacts and are not committed as opaque binaries. Face landmarks are geometry for a visual renderer; they are not skin-health evidence, identity evidence, or permission to recommend products.

A real implementation needs a versioned provider adapter, explicit model/runtime assets, a rendering layer, device-quality tests, and graceful fallback. Adding a CDN script or silently downloading model files would violate the current no-network design.

## Candidates considered

| Candidate | Advantages | Costs / risks | Decision |
|---|---|---|---|
| **MediaPipe Tasks Vision Face Landmarker (Web)** | Purpose-built for image/video; returns a dense 3D face landmark set, optional blendshapes and facial transformation matrices; documented JS API. | Requires a compatible model bundle and WASM/runtime assets; synchronous frame inference can block the UI unless moved off-thread; model/runtime versioning, licences, CSP and device performance must be checked. | **Preferred candidate for a controlled prototype**, not yet approved for shipping. Vendor all required assets locally and pin versions before enabling. |
| TensorFlow.js face-landmarks-detection | JS/browser integration and a documented face-landmark package; can be evaluated where its runtime fits existing browser infrastructure. | Adds its own dependency/runtime and model/topology choices; local asset packaging, device performance and topology mapping still need validation. | Keep as fallback candidate if MediaPipe fails a measured gate. |
| Remote hosted SDK / CDN model | Fastest initial demo path. | Network dependency, third-party code/model delivery, weaker offline behavior, expanded privacy and CSP surface, and version drift. | **Reject for this local-first prototype.** |
| Build a custom landmark model | Maximum control over model/data and runtime. | Requires a properly licensed and representative dataset, model training/evaluation, device optimization and sustained maintenance. | Not justified for the current milestone. |

References:
- MediaPipe Web Face Landmarker guide: https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/web_js
- MediaPipe task overview and model outputs: https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker
- TensorFlow.js model catalogue: https://www.tensorflow.org/js/models
- TensorFlow.js face-landmarks-detection package: https://github.com/tensorflow/tfjs-models/tree/master/face-landmarks-detection

## Decision

Use the pinned `@mediapipe/tasks-vision@0.10.21` package, with the version-1 Face Landmarker and HairSegmenter models, behind a bundled classic worker. The implementation uses the pinned runtime and models only after preparation. No CDN or remote model fallback is wired into the application. The generated runtime/WASM and model files are kept out of Git and must be produced by the preparation script on a network-enabled build machine.

The implementation must keep these boundaries:

1. **Local-only by default:** package and pin the JS runtime, WASM files, and model bundle as reviewed local assets. No runtime network calls or remote model imports. If assets are absent, corrupt, or unsupported, disable face-tracked effects and retain existing colour filters.
2. **Explicit user control:** camera access remains behind the user's click and browser permission. Photo processing starts only after the user selects a photo. A separate, clear notice must explain face-landmark processing before first use. Provide stop/reset and clean up camera tracks, animation loops, workers, and model resources on source change, page hide, and teardown.
3. **Versioned adapter boundary:** providers emit a validated canonical landmark frame with explicit topology ID, source dimensions, monotonic media timestamp, and finite normalized coordinates. Renderers must declare the topology they support; never assume that point indices are interchangeable across providers.
4. **Render-only evidence:** landmarks and rendered pixels are not inputs to DermalSight. Filter output must never be described as a skin diagnosis, clinical assessment, product fit proof, or identity inference.
5. **CAL and consent remain authoritative:** a local makeup preview is not a product recommendation. Any product/marketplace suggestion, persistence, or server-side media operation requires its existing owning service, server-side consent/authorization, and CAL/CaTaCaCi decision path. The renderer cannot authorize those actions.
6. **Fail closed:** no face detected, invalid landmarks, low confidence, unsupported topology, model failure, or missed frame means hide/skip the face-anchored overlay and show a non-deceptive status. Do not extrapolate a fake face or report success.
7. **Performance:** inference must not monopolize the main UI thread. Evaluate worker/off-thread support and frame throttling before live mode. Stop processing when the page is hidden or the user stops the camera.
8. **No silent collection:** do not persist landmarks, blendshapes, images, or video. No analytics or telemetry in this milestone.

## Required gates before runtime enablement

- Pin package/runtime and model versions; record hashes, provenance, licence and redistribution rights for each artifact, including model assets.
- Confirm supported browsers and mobile devices, including low-memory Android devices.
- Add unit tests for malformed/out-of-range frames, stale timestamps, topology mismatch, no-face output and teardown.
- Add browser E2E tests for first-use notice, camera denial, source switching while loading, page-hide cleanup, offline startup and missing/corrupt local assets.
- Measure end-to-end frame latency, sustained frame rate, memory and thermal behavior on a documented device matrix.
- Evaluate overlay stability across lighting, pose, glasses, occlusion, varied skin tones and face shapes; publish known limitations rather than claim universal accuracy.
- Complete privacy/threat review and confirm CAL/consent integration boundaries remain intact.

## Consequences

The canonical contract, local classic worker, makeup/accessory renderer, hair mask recolouring, and opt-in controls now exist in the feature branch. Runtime/WASM/model files are not checked into Git; the asset preparation script downloads the pinned artifacts during the build and checks their hashes before installation. The controls remain unavailable when those files are missing or unsupported. This is an experimental implementation, not a completed or production-validated AR release. The build pins esbuild and emits `src/vision-worker.bundle.js` as a classic worker because MediaPipe 0.10.21's WASM glue calls `importScripts()`, which is invalid in module workers. The asset and Chromium workflow must pass, then device-quality and privacy review must be recorded before launch.


## Pinned implementation and release gate

The implementation files are:
- `apps/living-filters/src/vision-worker.mjs`: worker source bundled into a classic script for execution; it initializes both models, validates the output frame, copies the hair mask before releasing model resources, and handles disposal/stale sessions.
- `apps/living-filters/src/face-renderer.mjs`: 2D lipstick, eye-colour wash/blush, generic glasses, hoop earrings and headband overlays; plus hair-mask recolouring.
- `apps/living-filters/vision-assets.manifest.json`: immutable package/model URLs, versions, checksums and licence declarations.
- `apps/living-filters/scripts/prepare-vision-assets.mjs`: build-time download, integrity validation, licence retention and asset-lock generation.
- `apps/living-filters/scripts/verify-vision-assets.mjs`: verifies the generated lock, every runtime/WASM file, model hash/size, and CSP.
- `apps/living-filters/scripts/browser-smoke.mjs`: Chromium smoke test that initializes the local models, exercises makeup/hair selection, stops the worker, and asserts no cross-origin request or CSP violation occurred.

The runtime package is pinned at 0.10.21 with npm SHA-512 integrity `sha512-TuhKH+credq4zLksGbYrnvJ1aLIWMc5r0UHwzxzql4BHECJwIAoBR61ZrqwGOW6ZmSBIzU1t4VtKj8hbxFaKeA==`. The face model and hair model are version-1 URLs listed in the manifest; each is checked by its SHA-256 before installation. Apache-2.0 notices, model-card links and asset provenance are recorded in `apps/living-filters/THIRD_PARTY_NOTICES.md` and the complete upstream Apache licence text is copied into the project.

MediaPipe's public Tasks privacy notice describes performance/utilization metrics being sent to Google. This project does not enable third-party endpoints in the application CSP, and its browser smoke test is designed to fail if a cross-origin request or CSP violation is observed. The SDK version must not be upgraded without rechecking the actual bundle and network behavior; if the smoke test sees an outbound metrics attempt, the build is rejected and the SDK must be replaced or a separately approved privacy decision made. Media/video/landmarks are never sent to an app backend by this feature.

## Explicit limits

- The hair model supplies a hair/background segmentation mask, not an image generator; effects recolour visible hair rather than synthesize a different haircut.
- Makeup and accessories are 2D landmark overlays; product-specific matching, depth occlusion, realistic materials, and physically accurate fit remain unimplemented.
- Asset preparation requires network access at build time. After preparation, runtime model/script/WASM loading is same-origin. This is not a promise that the app's HTML can be opened without a host or that an unprepared deployment will work.
- The browser workflow must pass after assets are generated. Unit/contract tests alone do not prove real model initialization, face tracking quality, zero egress, mobile performance, or supported-device quality.
