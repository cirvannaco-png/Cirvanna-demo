# DSI Android physical-device acceptance protocol

**Status: NOT RUN.** No physical-device or production Google Play Integrity verdict is claimed by the source-code and CI work in this branch.

## Purpose

Validate the exact Android capture pipeline on real hardware before the SDK can be called an accepted capture provider. A passing software build or mocked verifier test does not establish that a device key is hardware-backed, the camera result belongs to the uploaded image, the OEM pipeline is colour-stable, or Play Integrity recognizes the production application.

## Entry criteria

- A release-signed Cirvanna Android application is installed from the intended distribution channel.
- The final package name, Play app-signing certificate SHA-256 and minimum version code are pinned in the Vision deployment.
- The server-side attestation verifier has been built from the exact pinned Google source commit and security-reviewed.
- Google Play Integrity Standard API is enabled for the linked Google Cloud project; production service identity has only the required decode permissions.
- Identity Learning challenge and receipt migrations are deployed in a non-production environment with an independently rotated DSI capture credential.
- No device serial, IMEI, advertising ID, raw EXIF, or unnecessary location data is collected in the test record.
- Each image capture is made under explicit, purpose-specific test consent. Source bytes remain in memory unless the protocol explicitly authorizes a secured test fixture.

## Required device matrix

Do not certify a manufacturer or marketing family from one handset. Test the exact device/camera/OS/runtime pipeline. Complete at least one physical unit in each relevant class before release review, and add units when field variation is detected.

| Matrix slice | Required coverage | Status |
|---|---|---|
| Google reference device | Current supported Android release; front and rear camera paths | NOT RUN |
| Samsung mid-range device | At least one front and one rear camera path | NOT RUN |
| Low-cost Android device | Include lower-cost devices used in target markets | NOT RUN |
| Transsion / Tecno / Infinix | Representative device and each selected camera module | NOT RUN |
| Xiaomi / Redmi or equivalent OEM | Camera pipeline and image processing behaviour | NOT RUN |
| Older supported Android release | Minimum supported OS and security patch policy | NOT RUN |
| Multi-camera handset | Logical and physical camera IDs; each lens is independently recorded | NOT RUN |
| RAW-capable device | RAW_SENSOR availability, DNG path and calibration metadata | NOT RUN |
| JPEG-only device | Exact ICC/profile path and relative-only fallback until validated | NOT RUN |

## Per-device procedure

1. **Identify the pipeline without collecting direct hardware identifiers.** Record manufacturer/model as reported, OS/API/security-patch version, Camera2 camera ID, logical/physical camera IDs, facing/lens role, hardware level, output format, resolution, SDK version and canonical pipeline fingerprint.
2. **Test camera capability claims.** Record actual CameraCharacteristics, available request/result keys, AE/AWB lock support, RAW support and sensor colour-calibration metadata. A missing key is unsupported, not guessed.
3. **Verify capture-result association.** Capture unlocked preview frames until AE/AWB converge, request AE/AWB locks, and retain the TotalCaptureResult associated with the still frame. Verify that the still Image.timestamp equals that result's SENSOR_TIMESTAMP. Upload a byte-for-byte image whose SHA-256 and byte count match the signed manifest.
4. **Verify Android Key Attestation.** Create a new server-challenge-bound Keystore key for each capture. Confirm the server validates the complete chain, challenge, expected application ID/signing certificate, TEE/StrongBox security level, verified boot state and locked bootloader. Confirm software-backed keys and wrong application IDs fail.
5. **Verify Play Integrity.** Obtain a fresh Standard API token whose requestHash is the canonical manifest SHA-256. Confirm decoded server-side PLAY_RECOGNIZED, expected package and certificate, LICENSED, a policy-approved device-integrity label and fresh request timestamp.
6. **Verify persistence and replay protection.** Confirm Vision creates a receipt only after both independent verifiers pass, Identity stores exact digest/consent bindings, receipt verification checks live consent, and a second consumption attempt fails.
7. **Verify image pipeline limitations.** Record whether HDR, tone mapping, beauty filters, denoise, sharpening, colour transforms or vendor post-processing can be observed or controlled. Use not_exposed_by_camera2 when the platform cannot prove state; do not translate unknown into disabled.
8. **Run physical colour protocol separately.** Use calibrated diffuse illumination, an in-frame physical reference chart, controlled white balance/exposure, and traceable spectrophotometer references. Record only data allowed by the laboratory's data-minimization protocol; never record handset serial/IMEI.
9. **Run subgroup and repeatability analysis.** Include measured skin-colour ranges across the intended operating population, multiple sessions, operators, lighting conditions and physical units. Report per-slice error, bias, repeatability, confidence intervals and failure rates. Do not conceal a failing slice with an aggregate score.
10. **Test lifecycle and privacy.** Denied consent, cancelled capture, expired challenge, revoked consent, app reinstall/update, process death, upload retry, deletion, memory cleanup, telemetry/log redaction and retention purge.

