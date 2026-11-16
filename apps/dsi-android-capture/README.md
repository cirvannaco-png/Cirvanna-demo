# DSI Android capture SDK

**Status:** implementation scaffold; client-side evidence generation only. This is the first native Android module in the Cirvanna monorepo, not a complete Android application and not a released or trusted capture provider.

## Purpose

This Android library provides a Camera2-specific capture evidence layer for DermalSight. It identifies each exact camera pipeline, checks which capture controls the platform exposes, applies supported AE/AWB locks to a host application's still-capture request, records the actual `TotalCaptureResult`, and binds a digest of the exact in-memory image bytes to a single-use server challenge.

It does not replace the host application's camera UI, permission flow, user authentication, consent capture, image upload or DSI API orchestration. The host app remains responsible for showing the capture guidance, obtaining purpose-bound DSI consent before transmission, requesting a challenge from the authenticated DSI backend, and keeping or discarding image bytes according to the user's choice.

## Components

- `DsiCamera2PipelineInspector` reads Camera2 characteristics, available request/result keys, stream sizes, logical/physical camera IDs, lens/sensor metadata, RAW/manual capabilities and per-device calibration, colour-transform and forward matrices. It produces the same canonical fingerprint shape expected by the backend device-baseline registry. It does not use serial numbers, IMEI, advertising IDs or geolocation.
- `DsiCamera2CaptureControls` begins with unlocked AE/AWB metering, requires both to converge, then requests locks and verifies the lock booleans and LOCKED states in the capture result. The host must retain the result associated with the still image.
- `DsiCaptureManifest` hashes the exact in-memory image bytes and requires `Image.timestamp` to equal `CaptureResult.SENSOR_TIMESTAMP`. It embeds the exact device-baseline report, image dimensions, capture result values, server challenge ID/nonce digest, and chart/illumination/polarization declarations. Canonical JSON is used for signatures and Play Integrity request binding.
- `DsiAndroidCaptureAttestor` creates a per-capture EC signing key in Android Keystore using the server nonce as its Android Key Attestation challenge, requires hardware-backed key storage, signs the canonical manifest and requests a Play Integrity Standard API token whose `requestHash` binds the same manifest.

## Capture sequence

1. Host obtains camera permission and the relevant DSI consent receipt for the exact user, resource and intended analysis purpose.
2. Host requests a short-lived, single-use challenge from the authenticated DSI backend. The response contains an opaque challenge ID, a cryptographically random base64url nonce (at least 256 bits) and expiry.
3. Host calls `inspectAllCameras()` and selects a camera/lens the user can physically use. The SDK does not silently switch to a different lens.
4. Host creates the Camera2 preview/still session. It calls `applyUnlockedMetering()`, waits for a preview result where AE and AWB are converged, calls `applyLocksAfterConvergence()`, then waits for both AE/AWB lock states to be reported as LOCKED before submitting the still request.
5. Host obtains the exact still `Image` and its corresponding `TotalCaptureResult`. It passes the still buffer's `Image.timestamp`, encoded width/height, exact output bytes and the matching capture result into `DsiCaptureManifest.create()`. The SDK rejects the request unless the image and result timestamps match exactly.
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

The server-side implementation is being added on the DSI verification branch. It is still subject to automated CI, deployment configuration and physical-device acceptance. Every SDK envelope remains `pending_server_verification` until the Vision service independently verifies it and Identity Learning persists the receipt. See [issue #217](https://github.com/cirvannaco-png/Cirvanna-demo/issues/217) and [the physical-device test matrix](docs/PHYSICAL_DEVICE_TEST_MATRIX.md).

**Threat-model limit:** Android Keystore attestation and Play Integrity can strengthen app/device integrity and bind a request manifest to a trusted key/token. They do not prove that the signed image bytes originated directly from the physical camera sensor, that no privileged OEM processing occurred, or that the device is free of every compromise. Treat the result as supporting evidence, not sensor-origin attestation. The capture app and all upload paths still require review and server-side validation.

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
- verify image/result timestamp matching and frame association on physical Camera2 devices;
- compare supported image paths with same-session spectrophotometer references under controlled lighting;
- review user consent, permission denial, cancellation, revocation, deletion and memory lifecycle;
- independently sign the exact Android SDK, capture pipeline, device profile and dataset scopes before any baseline promotion.

No phone model is pre-certified by adding this library. No skin/colour result, model readiness or production capability is enabled by this scaffold.


## Authenticated backend submission contract

The host application must call the authenticated API gateway / DermalSight BFF. Do not embed the private DSI_INTERNAL_API_TOKEN or DSI_VISION_API_TOKEN in Android.

1. POST multipart form data to /api/v1/dsi/capture-challenges with subject_id, consent_id, consent_version, resource_id and purpose. The returned challenge contains challengeId, nonceBase64Url and expiresAtEpochMs. Map those fields directly to DsiServerCaptureChallenge. Do not request a challenge until the user has granted the exact purpose consent.
2. Create DsiCaptureManifest from the exact encoded image bytes and matching Camera2 TotalCaptureResult. The image and result timestamps must match.
3. Call DsiAndroidCaptureAttestor.createAttestation(challenge, manifest). The returned DsiAndroidAttestationEnvelope is evidence only; its verificationState must remain pending_server_verification.
4. Serialize the envelope using the exact camelCase property names in DsiAndroidAttestationEnvelope. POST multipart form data to /api/v1/dsi/capture-verifications with subject_id, consent_id, consent_version, resource_id, purpose, envelope_json, challenge_nonce_base64url and the exact original image bytes. The current BFF accepts JPEG, PNG and WebP up to 5 MiB and 16 megapixels. It does not accept RAW/DNG/HEIF through this API yet.
5. Retain the server-created receipt ID and the signed digest metadata. For follow-on trusted analysis, use the receipt-bound DermalSight endpoints. Do not use the receipt to infer absolute colour accuracy, a skin diagnosis or permission to persist a profile.

The API gateway/BFF re-checks consent at challenge and submission time. Vision independently validates the challenge, device certificate chain, ECDSA signature, image and manifest digests, Play Integrity token and server policy. Identity Learning persists the receipt only after both cryptographic checks pass. Vision re-checks active receipt and consent before each receipt-bound inference.

## Current acceptance evidence

- The SDK generates capture manifests and signed evidence; this does not itself authenticate the image or device.
- The backend verification path is implemented in the DSI feature branch and requires CI before deployment.
- The physical-device matrix is currently NOT RUN. No Pixel, Samsung, Transsion or modified-bootloader device has been represented as passing.
- The Android SDK module is a library scaffold. Host-app camera UI, user authentication, Play Console setup, upload orchestration and staging/production secrets remain host/deployment responsibilities.
- A successful certificate and Play Integrity check is not proof of original sensor pixels, no OEM enhancement, optical calibration or validated skin-colour measurements.
