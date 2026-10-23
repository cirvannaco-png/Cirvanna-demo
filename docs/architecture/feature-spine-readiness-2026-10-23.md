# Cirvanna feature-spine audit and integration gates

**Audit date:** 23 October 2026  
**Reviewed main:** `d4f61184e4a7b34943c91bb2e46eaa86ccff9bc5`  
**Status:** feature contracts and mock-tested private inference boundary merged; production model-backed features remain gated.

## Canonical naming and boundary decisions

- **Xari** is the canonical assistant/orchestration name. Tari and Xyra are legacy source generations. Preserve them under source lineage; do not deploy multiple orchestrators.
- **CaTaCaCi/CAL** is the only display authorization authority. Xari, Wardrobe, Virtual Twin, Click It, and Virtual Try-On cannot independently approve candidate display.
- **NPL** is a hard-veto policy layer. Explicit exclusions and learned exclusions at their threshold cannot be overridden by ranking, outfit suggestions, Click It, or visualization.
- **Cultural identity** evaluates only declared user requirements against explicit product metadata. Do not infer religion, ethnicity, modesty, or cultural constraints from appearance, skin tone, names, geography, or demographic proxies.
- **FCI/confidence** is an evidence and calibration boundary, not a substitute for a validated fit-prediction model. Missing inputs, uncalibrated estimates, and incomplete metadata route to review.
- **Virtual Twin** owns user body representation and measurements. **Click It** owns product reconstruction from a user-provided product reference. **Virtual Try-On** owns garment/person rendering. They exchange opaque asset IDs and typed results; none owns policy arbitration.
- **Wardrobe** owns user-specific item records and their lifecycle. Catalog product metadata remains catalog-owned; other services must not write directly to wardrobe tables.

## Verified state after PR #56 and PR #57 merges

| Feature | Evidence in repository | Missing acceptance evidence |
|---|---|---|
| Tari/Xari | Authenticated Xari route-planning API, fixed intent/upstream allowlist, consent requirements, URL trust checks, capability reporting and contract tests. Tari/Xyra remain legacy names in source lineage. | Downstream execution adapters, tracing, rate limits and production identity/consent propagation. |
| NPL | Pure policy kernel; SQLAlchemy persistence API, PostgreSQL migration, unique rejection/correction event keys, authenticated API, HMAC-signed candidate-bound snapshots, and CI tests. Decision service verifies the NPL evidence HMAC; gateway can consume and verify snapshots when configured. | Deployed PostgreSQL integration/restore and concurrency evidence; production key management; durable preference onboarding and gateway configuration in the real deployment. |
| Virtual Twin | Authenticated API, explicit-consent gates, upload bounds, DermalSight proxy contract, Click It contract, readiness/capability reporting and API tests. The private VTON worker is separately isolated with mock-tested image validation and category mapping. | A real Virtual Twin/body-reconstruction model and validated output storage; the VTON worker itself still needs pinned source/weights/GPU deployment and secure orchestrator adapters. |
| Wardrobe | Domain model and lifecycle contract; authenticated SQLAlchemy API; PostgreSQL migration; owner-scoped CRUD; version-checked transitions; explicit image-storage consent; durable asset-deletion outbox; CI tests. | Deployed PostgreSQL integration/restore, authenticated identity binding at ingress, live object-storage deletion worker and retry/DLQ testing, catalog contract and end-to-end deletion evidence. |
| Click It | Authenticated guarded endpoint requires explicit processing/Click It consent, validates media and size, closes the upload, and honestly returns unavailable when reconstruction is not configured. | Validated image-to-product reconstruction adapter, output asset storage, CAL decision-governance integration, latency/quality benchmark and end-to-end tests. |
| Confidence engine / FCI | Fit estimate contract, uncertainty bounds, provenance, required/observed evidence coverage gate, Brier/ECE offline metrics, and CAL UNKNOWN/review behavior for missing or uncalibrated evidence. | Trained/calibrated predictor, representative held-out labels, interval coverage, high-confidence failure analysis and subgroup/bias validation. |
| Cultural identity | Explicit-declaration policy is integrated into canonical CAL; a persistent declaration API stores confirmed declarations, supports auditable retraction, and emits candidate-bound HMAC-signed requirement snapshots; both decision service and gateway have signature-verification paths. | Deploy PostgreSQL, bind user identity at ingress, connect the provider in production, rotate keys safely, and review/version a locale-aware attribute catalog with culturally informed governance. |

## Merged implementation scope