## Adversarial acceptance matrix

| Attack / fault | Required outcome | Status |
|---|---|---|
| Modify one image byte after manifest signing | Reject before inference and before Identity receipt creation | NOT RUN ON DEVICE |
| Replace image while preserving filename/MIME | Reject digest mismatch | NOT RUN ON DEVICE |
| Change challenge ID or nonce | Reject challenge/attestation mismatch | NOT RUN ON DEVICE |
| Replay consumed challenge or receipt | Reject replay or expired/revoked receipt | NOT RUN ON DEVICE |
| Substitute self-signed or wrong-root certificate chain | Reject chain | NOT RUN ON DEVICE |
| Alter leaf certificate or manifest signature | Reject signature | NOT RUN ON DEVICE |
| Use software-backed Android key | Reject trusted capture | NOT RUN ON DEVICE |
| Unlock bootloader or fail verified boot | Reject trusted capture | NOT RUN ON DEVICE |
| Use wrong package, app signer or old version | Reject application identity | NOT RUN ON DEVICE |
| Play Integrity says unrecognized app | Reject | NOT RUN ON DEVICE |
| Play Integrity says unlicensed app | Reject | NOT RUN ON DEVICE |
| Play Integrity lacks accepted device verdict | Reject | NOT RUN ON DEVICE |
| Use stale, revoked or suspended attestation certificate | Reject; no stale status-list fallback | NOT RUN ON DEVICE |
| Google status or Play Integrity provider unavailable | Fail closed; no receipt | NOT RUN ON DEVICE |
| Change user, consent bundle, resource or analysis purpose | Reject exact-scope mismatch | NOT RUN ON DEVICE |
| Directly call Vision endpoint with worker token but no receipt | Reject before model inference | AUTOMATED TEST REQUIRED |
| Directly call DermalSight legacy analysis endpoint without receipt | Reject before model load | AUTOMATED TEST REQUIRED |

## Run record template

Create one record per exact pipeline (not one per phone name). Use pseudonymous test-run IDs; never use hardware serials or IMEIs.

| Field | Value |
|---|---|
| Test-run reference | NOT RECORDED |
| Device make/model | NOT TESTED |
| Android version / API / security patch | NOT TESTED |
| Camera ID / physical ID / lens role | NOT TESTED |
| Output format / resolution / colour profile digest | NOT TESTED |
| DSI SDK / app version / signing certificate digest | NOT TESTED |
| Hardware key security level | NOT TESTED |
| Verified boot / device locked | NOT TESTED |
| Play app recognition / licensing / device verdict | NOT TESTED |
| AE/AWB lock and timestamp pair | NOT TESTED |
| Exact image SHA-256 / manifest SHA-256 | NOT TESTED |
| Google root / revocation status version or retrieval time | NOT TESTED |
| Spectrophotometer / chart protocol report | NOT TESTED |
| Per-slice validation report digest | NOT TESTED |
| Independent reviewer / date | NOT TESTED |
| Decision | NOT QUALIFIED |

## Promotion rule

A passing physical capture test only proves the tested app/device/camera/OS/runtime scope. It does not certify another camera lens, OS build, capture SDK version or OEM image pipeline. Promotion to a device baseline requires an independently reviewed, versioned record and separate colour-validation evidence. capture_candidate is not colour_validated. Cross-polarized capture requires a separate optical report. Absolute colour output remains disabled until per-region, per-lightness-range and per-population validation passes.
