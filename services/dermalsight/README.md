# DermalSight and DSI

**Status: DSI purpose-authorized preview APIs are implemented. Real visual inference remains blocked until immutable model assets are provisioned and pass their task-specific validation gates. DSI does not persist profiles, train global models or render corrected appearances.**

DermalSight owns non-diagnostic cosmetic skin analysis and clinically sensitive visual attributes. DSI (DermalSight Intelligence) is a governed extension inside this service, not a second service, profile database or competing intelligence authority.

## DSI capability map

| Priority | Capability | Current implementation state | Acceptance evidence still required |
|---|---|---|---|
| 1 | Skin-tone intelligence | Face/body skin-region segmentation preview is wired; no colour value is computed | Calibrated colour pipeline, physical reference processing, repeatability/uncertainty report and held-out evaluation across skin-tone, camera and lighting slices |
| 2 | Facial geometry | 478-point Face Landmarker provider and stateless ratio preview exist; face shape and hairline remain unclassified | Immutable licensed asset, annotation agreement, pose/occlusion/device subgroup evaluation and independent geometry validation |
| 3 | Body-tone alignment | Coarse face-skin/body-skin masks only; no individual neck/chest/arm/hand/leg alignment | Region-specific segmentation, calibration, uncertainty and same-session regional validation |
| 4 | Shared intelligence API | Private, purpose-authorized preview APIs use Identity Learning consent verification; no profile read/write API | Service-to-service subject scoping, export, revocation/deletion propagation and consumer contract tests |
| 5 | Global learning | Separate global-training consent scope and aggregate-only evaluation contract; no dataset ingestion or training | Rights-provenance registry, privacy-preserving dataset pipeline, independent held-out/subgroup validation and rollback/deletion procedure |
| 6 | Appearance corrector | Cosmetic-only correction plan contract exists; no renderer or output route is enabled | Licensed renderer, separate user consent, identity-preservation/geometry-drift evaluation and private output lifecycle |

The capability endpoint is GET /api/v1/dsi/capabilities. The authenticated POST /api/v1/dsi/capture-plan returns guidance only and accepts no media. Two additional private endpoints are now available: POST /api/v1/dsi/face-geometry-preview and POST /api/v1/dsi/skin-region-preview. They require the dedicated DSI internal bearer and an exact, active, unrevoked, expiring Identity Learning consent bundle bound to the same subject, version and resource. They stream uploads to the isolated Vision DSI worker and return only provisional geometry ratios or skin-region coverage. They do not create or persist user profiles, retain original media, enable global training, or authorize appearance rendering.

## Architectural ownership

- DermalSight remains the canonical owner of derived cosmetic skin signals and DSI assessment contracts.
- DSI owns no enrollment identity, account record, raw-photo store, wardrobe, product catalog or final product-display decision.
- Virtual Twin remains the owner of the user's authorized body representation. DSI can provide validated, purpose-authorized measurements through a future service contract; it cannot write Twin assets directly.
- USI/TAL own positive preference state and temporal learning. DSI does not silently write preferences.
- CAL remains the final product-display authorization authority. DSI measurements are evidence, never permission to display or purchase.
- The existing platform-wide Intelligence Service/CIL governs registered evidence and rights. DSI does not create another general-purpose collective-intelligence registry.

## Controlled capture planning

The authenticated POST /api/v1/dsi/capture-plan endpoint accepts only a user's selected assessment types, selected body regions, tone-capture mode and whether optional video guidance is wanted. It returns capture instructions; it accepts no image or video bytes, creates no consent receipt and performs no inference.

Facial geometry can be requested without tone or body analysis. Body regions are explicitly selected; full-body exposure is not required. Left/right three-quarter face views are optional. Video is guidance-only and remains unprocessed. For calibrated CIELAB capture, the user must have a supported physical colour-reference card; without it, the user can select relative same-session comparison instead. The service never silently downgrades a calibrated request.

Analysis consent is separate for each purpose and must be verified before any future media-processing route is called. Global training consent is never included in capture consent. Users can skip DSI or any optional view and continue using Cirvanna discovery.

## Perception preview integration

DermalSight delegates image work to the existing Vision Intelligence service rather than embedding MediaPipe or duplicating its model runtime inside DermalSight. Vision exposes a dedicated private DSI surface:

- GET /v1/dsi/ready verifies both configured and successfully loaded task assets, including the segmenter's exact label map. It is independent of the CLIP/Commerce marketplace readiness gate.
- POST /v1/dsi/face-landmarks returns exactly one face's 478 normalized landmarks. No face embeddings, blendshapes, facial transformation matrices, identity matching, recognition or age estimation are computed. Zero or multiple faces fail closed.
- POST /v1/dsi/skin-segmentation returns pixel-aligned face-skin and body-skin masks plus non-calibrated segmentation diagnostics. It does not calculate a skin-tone value.

Vision requires DSI_VISION_WORKER_TOKEN (at least 32 bytes). DermalSight calls it using DSI_VISION_API_URL and DSI_VISION_API_TOKEN, with TLS required except for loopback-only tests, redirects disabled and environment proxy inheritance disabled. Restrict these endpoints to the private service network as well as requiring the bearer credential.