1. Move cultural identity evaluation into the canonical package-level decision pipeline; reject caller-injected cultural approval signals and preserve BLOCK/REVIEW outcomes.
2. Add a confidence-engine coverage gate so calibrated numbers cannot enter CAL as a positive fit signal when required evidence is missing or no required evidence fields have been declared.
3. Add a wardrobe domain kernel for owner-scoped item lifecycle changes, opaque image asset identifiers, explicit image-storage consent, versioning, and terminal deletion state.
4. Add Xari's authenticated route-planning contract for chat, skin analysis, marketplace search, Virtual Twin, wardrobe, Click It, and Virtual Try-On. It is deliberately planning-only until each service's request/response contract and authentication adapter are integrated.
5. Add a SQLAlchemy-backed NPL ledger API, PostgreSQL migration, event uniqueness/idempotency and signed candidate-bound evaluation snapshots. Production DB deployment, concurrency/restore tests and live provider configuration remain required.
6. Add a persistent cultural declaration API with user confirmation, explicit requirement records, correction/retraction events and a signed evidence envelope. The decision service and gateway verify signatures when the provider is integrated; no attributes are inferred from images or demographic proxies.
7. Keep Twin reconstruction and Click It unavailable. Only validated models, measured quality, consented asset handling, and real deployment evidence can enable them.
8. Add a separate private GPU worker boundary for VTON: bearer authentication, explicit consent flags, image decoding/size/pixel checks, explicit category mapping, output PNG validation, no-store handling, CUDA/weights readiness checks, and mandatory exact upstream commit pin. Worker tests use a mock pipeline only; no GPU, weights, or model execution is claimed.
9. Add dedicated CI for worker contracts without downloading PyTorch or model weights. The worker has not been deployed and the orchestrator's real consent, asset-resolution, authorization, and output-storage adapters are still not connected.

## Required acceptance gates before any feature is called complete

### Xari / Tari lineage
- Exactly one canonical runtime name and router.
- Authenticated requests; fixed server-side upstream allowlist; no client-provided URL, tokens or arbitrary tool name.
- Per-intent consent requirements and clear not-configured/not-executed errors.
- Execution adapters contract-tested against each downstream service, timeouts, redaction, correlation IDs, tracing and abuse/rate limits.

### NPL
- PostgreSQL uniqueness on rejection event IDs scoped to user; transaction/concurrency tests prove retries cannot double-count.
- Durable hard exclusions, explicit correction events, audit delivery, retention, deletion, and tenant-isolation tests.
- CAL still independently requires SHOW after NPL passes.

### Virtual Twin, Click It and Virtual Try-On
- Licensed model/adapter and reproducible model revision. The private VTON worker Dockerfile requires an exact upstream commit SHA; dependency licensing, including human-parser dependencies, must be reviewed.
- Input validation, explicit consent, bounds on bytes/pixels/video duration, no arbitrary URLs, safe storage/deletion, and no sensitive output in logs.
- Labeled validation across relevant body shapes, lighting, devices and product classes; report accuracy and uncertainty.
- Capability readiness remains false until real adapter and required secrets are available.

### Virtual Try-On worker
- Keep the worker on a private network; do not expose it to public ingress.
- Integrate real server-side consent verification, asset authorization/resolution and output storage. Worker booleans are not proof of a durable consent record.
- Verify the exact upstream model revision, full dependency licenses, real CUDA/weights readiness, output image integrity, quality across diverse subjects/garments, latency/VRAM/cost and failure behavior before enabling it.

### Wardrobe
- PostgreSQL-backed repository, migration/backup/restore, object-storage asset authorization and deletion.
- Optimistic concurrency or transactional version checks; ownership and cross-tenant tests.
- Catalog references are identifiers only; avoid a duplicate catalog product model.
- Lifecycle audit and retention/deletion workflow proven end to end.

### Confidence engine
- Every estimate carries model version, calibration version, evidence provenance, interval semantics, required-field coverage and uncertainty.
- Uncalibrated estimates or missing required evidence become UNKNOWN; no implicit 0.5 fallback or heuristic score becomes confidence.
- Held-out outcome labels, Brier score/ECE, interval coverage, high-confidence failure analysis, sample counts, coverage by cohort and bias review.
- CAL thresholds are versioned and evaluated; confidence never overrides hard safety, user, NPL, or cultural blocks.

### Cultural identity
- Requirements must trace to a current explicit user declaration and remain scoped to that user. The declaration service stores confirmation versions and retractable declaration records and signs the active requirements bound to each candidate evaluation.
- Product metadata completeness is measured; unknown requirement status routes to REVIEW.
- Versioned, reviewed, locale-aware attribute catalog with documented provenance and culturally informed review.
- Soft preferences are explanatory; explicit hard requirements can block; no demographic inference from images.
- Canonical CAL tests prove a cultural block always blocks and missing metadata never becomes a pass; decision-service tests reject modified/foreign-user evidence. Provider deployment, key rotation and an end-to-end production signature test remain release gates.

## Non-negotiable release rule

Passing unit/contract CI is necessary but not sufficient. Do not enable real rendering, product reconstruction, skin analysis, or body measurement simply because an API scaffold is healthy. Keep each model-backed feature unavailable until model licensing, data protection, evaluation, deployment configuration, and end-to-end operational evidence have passed review.
