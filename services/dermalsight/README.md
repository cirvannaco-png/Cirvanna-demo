# DermalSight and DSI

**Status: DermalSight's original cosmetic-attribute API remains model-gated. DSI contracts and a read-only capability endpoint are implemented; DSI inference, profile exchange, learning and rendering are not enabled.**

DermalSight owns non-diagnostic cosmetic skin analysis and clinically sensitive visual attributes. DSI (DermalSight Intelligence) is a governed extension inside this service, not a second service, profile database or competing intelligence authority.

## DSI capability map

| Priority | Capability | Current implementation state | Acceptance evidence still required |
|---|---|---|---|
| 1 | Skin-tone intelligence | Typed calibrated/relative measurement contracts and controlled-capture requirements | Approved tone model, colour-reference calibration, repeatability/uncertainty report and held-out evaluation across skin-tone, camera and lighting slices |
| 2 | Facial geometry | Typed face-shape, hairline and proportion contracts with bounded estimates | Licensed landmark model, geometry agreement metrics, pose/occlusion/hairline failure analysis and privacy review |
| 3 | Body-tone alignment | Region-specific observations, capture-session binding and uncertainty contracts | Validated body-region segmentation and region-specific calibration/evaluation |
| 4 | Shared intelligence API | Versioned profile contract and capability surface | Service identity, subject-scoped authorization, purpose enforcement and revocation/deletion propagation |
| 5 | Global learning | Exact-purpose consent contract and aggregate-only evaluation record | Independent consent/rights registry, governed dataset workflow, held-out evaluation, subgroup reporting and rollback/deletion procedure |
| 6 | Appearance corrector | Cosmetic-only correction plan contract; geometry changes and public media output are prohibited | Licensed renderer, separate user consent, identity-preservation evidence and private output lifecycle |

The live capability endpoint is GET /api/v1/dsi/capabilities. It is informational only. It does not accept images, videos, profile reads, training examples or rendering jobs.

## Architectural ownership

- DermalSight remains the canonical owner of derived cosmetic skin signals and DSI assessment contracts.
- DSI owns no enrollment identity, account record, raw-photo store, wardrobe, product catalog or final product-display decision.
- Virtual Twin remains the owner of the user's authorized body representation. DSI can provide validated, purpose-authorized measurements through a future service contract; it cannot write Twin assets directly.
- USI/TAL own positive preference state and temporal learning. DSI does not silently write preferences.
- CAL remains the final product-display authorization authority. DSI measurements are evidence, never permission to display or purchase.
- The existing platform-wide Intelligence Service/CIL governs registered evidence and rights. DSI does not create another general-purpose collective-intelligence registry.

## Measurement rules

### Skin tone

Absolute colour measurements use CIELAB only when the capture is controlled, white balance and exposure are locked, a known colour reference is present, the quality assessment passes, and a calibration report is bound to that reference. Each measurement carries a Delta E uncertainty bound.

A capture without sufficient calibration may produce only a same-session relative observation. It must not be described as an exact or universal skin tone. Rejected or review-required captures cannot carry measurements. Face, neck, chest, arms, hands and legs remain separate regions; the system must not assume that natural regional pigmentation should be identical.

### Facial geometry

The contract contains cosmetic proportions, face-shape and hairline categories plus uncertainty intervals. It deliberately excludes face embeddings, identity templates, names, matching, age estimates and identity-verification use. Facial geometry is sensitive and must be protected as such even where it is not used to identify a person.

### Appearance correction

Only cosmetic previews are in scope: makeup placement, shade previews, concealer placement, hairstyle previews and cosmetic colour previews. The plan requires identity preservation, forbids facial-geometry modification, prohibits diagnostic claims and does not authorize public media output. Any future renderer must prove these invariants against the output asset, not merely set a request flag.

## User autonomy and self-discovery

DSI is advisory and must never become a beauty-standard gatekeeper. A user's requested look or aesthetic direction is authoritative for that exploration, even when it conflicts with previously saved preferences or DSI measurements. Prior preferences are suggestions, not hard constraints; users may experiment, reject advice, change direction, or request a style outside any inferred face-shape, tone or colour profile.

