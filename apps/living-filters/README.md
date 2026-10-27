# Cirvanna Living Filters

**Status:** local-only browser prototype. This is a presentation feature, not a validated AR or generative rendering system.

## What works

- Camera preview after the user explicitly requests camera access.
- Local JPEG, PNG, WebP, and AVIF photo preview (12 MB cap; files are not sent to a server).
- Eight curated visual treatments: Original, Golden Hour, Dewy Light, Rose Tint, Editorial, Aurora, Starlight, and Soft Film.
- Local PNG capture of the selected visual treatment.
- Camera tracks stop when the user stops the camera or the page becomes hidden.
- Late camera-permission results are discarded and their tracks stopped if the user switches to a photo or the page is hidden while permission is pending.
- Responsive controls and a restrictive Content Security Policy.

## What does not work yet

This prototype does **not** implement face landmarks, realistic face-anchored lipstick or makeup, hairstyle segmentation, 3D accessory placement, generative video effects, saved user profiles, marketplace matching, RadianceScore calculation, or skin inference. CSS colour treatments and decorative overlays are not equivalent to Snapchat/TikTok-grade face-tracked lenses. The UI names this boundary explicitly.

The existing services/virtual-try-on API remains the owner of try-on orchestration. It is currently guarded and does not have a validated production renderer. Living Filters does not bypass that API or enable an unvalidated model. CAL and consent service integration are mandatory before any filter can initiate a product/clinical recommendation or server-side media processing.

## Privacy and security

- No API calls, external scripts, analytics, cookies, or remote model imports are used by the app.
- Media is processed in the browser. The selected image is held through a temporary object URL and is not persisted or uploaded.
- Camera access requires an explicit user click and browser permission. Camera support requires a secure context (HTTPS or localhost).
- When the page becomes hidden, camera tracks are stopped. The user can stop the camera at any time.
- The image input accepts selected image MIME types and rejects files over 12 MB. The browser still performs image decoding; this is not malware scanning.
- Captures are created locally and downloaded to the device. The browser controls the final download location.

No privacy or security certification is implied by these safeguards. Production launch requires testing against supported browsers/devices and a formal threat/privacy review.

## Run locally

Requires a recent browser and Python 3 for a local static server.

    python -m http.server 8080 --directory apps/living-filters

Open http://localhost:8080. Camera access requires HTTPS or localhost and browser permission. Photo preview and visual effects run without a backend.

## Tests

The catalogue contract tests use Node's built-in test runner.

    node --test apps/living-filters/tests/*.test.mjs

These tests validate immutable filter metadata and invariants. They are not browser end-to-end or face-tracking quality tests.

## Integration plan

1. Add browser-based end-to-end tests for permission denial, file validation, capture, keyboard access, and camera-track cleanup.
2. Follow [ADR-0002](../../docs/architecture/adr/ADR-0002-living-filters-landmark-provider.md): MediaPipe Tasks Vision is the preferred local prototype candidate, but runtime/model adoption remains blocked on pinned local assets, licence review, device quality, CSP/offline and latency gates. A provider-neutral landmark-frame validator and contract tests now establish the adapter boundary; they do not perform face detection.
3. Add consent-scoped face-anchored cosmetic effects behind a renderer adapter; never use a beauty filter's rendered pixels as DermalSight input.
4. Add hairstyle/accessory preview only when segmentation/asset alignment has measured quality and fallback behavior.
5. Route product suggestions through existing product/identity services and CaTaCaCi/CAL. Client-side filter selection must never authorize a recommendation, claim fit, or infer sensitive identity.
6. Preserve local-only behavior when model providers are unavailable; fail visibly instead of fabricating a successful try-on.