Model assets are provisioned outside Git and must all have a version, local asset path and SHA-256 pin:

- DSI_FACE_LANDMARKER_MODEL_PATH, DSI_FACE_LANDMARKER_MODEL_SHA256, DSI_FACE_LANDMARKER_MODEL_VERSION.
- DSI_SKIN_SEGMENTER_MODEL_PATH, DSI_SKIN_SEGMENTER_MODEL_SHA256, DSI_SKIN_SEGMENTER_MODEL_VERSION.

Missing, unreadable or digest-mismatched assets fail closed. The model label map must be exactly background, hair, body-skin, face-skin, clothes, others. The current preview derives only pixel-distance ratios from the face landmarks; it deliberately leaves face shape and hairline unclassified and reports uncertainty as uncalibrated. Coarse body-skin segmentation is not segmentation of individual body regions. Thus priorities 1 and 3 remain blocked.

DermalSight verifies consent with Identity Learning at POST /internal/v1/consents/verify using IDENTITY_LEARNING_API_URL and IDENTITY_LEARNING_API_TOKEN. DSI requires exact subject, consent bundle, consent version, resource, active grant, non-revocation, every required scope, receipt IDs and a future expiry. Legacy no-expiry receipts cannot authorize DSI image processing. The new scopes are independent:
- cosmetic skin preview: image_processing + skin_analysis;
- facial geometry: image_processing + facial_geometry_analysis;
- body-tone preview: image_processing + body_tone_analysis + body_measurements;
- appearance correction: image_processing + appearance_correction;
- global training: global_model_training only.

No enrollment consent, one analysis purpose, or image_processing consent alone grants any other DSI purpose. DSI does not create or extend consent receipts. The trusted gateway must obtain the subject identifier from its authenticated session and pass the exact resource to be analyzed.

The current skin-segmentation model only partitions face skin and body skin at a coarse level. It cannot distinguish neck, chest, forearms, hands or legs as independent calibrated skin-tone regions. A segmentation confidence score is not a calibrated probability and is not an uncertainty interval for skin colour. No CIELAB conversion or exact shade claim is currently made.

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

The canonical Identity Learning service verifies DSI receipts, including the subject binding, exact purpose-scope set, bundle, version, exact resource, expiry and revocation. DSI refuses legacy receipts without an expiry for these sensitive previews. The appearance-correction contract separately checks a verified, active, unrevoked, current receipt; no public correction route exists.

Consent purposes are distinct: cosmetic skin analysis, facial geometry analysis, body-tone analysis, appearance correction and global model training. Consent for enrollment or cosmetic analysis must never imply consent for model training. Global-learning records are aggregate-only, require independent review and a 30-contributor reporting floor, and forbid source images, face templates, subject identifiers and individual profiles. The cohort floor is a disclosure safeguard, not proof of statistical representativeness or permission to train.

Raw enrollment media is processed in memory and is not persisted by DSI or the Vision DSI worker. Video ingestion and frame extraction remain disabled; capture-plan video guidance is optional and informational only. Preview outputs are marked no-store/private. No DSI route writes a Twin, avatar, CDN asset, public image or persistent profile. Global training and appearance correction remain disabled.

## Existing DermalSight API

- GET /health is liveness only.
- GET /ready is 503 unless the existing API token and approved model bundle are configured.
- GET /capabilities reports actual existing model availability.
- POST /api/v1/analyze requires bearer authentication and the existing cosmetic analysis consent contract.
- POST /api/v1/dsi/face-geometry-preview requires exact facial_geometry_analysis consent and returns unvalidated geometry ratios only.
- POST /api/v1/dsi/skin-region-preview requires either cosmetic_skin_analysis or body_tone_analysis consent and returns coarse segmentation coverage only.
- DSI preview routes require DSI_INTERNAL_API_TOKEN, while Identity Learning and Vision use separate internal tokens.
- The existing ONNX adapter and signed validation report gate apply only to cosmetic_skin_attributes; they do not validate the Face Landmarker or segmenter. They do not establish DSI skin-tone calibration, facial geometry, body segmentation or rendering capability.

Images are decoded in memory, bounded by byte and pixel limits, and not persisted by this service. Missing/invalid model artifacts fail closed; heuristic fallback is prohibited.

## Run the service

Use Python 3.12. Install runtime dependencies with python -m pip install -r requirements.txt. Configure DERMALSIGHT_API_TOKEN and DSI_INTERNAL_API_TOKEN with independently generated secrets. Configure IDENTITY_LEARNING_API_URL / IDENTITY_LEARNING_API_TOKEN and DSI_VISION_API_URL / DSI_VISION_API_TOKEN as private service-to-service credentials. Configure the DSI Vision model paths, versions and SHA-256 values in the Vision deployment; never commit weights or secrets. For the existing skin-attribute API, configure DERMALSIGHT_MODEL_PATH, DERMALSIGHT_MODEL_MANIFEST_PATH, DERMALSIGHT_VALIDATION_REPORT_PATH and DERMALSIGHT_VALIDATION_SIGNING_KEY. Start the service with uvicorn app.main:app --host 0.0.0.0 --port 8000.

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