Failure, low confidence, missing model assets or declined consent for optional DSI analysis must not block ordinary self-discovery. The analysis may be skipped, marked unavailable, or offered after the user grants the separate purpose consent. The experience must continue through user-selected, manually guided or otherwise non-DSI routes. Privacy consent remains mandatory for processing the protected image or derived biometric-like measurements; autonomy does not mean processing without permission.

DSI must not silently rewrite USI/TAL preferences. A user's approval or correction is recorded only through the existing authorized preference workflow and an explicit save action. A one-time exploration is not a permanent preference.

DSI output cannot veto a user's chosen aesthetic, hairstyle, makeup, colour or accessory. It may explain trade-offs, confidence and alternatives, but the user makes the final decision. Any non-DSI safety or legal restriction must come from its own documented authority and must not be invented by DSI.

## Consent and learning boundaries

The privacy service must authenticate a receipt and verify its subject binding before a trusted internal caller constructs the DSI consent contract. The DSI helper checks active state, revocation, exact purpose and expiry; the appearance-correction plan also rejects receipts that are not currently verified, active and unrevoked. These checks are not a cryptographic signature verifier or a substitute for subject-binding verification.

Consent purposes are distinct: cosmetic skin analysis, facial geometry analysis, body-tone analysis, appearance correction and global model training. Consent for enrollment or cosmetic analysis must never imply consent for model training. Global-learning records are aggregate-only, require independent review and a 30-contributor reporting floor, and forbid source images, face templates, subject identifiers and individual profiles. The cohort floor is a disclosure safeguard, not proof of statistical representativeness or permission to train.

Raw enrollment media is not persisted by DSI. Video may be considered only as an in-memory source of selected frames after purpose-specific consent and capture-quality checks. No public image, avatar, CDN or sharing route is enabled by this contract.

## Existing DermalSight API

- GET /health is liveness only.
- GET /ready is 503 unless the existing API token and approved model bundle are configured.
- GET /capabilities reports actual existing model availability.
- POST /api/v1/analyze requires bearer authentication and explicit in-memory analysis consent.
- The existing ONNX adapter and signed validation report gate apply only to the declared cosmetic_skin_attributes task. They do not establish DSI skin-tone calibration, facial geometry, body segmentation or rendering capability.

Images are decoded in memory, bounded by byte and pixel limits, and not persisted by this service. Missing/invalid model artifacts fail closed; heuristic fallback is prohibited.

## Run the service

Use Python 3.12. Install runtime dependencies with python -m pip install -r requirements.txt. Configure DERMALSIGHT_API_TOKEN with a high-entropy secret from the deployment secret manager. For the existing skin-attribute API, configure DERMALSIGHT_MODEL_PATH, DERMALSIGHT_MODEL_MANIFEST_PATH, DERMALSIGHT_VALIDATION_REPORT_PATH and DERMALSIGHT_VALIDATION_SIGNING_KEY. Start the service with uvicorn app.main:app --host 0.0.0.0 --port 8000.

The model manifest binds the model version, preprocessing contract and output tensor names to the exact ONNX artifact SHA-256 digest. The detached HMAC-SHA256 validation report must match that digest and model version and pass the existing licensing, overall-quality, skin-tone-subgroup, lighting/device, privacy/security and claims gates. Keep model weights, validation reports and signing keys outside Git; store secrets in a managed secret store. The existing adapter accepts only the cosmetic_skin_attributes task and must not be reused as evidence for DSI tone calibration, facial geometry, body segmentation or correction rendering.

The provided container uses Python 3.12 and runs as a non-root user. Expose the service only behind trusted TLS ingress, request-size limits, rate limiting, monitoring and a reviewed service-authentication boundary.

## Run tests

From this directory:

- Install runtime dependencies: python -m pip install -r requirements.txt
- Install test dependencies: python -m pip install -r requirements-dev.txt
- Run tests: python -m pytest -q

Synthetic model fixtures and contract tests verify wiring and rejection rules only. They are not evidence of model accuracy, fairness, calibration or production readiness.

## Release blockers

Do not enable DSI image ingestion, profile sharing, global training or appearance rendering until the required evidence for that individual capability is signed, independently reviewed, deployed and exercised end-to-end. A capability must remain blocked when its model, calibration, consent, licensing, authorization or deletion evidence is missing.
