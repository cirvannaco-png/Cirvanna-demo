# Virtual Twin shared-package archive review — 21 November 2026

## Decision

**Do not import `cirvanna-virtual-twin` v2.0.0 wholesale.** The archive is a reconstructed shared Python contracts/platform library, not a Virtual Twin reconstruction or rendering implementation. Its useful ideas must be reconciled selectively against the current service owners and contracts. No runtime capability or readiness flag is changed by this review.

The review target is the uploaded `cirvanna-virtual-twin (1).zip`, whose root package is `cirvanna-virtual-twin/`.

## Current canonical ownership in Cirvanna

| Concern | Canonical owner | Integration constraint |
|---|---|---|
| Pose inference and Twin orchestration | `services/virtual-twin` | Current `/twin` output is an ephemeral pose skeleton, not a saved full-body Twin. |
| Persistent Twin metadata, ownership, versions and deletion outbox | `services/twin-registry` | Do not add a second Twin database or registry. Registration is restricted to independently validated `full_body_mesh` assets. |
| Private binary assets and derived-asset lifecycle | `services/asset-service` | Do not introduce another object store or expose stable/public source URLs. Provider-backed bucket/origin/CDN verification remains outstanding under issue #121. |
| Independent mesh preflight | `services/twin-mesh-validator` | Structural preflight is not equivalent to validated body coverage, calibrated scale, privacy or non-embedding proof. |
| Render jobs and renderer orchestration | `services/virtual-try-on` | Keep unavailable until a commercially approved, pinned, actually evaluated renderer and production asset/consent checks exist. |
| Purpose-bound consent | `services/identity-learning-service` | Preserve `image_processing`, `body_measurements`, and `virtual_twin_storage`; do not create aliases or bypass server-side receipt verification. |
| Fit confidence and product decision evidence | `packages/fit-intelligence/fci` plus decision services | The archive's `FitConfidence` DTO is not a replacement for FCI and must not turn a preview into a fit guarantee. |
| PNELLY daily looks and wardrobe context | Xari/PNELLY, Wardrobe and Marketplace BFF | A render must bind to look/version, wardrobe snapshot/version, Twin/version, consent and renderer/model version. Styling remains useful when rendering is unavailable. |

The current `main` head at this reconciliation pass was `a344295a56a40e20f8852b9f1358ea7961f25444`, after the selective garment-fit integration in PR #231. This review remains an archive disposition record, not a claim that the complete Twin reconstruction/rendering pipeline is available.

## Archive contents and disposition

### 1. Domain contracts

The archive supplies Pydantic v2 models for body capture, measurements, measurement uncertainty, body mesh/profile, garment descriptors, fit summaries, outfits, calibration responses and inference envelopes.

**Potentially reusable after reconciliation:** `BodyCapture`, `Measurements`, `MeasurementUncertainty`, `BodyProfile`, and the calibration response mapping. These are not yet adopted because the repository does not contain the claimed `cirvanna-body-calibration` producer/service or a verified producer-owned schema artifact. The service's current `/twin` endpoint does not return calibrated measurements and correctly reports that capability as unavailable.

**Not accepted as canonical:** the archive's `FitConfidence` and inference wire models. FitConfidence has a separate FP/MCR/OAS representation and is not the repository's FCI contract. The archive itself says its inference models were reconstructed from an incomplete export and that Skin/GarmentCompatibility are placeholders.

### 2. Calibration adapter

`to_body_profile()` maps a calibration v2 response to a normalized body profile. The mapping is a plausible anti-corruption-layer pattern, but its current tests and claims need correction before adoption:

- `CalibrationResult`, `CalibrationMeasurement` and `CalibrationQuality` use `extra="ignore"`, while the README claims producer-added fields fail compatibility tests. The test assertion checks that fixture keys are a subset of model fields, so it does not detect unknown producer keys.
- The adapter accepts `persisted=false` because it does not require or explicitly model persistence semantics.
- Major-version parsing uses `split(".")[0]`, which is weaker than validating a complete supported version string.
- Uncertainty values over 10 cm are silently truncated to 10 cm when building `MeasurementUncertainty`; the original uncertainty should not be hidden. Reject or preserve it with an explicit contract decision.
- The sample fixture is a static copied JSON response. It is not proof that a live producer currently emits this exact schema.

Before adoption, obtain the producer source and its generated OpenAPI/JSON Schema or contract fixture, then add consumer-driven compatibility tests that fail on unexpected breaking and additive changes according to an explicitly chosen compatibility policy.

### 2a. Selective garment-descriptor adaptation (PR #231 — merged)

