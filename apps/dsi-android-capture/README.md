# DSI Android capture SDK

**Status:** implementation scaffold; client-side evidence generation only. This is the first native Android module in the Cirvanna monorepo, not a complete Android application and not a released or trusted capture provider.

## Purpose

This Android library provides a Camera2-specific capture evidence layer for DermalSight. It identifies each exact camera pipeline, checks which capture controls the platform exposes, applies supported AE/AWB locks to a host application's still-capture request, records the actual `TotalCaptureResult`, and binds a digest of the exact in-memory image bytes to a single-use server challenge.

It does not replace the host application's camera UI, permission flow, user authentication, consent capture, image upload or DSI API orchestration. The host app remains responsible for showing the capture guidance, obtaining purpose-bound DSI consent before transmission, requesting a challenge from the authenticated DSI backend, and keeping or discarding image bytes according to the user's choice.

## Components

- `DsiCamera2PipelineInspector` reads Camera2 characteristics, available request/result keys, stream sizes, lens/sensor metadata, RAW/manual capabilities and available sensor calibration matrices. It produces a deterministic camera-pipeline fingerprint. It does not use serial numbers, IMEI, advertising IDs or geolocation.
- `DsiCamera2CaptureControls` applies AE and AWB lock requests only when the exact camera advertises the required keys and modes. The host must wait for a returned `TotalCaptureResult` confirming both states are locked before treating a capture as lock-observed.
- `DsiCaptureManifest` records the exact image SHA-256, byte count, pipeline fingerprint, server challenge ID/nonce digest, actual capture result values and chart/illumination/polarization declarations. Canonical JSON is used for signatures and Play Integrity request binding.
- `DsiAndroidCaptureAttestor` creates a per-capture EC signing key in Android Keystore using the server nonce as its Android Key Attestation challenge, requires hardware-backed key storage, signs the canonical manifest and requests a Play Integrity Standard API token whose `requestHash` binds the same manifest.

## Capture sequence

1. Host obtains camera permission and the relevant DSI consent receipt for the exact user, resource and intended analysis purpose.
2. Host requests a short-lived, single-use challenge from the authenticated DSI backend. The response contains an opaque challenge ID, a cryptographically random base64url nonce (at least 256 bits) and expiry.
3. Host calls `inspectAllCameras()` and selects a camera/lens the user can physically use. The SDK does not silently switch to a different lens.
4. Host creates the Camera2 preview/still session. It calls `applyExposureAndWhiteBalanceLocks()` only when supported, waits for AE/AWB state confirmation, then performs the still capture.
5. Host retains the returned still bytes in memory and passes those exact bytes and the corresponding `TotalCaptureResult` into `DsiCaptureManifest.create()`.
6. Host obtains a Play Integrity Standard API token provider early in the app session, then calls `createAttestation()`. The SDK signs the manifest and binds its SHA-256 to the Play Integrity `requestHash`.
7. Host sends the manifest, signature, Android attestation certificate chain, Play Integrity token and image bytes through the authenticated DSI API. The image must be bound to the same capture reference and image digest. Do not persist the original media unless a separately justified, consented purpose requires it.

The backend must issue and consume challenges atomically. Repeated, expired, wrong-subject, wrong-purpose, wrong-resource or mismatched-digest challenges must be rejected. The client clock is informational; the server controls expiry and replay checks.

## What Android APIs can and cannot prove

The SDK uses actual Camera2 characteristics and capture results rather than assuming that all phones support the same features. It can report RAW support, MANUAL_SENSOR/MANUAL_POST_PROCESSING support, request/result key availability, the presence/digests of sensor calibration transforms and the AE/AWB state returned for a particular frame.

Camera2 does **not** expose a universal signal proving that an OEM beauty filter, HDR enhancement, skin smoothing, tone mapping or other vendor image-processing step has been disabled. The SDK therefore records `vendor_image_processing_state=not_exposed_by_camera2`. A JPEG is not a calibrated colourimeter output merely because AE/AWB were locked. For a device without a validated RAW or exact JPEG colour pipeline, DSI must keep the experience relative-only. Device baselines and individual colour-measurement release gates remain server-side.

Camera2 AE/AWB lock results are capture metadata, not laboratory proof of stable spectral illumination. A physical chart and calibrated light measurement still require their own protocol and independent review. User/device declarations for illuminance, chart condition or polarization remain untrusted.

## Server verification required before any trusted status

The backend must independently:

- authenticate the signed-in subject and verify exact DSI consent purpose, resource, expiry and revocation;
- atomically consume the challenge and check its subject/resource/purpose binding and expiry;
- validate the Android certificate chain against the approved Google attestation root, verify signatures and the attestation extension's challenge, verify verified-boot/application identity claims as policy requires, and check Google's attestation certificate revocation status list;
- verify the ECDSA signature over the exact canonical manifest;
- send the Play Integrity token to Google's decode endpoint using server-held service-account credentials, then verify package name, request hash, timestamp, app-recognition verdict and the required device-integrity labels;
- compare the uploaded image digest/size with the signed manifest and the actual image bytes before any inference;
- record an immutable, short-lived verification receipt bound to the exact manifest digest, image digest, pipeline fingerprint, challenge, app package/version, validation policy and capture runtime;
- return a server-generated verification state. The client must never set `attestation_verified=true` or change the device operational tier.

The current backend does not yet perform these checks for Android captures. Until that verifier and the authenticated challenge endpoints are deployed and independently tested, every SDK envelope is `pending_server_verification` and **must remain relative-only**.

## Build and test

Requires JDK 17, Android SDK Platform 35 and Gradle 8.11.1 or newer compatible with Android Gradle Plugin 8.9.1. From this directory:

```bash
gradle :dsi-android-capture:testDebugUnitTest :dsi-android-capture:assembleRelease
```

The JVM tests cover canonical serialization, escaping, stable hashing and rejection of non-finite values. They do not exercise physical camera hardware, Android Keystore, Play Integrity, device attestation or OEM processing.

## Physical acceptance gates

Before promoting this SDK:
- real-device QA on a representative device matrix including low-cost Android phones;
- check every physical rear/front lens and stream-format combination separately;
- confirm locked AE/AWB state in actual Camera2 capture results and check that the host uses the result paired with the exact bytes;
- test devices with RAW, devices without RAW, unavailable sensor calibration transforms, legacy/limited hardware levels and unsupported lock modes;
- verify StrongBox/TEE attestation chains on real devices, revoked certificate handling, Play Integrity verdicts and replay rejection against the staging backend;
- compare supported image paths with same-session spectrophotometer references under controlled lighting;
- review user consent, permission denial, cancellation, revocation, deletion and memory lifecycle;
- independently sign the exact Android SDK, capture pipeline, device profile and dataset scopes before any baseline promotion.

No phone model is pre-certified by adding this library. No skin/colour result, model readiness or production capability is enabled by this scaffold.
