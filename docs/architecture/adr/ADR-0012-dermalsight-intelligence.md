# ADR-0012: DSI as a governed DermalSight extension

- Status: Accepted
- Date: 2026-11-14
- Owners: DermalSight / Cirvanna architecture

## Context

Cirvanna proposes a unified intelligence capability for cosmetic skin-tone estimation, facial geometry, body-region tone alignment, shared authorized profile attributes, consent-based global model improvement and identity-preserving cosmetic previews.

The existing DermalSight service owns non-diagnostic cosmetic skin signals and already has a hash-verified ONNX adapter, signed validation-report gate, explicit-consent requirement and in-memory image handling. Its current model task is only cosmetic_skin_attributes. It does not include a validated tone-calibration model, facial-landmark model, body-region segmenter or appearance renderer.

## Decision

DSI is implemented as a bounded module within services/dermalsight, not as a new repository or independent service. It reuses DermalSight's domain ownership and exposes versioned contracts for measurements, evidence, consent and capability readiness.

The initial increment adds:
- strict contracts for controlled capture evidence, CIELAB estimates and Delta E uncertainty;
- body-region-specific tone observations with explicit calibrated, relative-only and review-required states;
- facial geometry proportions and shape categories with uncertainty intervals, excluding identity templates and embeddings;
- purpose-specific consent contracts and fail-closed consent checks;
- aggregate-only global-learning evaluation records, not a live training ingestion path;
- cosmetic-only appearance correction plans that require identity preservation and prohibit geometry alteration and public output;
- a read-only capability endpoint that reports every unvalidated capability as blocked;
- an authenticated capture-plan endpoint that returns user-selected guidance without accepting or processing media, with explicit optional video and region choices;
- dedicated, separately authenticated Vision DSI endpoints that lazily load SHA-256-pinned Face Landmarker and skin-segmentation assets;
- DermalSight preview endpoints that verify exact-purpose consent against Identity Learning before forwarding an image to Vision; these return unvalidated geometry ratios or coarse mask coverage, never a saved profile.

## Invariants

1. No inference result is represented as measured truth without task-specific, signed validation evidence.
2. Exact skin tone is not claimed from uncontrolled images. Absolute colour requires controlled capture, locked exposure/white balance, a known colour reference and a calibration report. Otherwise the observation is relative to a single capture session or marked for review.
3. Body regions are measured independently. Natural regional variation is preserved; the platform does not normalize every region to one colour.
4. Face geometry is used only for explicitly consented cosmetic personalization. Recognition, identity matching, age estimation and authentication are prohibited.
5. Enrollment, analysis and appearance-correction consent never imply global model-training consent.
6. Raw media, face templates, subject identifiers and individual profiles are not included in global-learning aggregates.
7. DSI outputs are evidence only. USI/TAL, Virtual Twin, Catalog and CAL retain their existing domain ownership.
8. Inference, profile exchange, training and rendering remain disabled until their separate gates pass.
9. DSI cannot deny a user's aesthetic or self-discovery request. Previous preferences and inferred appearance attributes are advisory, never hard filters; optional analysis failure or declined consent must fall back to non-DSI discovery.
10. DSI never updates persistent preferences without an explicit user save action through the canonical USI/TAL workflow.
11. Capture planning is not consent or inference. Video, additional views and body regions remain optional/user-selected; no media upload route is enabled by the capture-plan endpoint.
12. A calibrated CIELAB capture request requires a supported physical colour reference. The system must not silently relabel an uncalibrated capture as absolute tone.
13. Each DSI visual operation must verify the exact, active, unrevoked, resource-bound Identity Learning consent bundle and a future expiry at request time. DSI must not accept a boolean consent claim as proof.
14. The Vision DSI worker uses dedicated authentication, exact model artifact SHA-256 pins, in-memory image handling and no-store responses. It is independent of marketplace/CLIP readiness.
15. Current Face Landmarker ratios are unvalidated previews; current segmentation is coarse face/body skin coverage, not a calibrated colour model or regional body-tone analysis. DSI must not claim face-shape, hairline, exact tone or region-level alignment until independently validated.

## Consequences

- DSI can evolve without duplicating DermalSight, the platform-wide Intelligence Service or Virtual Twin.
- Consumers receive stable, versioned contracts instead of private implementation details.
- Current model assets do not satisfy DSI acceptance criteria; no user-facing claims are enabled.
- A later shared profile API requires authenticated service identities, subject-scoped authorization, purpose enforcement and lifecycle propagation. It cannot be activated by exposing an unauthenticated read endpoint.
- Global learning needs a distinct consent/rights registry and independent held-out evaluation. Aggregate reporting thresholds alone do not authorize training.
- Appearance correction requires proof of identity preservation and private output lifecycle at the generated-asset level.
- The discovery autonomy policy keeps users free to explore beyond prior preferences, while still refusing unauthorized processing of protected media.
- The initial perception slice reuses Vision Intelligence and Identity Learning and does not introduce duplicate model-serving or consent stores.
- No DSI model weights are committed. Runtime readiness requires out-of-band versioned assets and digest checks.
- Model/provider integration is not equivalent to accuracy validation. Tone calibration, body-region alignment, persistent profiles, global learning and appearance correction remain blocked.