[PR #231](https://github.com/cirvannaco-png/Cirvanna-demo/pull/231) has now merged a selective adaptation of the useful garment-construction subset of the archive's `GarmentDescriptor` into Catalog's canonical, versioned `product_intelligence.garment_fit` metadata. The integration does not import the shared package or its reconstructed calibration/inference layer.

This is **not a wholesale package import**:
- Catalog remains the owner of product and canonical size-variant identity.
- Every spec binds to an active same-product canonical variant and an exact normalized `size` option.
- Finished-garment dimensions are explicitly normalized to millimetres. The archive's example model does not declare units, so its example numeric values must not be copied directly.
- CIL authorizes every spec using an exact registered evidence ID, source ID, finished-product scope, allowed evidence grade/source type, and current commercial rights.
- No body measurement, fit score, FCI estimate, CAD pattern, color vector, body-shape inference, or Try-On behavior is imported or enabled.

PR #231 passed Catalog, Intelligence Service/CIL, architecture and cross-service contract workflows before merge. The source archive itself remains unmodified and is not added as a runtime dependency.

### 3. Platform utilities

The archive includes structlog setup, Prometheus middleware/metrics, OpenTelemetry tracing, an asyncio circuit breaker/retry helper, Fernet key rotation, JWT/OAuth2 helpers and a typed HTTP inference client.

These utilities are not wired into the current Virtual Twin, Twin Registry, Asset Service or Try-On runtime. They must not be copied in as an unused second platform layer. Specific review findings:

- `CircuitOpenError.retryable = True` conflicts with the module's stated non-retry behavior. `retry_async()` special-cases the exception, but the public property remains misleading.
- The inference client is explicitly marked reconstructed; provider paths/envelopes are not verified. It also needs explicit tests for malformed JSON, redirect behavior, URL trust policy, timeout classes, and response-size bounds before runtime use.
- OAuth token acquisition needs an explicit redirect policy and trusted endpoint configuration; credentials must never be forwarded to an untrusted redirect target.
- Logging configuration replaces root handlers globally and has no default sensitive-field redaction policy. It must not be introduced without a service-level logging and PII/secret-redaction review.
- Metrics/tracing need service lifecycle, cardinality, duplicate registration and exporter configuration review before being added to production services.
- Fernet rotation is useful as a primitive, but no archive code demonstrates its integration with Cirvanna's existing secret/key-management lifecycle or database field ownership.

The existing services should retain their established authentication, consent, storage and provider boundaries. A later platform-library proposal must be separately tested and adopted only where a service actually consumes it.

## External provider contract cross-check — 20 November 2026

This check compares the archive's expected calibration contract with public provider documentation. It is a technical integration assessment, not procurement approval or permission to transmit user photographs.

### Bodygram Platform

The current public REST contract documents:

- A photo scan requires age, gender (`male` or `female`), height in millimetres, weight in grams, and front/right-side JPEG photos.
- A successful response includes measurements as `{name, unit, value}`, plus a base64 OBJ avatar. Body-composition and posture outputs are available on photo scans.
- The documented response does not include per-measurement uncertainty, confidence tier, or a calibrated quality score.
- The server-side organization API key must never reach the browser. A short-lived scoped scan token is intended for the client scanning flow.
- `DELETE /api/orgs/{ORG_ID}/scans/{SCAN_ID}` permanently deletes the scan and derived data, including the avatar, measurements and original input. Deletion is not idempotent; an already-deleted scan returns 404.

**Integration consequence:** the archive's `CalibrationResult` is not a direct Bodygram response model. A mapping must not manufacture uncertainty, confidence tiers or quality scores that the provider did not return. Cirvanna would need an independently evaluated calibration/uncertainty layer before Bodygram measurements could be represented as calibrated fit evidence. Its OBJ avatar would also need a controlled conversion to the registry's private GLB 2.0 boundary and the full independent mesh-validation chain. The age/gender fields require explicit product, consent and legal review rather than inference.

Official contract: https://docs.bodygram.com/platform/endpoints

### 3DLOOK FitXpress

The vendor's current public FAQ describes two smartphone photos and a short profile producing 80+ measurements, body-composition estimates and a 3D model. Its documented profile fields include gender and height; weight is optional for body-composition outputs.

Its FAQ states that photos are deleted immediately or within 30 days depending on customer instructions, while measurements and 3D models are retained on an ongoing basis unless contract terms or a deletion request change that. It describes AWS hosting primarily in us-west-2 and partly in us-east-1. Full API documentation and subprocessor detail are available through procurement/security review; the public FAQ expressly does not replace a signed DPA or customer agreement.

**Integration consequence:** this remains the first body-scan pilot candidate recorded in the existing provider qualification assessment, but only after a signed DPA/order form sets immediate source-photo deletion, explicit output retention/deletion SLAs, data regions, subprocessors, permitted purposes, output rights, and no training use absent separate authorization. The private provider API schema must be obtained before writing an adapter.

Official data lifecycle and FAQ: https://3dlook.ai/content-hub/fitxpress-data-privacy-security-regulatory-faq/

### Avatar SDK

Its current product page describes a single-photo API producing rigged full-body avatars with facial blendshapes and GLB/glTF or FBX output, with cloud and on-premise options.

**Integration consequence:** this is an appearance/presentation-layer candidate only. It is not a substitute for calibrated anthropometric measurements or fit evidence. It still requires commercial terms, source-image deletion, DPA, data region, model/version pinning and output-rights review.

Official product information: https://avatarsdk.com/avatar-api/

### SAM 3D Body

The public repository describes single-image full-body mesh recovery and publishes inference code, but its Hugging Face checkpoints are gated. The model listing identifies a 2.11 GB checkpoint; the installation guide requires Python 3.11, PyTorch, Detectron2 and additional vision dependencies. The connected Hugging Face file operation returned access denied for the gated model files, so the checkpoint could not be downloaded or run in this integration pass.

**Integration consequence:** retain SAM 3D Body as a self-hosted research benchmark, not an enabled production provider. Public source code without authorized checkpoint access is not a runnable model. License acceptance, dependency review, GPU runtime, subgroup evaluation and independent validation remain prerequisites.

Official model: https://huggingface.co/facebook/sam-3d-body-dinov3
Inference code and installation: https://github.com/facebookresearch/sam-3d-body

### Provider decision

- Do not select or enable an external provider from public marketing claims alone.
- Keep 3DLOOK as the first body-scan procurement/pilot candidate and Bodygram as a measured alternative; compare them with the same consented evaluation protocol and pre-registered metrics.
- Treat Avatar SDK as a separate appearance candidate, not a body-measurement authority.
- Keep SAM 3D Body as a research baseline until gated checkpoint access and full model-stack qualification are complete.
- Do not send any Cirvanna user media to any of these providers in this pass.

The archive's calibration adapter must remain unconnected until one provider's producer-owned schema is obtained and its measurement uncertainty, confidence and capture-quality semantics are verified.

## Required integration sequence

1. Keep the current canonical service ownership and the full-body-mesh-only registry rule.
2. Obtain and verify the real body-calibration producer contract before introducing the archive's calibration DTO/adapter.
3. Reconcile any normalized body-profile representation with FCI's evidence requirements; preserve measurement provenance, uncertainty, capture quality, consent scope and model/version lineage.
4. Do not infer fit from pose landmarks or from the archive's placeholder fit/inference DTOs.
5. Keep generation unavailable until a licensed/pinned full-body model, private asset ingestion, independent geometric/body/privacy validation and registry authorization are all verified.
6. Keep Try-On unavailable until renderer licensing, exact model/weight pinning, atomic idempotent job reservation, post-render consent/ownership revalidation and private output persistence are proven.
7. Complete the three-role PNELLY render journey with per-role failure states, no placeholder substitution, and strict binding to current look and wardrobe versions.
8. Close issue #121's provider-backed binary access, publication, revocation and deletion checks before claiming private media is safe in production.

## Validation and status

- Archive tests run locally against the exact ZIP: `tests/test_contracts.py`, `tests/test_adapter.py`, and `tests/test_layering.py` passed (**13 passed**). Platform-dependent tests could not be collected because `structlog` is missing. The root `cirvanna_twin.platform.__init__` eagerly imports auth, encryption, inference, logging and resilience modules, so even importing one platform submodule requires optional dependencies from the whole platform extra. This contradicts the pyproject's optional-extra separation and must be fixed before library adoption. No complete-suite pass is claimed.
- The archive README itself lists reconstructed inference contracts and missing upstream AIS/GSIS/DTAE/FCE service code.
- Repository inspection confirms the canonical Virtual Twin API currently advertises full-body reconstruction, persistent Twin generation/preview and calibrated measurements as unavailable. This review does not change those capabilities.
- No production provider, model, secret, database, storage bucket, feature flag or deployment configuration was changed.

## Related work

- Issue #108 — PNELLY daily looks with persistent Virtual Twin and validated renderer.
- Issue #121 — binary media storage/delivery privacy enforcement.
- PR #124 — private Asset Service foundation (already merged; provider-backed storage security remains outstanding).
- PR #109 — registry foundation work was closed unmerged; the canonical registry implementation must be assessed from current `main`, not copied from that stale branch.

**Outcome:** archive reviewed; no code from it is promoted into runtime. The next valid code integration is producer-backed calibration contract adoption or a separately scoped, service-consumed platform primitive—not a wholesale package import.
