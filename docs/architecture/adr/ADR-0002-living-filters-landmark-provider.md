# ADR-0002: Living Filters face-landmark provider and renderer boundary

- **Status:** Proposed implementation decision; runtime adoption is gated
- **Date:** 2026-10-27
- **Owners:** Cirvanna architecture / Living Filters
- **Scope:** `apps/living-filters/` only; this ADR does not authorize changes to DermalSight, Virtual Try-On orchestration, or CAL

## Context

Living Filters currently applies deterministic CSS colour treatments and decorative overlays to a local camera/photo preview. It does not track a face. The app's current Content Security Policy forbids network connections, and the privacy promise is that media remains on-device. Face landmarks are geometry for a visual renderer; they are not skin-health evidence, identity evidence, or permission to recommend products.

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

Use **MediaPipe Tasks Vision Face Landmarker as the preferred candidate for a local, opt-in prototype**, subject to all gates below. This is a selection for evaluation, not a claim that the runtime or face tracking is already implemented. Do not add a CDN, runtime dependency, or model binary in this change.

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

The first follow-up can implement a small canonical contract and contract tests without importing a model. Actual face-anchored makeup, hair segmentation and accessory placement remain disabled until the above gates are met. This deliberately avoids converting an architectural decision into an unsupported feature-completion claim.
