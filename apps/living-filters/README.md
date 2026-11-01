# Cirvanna Living Filters

**Status:** experimental, local-only visual/AR prototype. The face-tracked UI and renderer are implemented in code, but the pinned runtime and model binaries are generated during preparation rather than committed. Do not treat it as release-verified until asset verification and the browser/model smoke test pass.

## Current capability

- Camera preview after explicit browser permission, and local JPEG/PNG/WebP/AVIF photo preview (12 MB file cap; decoded image capped at 40 million pixels).
- Eight curated colour/creative treatments and local PNG export.
- Optional on-device 478-point Face Landmarker, running in a bundled classic worker. MediaPipe 0.10.21's WASM glue uses `importScripts()`, so the worker is bundled as a classic script rather than loaded as an ES module.
- Landmark-anchored cosmetic rendering: berry lipstick, an eye-colour wash and blush. These are approximate 2D effects, not makeup product matching or a skin-health analysis.
- Optional hair segmentation with copper/violet recolouring from a hair/background mask. This segments visible hair pixels; it does **not** synthesize a different cut, add volume, replace braids, or generate a new hairstyle.
- Landmark-anchored 2D accessory placement: glasses, hoop earrings and a decorative headband. These are generic overlays, not product-specific assets, physical fit estimates, reliable occlusion, or 3D rendering.
- Camera/frame processing and model inference run locally in a browser worker. No upload/remote-model fallback is intentionally configured. The browser smoke test fails if a cross-origin request or CSP violation is observed.

## Prepare the runtime and model assets

Requires **Node.js 20+**, npm, and temporary network access during build/preparation. Run from the repository root:

    node apps/living-filters/scripts/prepare-vision-assets.mjs
    node apps/living-filters/scripts/verify-vision-assets.mjs

Preparation fetches the exact versioned `@mediapipe/tasks-vision@0.10.21` npm tarball and the two versioned model files specified in `vision-assets.manifest.json`. It verifies the package SHA-512 integrity and the model SHA-256 values before installing to:

- `apps/living-filters/vendor/mediapipe/` (local JS bundle, WASM variants, licence and generated asset lock)
- `apps/living-filters/models/` (face landmarker and hair segmenter)

The runtime bundle and model binaries are ignored by Git to avoid committing opaque multi-megabyte artifacts. Build/deployment must run preparation and publish these generated directories along with the static app. **The running app must never fetch a CDN or model URL.** If any file is missing, changed, or unsupported, use the original colour filters and display an error rather than silently switching providers.

The attribution and licence notes are in [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md); the complete MediaPipe Apache-2.0 license text is in `third-party/mediapipe-LICENSE`. Model cards, source URLs and pinned hashes are recorded with the manifest. Any version or model update requires fresh integrity, licence, CSP and browser checks.

## Run locally

After preparing and verifying assets:

    python -m http.server 8080 --directory apps/living-filters

Open http://localhost:8080. Camera access requires HTTPS or localhost and browser permission. Photo preview and all effects run without an application backend.

If the assets have not been prepared, face-tracked effects intentionally fail with a visible setup message; the eight local colour treatments remain available.

## Tests and validation

Run the Node.js contract/unit suite:

    node --test apps/living-filters/tests/*.test.mjs

Check syntax and verify installed binary hashes:

    node --check apps/living-filters/src/app.mjs
    node --check apps/living-filters/src/vision-worker.mjs
    node --check apps/living-filters/src/face-renderer.mjs
    node apps/living-filters/scripts/verify-vision-assets.mjs

Run the Chromium end-to-end smoke test after asset preparation, pinned worker bundling and asset verification:

    cd apps/living-filters
    npm install --no-save --no-package-lock --ignore-scripts playwright@1.55.0 esbuild@0.28.2
    npx --no-install esbuild src/vision-worker.mjs --bundle --platform=browser --format=iife --target=es2022 --outfile=src/vision-worker.bundle.js
    node --check src/vision-worker.bundle.js
    node scripts/verify-vision-assets.mjs
    npx playwright install chromium
    node scripts/browser-smoke.mjs

The browser smoke test initializes both local models, selects makeup and hair modes, stops the worker, and fails on cross-origin requests, CSP violations or browser errors. The GitHub workflow is configured to perform these steps. A passing static contract test is not a substitute for a successful run of the browser/model test; check the PR's actual Actions result before release.

## Privacy, safety and limitations

- Face/hair processing is opt-in for each page session; camera access is separately permission-gated by the browser.
- Media, landmarks and segmentation masks are held in memory for the current page session. This feature does not persist them or send them to the Cirvanna backend.
- The app's CSP permits same-origin worker/model loading and WASM compilation, but prohibits third-party runtime resources. The browser test checks for cross-origin requests and CSP violations.
- Source changes, stop action, consent withdrawal and page hide tear down the worker and stop camera tracks. Model assets are downloaded only during the explicit build step, not during a running user session.
- Hair segmentation is imperfect: thin braids, head coverings, overlap, movement, unusual lighting or off-angle views may produce poor masks. No overlay should be interpreted as evidence of product suitability or a promise of a real-world look.
- Makeup and accessory geometry is approximate 2D drawing. Realistic eye/lip shading, hair strand occlusion, 3D accessory alignment, depth, expression deformation and generative hairstyle replacement are not implemented.
- The feature does not feed rendered or segmented pixels into DermalSight and cannot make product recommendations. Any future product/marketplace recommendation, server-side processing, or persistence must be implemented through its owning service with server-side consent/authorization and CaTaCaCi/CAL governance.
- No privacy/security certification or universal face-detection accuracy is implied. Release requires real-device profiling, quality evaluation across varied skin tones/face shapes/lighting, dependency/license review, and a privacy/threat review.

See [ADR-0002](../../docs/architecture/adr/ADR-0002-living-filters-landmark-provider.md) for the provider and renderer boundary decision.
