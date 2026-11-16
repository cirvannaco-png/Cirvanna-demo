# DSI physical-device security and capture test matrix

**Current execution state: BLOCKED / NOT RUN.** No physical Android device, Google Play installation context, or live Play Integrity project credentials were attached to this engineering session. This matrix is an execution protocol, not evidence of a passing device.

## Release rule

No device enters a quantitative DSI tier from model name, megapixels, RAW support, Play Integrity alone, or a successful build. Every row requires a dated run, exact device/OS/build, app signing identity, capture SDK version, camera pipeline fingerprint, raw test artifacts with secrets removed, reviewer and pass/fail rationale. A single failed security assertion blocks trusted capture for that device/pipeline. Failure of an optional hardware capability may downgrade the device to relative-only where policy explicitly permits; a failed key/boot/app/manifest proof may not.

## Candidate device coverage

All candidate rows start as **NOT RUN**. Replace these with actual physical devices and measured build identifiers during execution.

| Candidate class | Representative coverage target | Attestation expectation to measure | Capture paths to exercise | Status |
|---|---|---|---|---|
| Google Pixel, recent release | Android 14/15/16; TEE and StrongBox-capable variant where available | TEE/StrongBox certificate chain, VERIFIED boot, locked state, package/signing digest | Front, rear wide, RAW where actually exposed, JPEG/PNG | NOT RUN |
| Samsung Galaxy S-series | Recent Android release; device security hardware variation | TEE/StrongBox support and Play Integrity labels | Front, rear wide/telephoto, JPEG and available RAW | NOT RUN |
| Transsion low-cost Android | TECNO / Infinix / itel class, multiple OS builds | TEE support where available; explicit rejection where only software key exists | Front/rear lenses, JPEG/PNG, AE/AWB lock support | NOT RUN |
| Legacy / limited camera device | Android 7–11 and limited/legacy Camera2 hardware | Must prove accepted attestation and boot claims independently; otherwise reject | JPEG only, absent RAW/transforms, lock limitations | NOT RUN |
| Unlocked / modified test device | Authorized lab device with unlocked bootloader or modified test image | Must fail locked/verified-boot policy | All available capture modes | NOT RUN |

The exact model, build fingerprint and pipeline fingerprint are evidence fields; the table's named families are sampling targets, not approved devices.

## Positive-path protocol

1. Install the exact production-signed app from Google Play using a licensed test account. Record package name, version code, signing certificate SHA-256, Play install source, Android build and patch level.
2. Obtain active consent for the exact subject, resource and DSI purpose through the normal app flow. Request a one-time capture challenge from the authenticated gateway. Confirm the SDK receives challengeId, nonceBase64Url and expiresAtEpochMs.
3. Enumerate physical cameras. For each lens/format, record the canonical Camera2 pipeline fingerprint. Do not infer the tested rear lens from a logical multi-camera ID.
4. Run AE/AWB convergence and locks. Retain the TotalCaptureResult paired with the exact still Image; verify Image.timestamp equals SENSOR_TIMESTAMP.
5. Create the canonical manifest and verify the local image SHA-256 / byte count. Sign with the per-capture Android Keystore key. Confirm Android reports hardware backing; record whether StrongBox or TEE is available.
6. Request the Play Integrity Standard token using the manifest SHA-256 request hash. Submit the exact image bytes and full signed envelope to the DSI gateway.
7. Confirm the backend returns a receipt only after independent key-attestation verification and successful server-side Play Integrity decoding. Inspect the persisted receipt for exact manifest, image and pipeline digests, package/signing digest, app version, server policy version, security level, verified boot, recognition, licensing and device verdicts.
8. Use the receipt on the receipt-bound DSI analysis route. Modify one image byte and repeat; it must reject before inference. Revoke consent or expire the receipt and repeat; it must reject before inference.
9. Repeat each lens and output encoding independently. A successful front camera run does not qualify a rear camera pipeline.

## Adversarial / negative-path protocol

| Attack or failure | Required outcome | Status |
|---|---|---|
| Replace one image byte after manifest signing | Reject image digest mismatch; no receipt / no inference | NOT RUN on hardware; unit contract covered |
| Alter manifest after signing | Reject signature or canonical manifest mismatch | NOT RUN on hardware |
| Alter challenge ID or nonce | Reject challenge/nonce binding; no receipt | NOT RUN on hardware; backend contract tests required |
| Replay a consumed challenge | Reject atomically; no second receipt | Existing Identity service test coverage; physical E2E NOT RUN |
| Supply client hint androidKeySecurityLevel=software/strongbox falsely | Ignore hint; use server-derived attestation extension | Unit contract covered; hardware E2E NOT RUN |
| Software-backed key | Reject | Unit policy only; physical negative test NOT RUN |
| Missing/broken/unknown certificate chain | Reject; no Identity consume | CLI negative test / CI pending |
| Revoked or suspended attestation certificate | Reject; no Identity consume | Status parser unit coverage; real revoked hardware chain NOT RUN |
| Bootloader unlocked or unverified boot | Reject | Physical test NOT RUN |
| Wrong package, signing cert or old app version | Reject | Play Integrity payload contract tests; real Play token NOT RUN |
| App not Play-recognized or unlicensed | Reject | Play Integrity payload contract tests; real Play token NOT RUN |
| Missing MEETS_DEVICE_INTEGRITY / MEETS_STRONG_INTEGRITY | Reject | Play Integrity payload contract tests; real Play token NOT RUN |
| Stale/future-dated Play Integrity token | Reject | Unit contract covered; live token NOT RUN |
| Google decoder, trust list, Identity or verifier unavailable | Fail closed; no receipt, no inference | Mock/provider tests; live outage test NOT RUN |
| OEM enhancement cannot be observed/disabled | Do not claim sensor-origin pixels or quantitative colour accuracy | Must be documented per pipeline |

## Required test record

For every device/lens/format combination capture:
- Date/time UTC, tester and reviewer.
- Manufacturer, model, Android version, build fingerprint, security patch level, bootloader lock and verified-boot claims.
- App package, version code, distribution source, certificate SHA-256 and SDK version.
- Camera ID (non-identifying), lens role, physical/logical relationship, Camera2 hardware level, output format, dimensions, pipeline fingerprint.
- AE/AWB request and observed result states, image/capture timestamps, original-byte digest and byte count.
- Android attestation security level, certificate-chain verification result, challenge binding, verified-boot state and certificate status-list freshness.
- Play Integrity package/request hash/timestamp, app recognition, licensing and device-integrity labels. Never store raw tokens, private keys, raw certificate secrets or user photos in test reports.
- Server receipt ID, verifier policy version, inference/receipt outcome, negative-test results and reviewer sign-off.

## Exit criteria

P0.6 is complete only when a reviewed physical-device report covers at least one current Pixel, one Samsung, and two distinct low-cost Android devices, plus one authorized negative device; includes at least two camera pipelines per device where available; and passes the positive/negative security protocol. Quantitative DSI colour acceptance remains a separate spectrophotometer and population-validation gate, even after P0.6 passes.
