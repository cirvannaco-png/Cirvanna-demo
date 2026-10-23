# Cirvanna feature-spine audit and integration gates

**Audit date:** 23 October 2026  
**Reviewed main:** `091a1bd692ede5fce666808a6a8e6eb5e914455b`  
**Status:** implementation work in progress; no production-readiness claim.

## Canonical naming and boundary decisions

- **Xari** is the canonical assistant/orchestration name. Tari and Xyra are legacy source generations. Preserve them under source lineage; do not deploy multiple orchestrators.
- **CaTaCaCi/CAL** is the only display authorization authority. Xari, Wardrobe, Virtual Twin, Click It, and Virtual Try-On cannot independently approve candidate display.
- **NPL** is a hard-veto policy layer. Explicit exclusions and learned exclusions at their threshold cannot be overridden by ranking, outfit suggestions, Click It, or visualization.
- **Cultural identity** evaluates only declared user requirements against explicit product metadata. Do not infer religion, ethnicity, modesty, or cultural constraints from appearance, skin tone, names, geography, or demographic proxies.
- **FCI/confidence** is an evidence and calibration boundary, not a substitute for a validated fit-prediction model. Missing inputs, uncalibrated estimates, and incomplete metadata route to review.
- **Virtual Twin** owns user body representation and measurements. **Click It** owns product reconstruction from a user-provided product reference. **Virtual Try-On** owns garment/person rendering. They exchange opaque asset IDs and typed results; none owns policy arbitration.
- **Wardrobe** owns user-specific item records and their lifecycle. Catalog product metadata remains catalog-owned; other services must not write directly to wardrobe tables.

## Verified state before this branch

| Feature | Evidence in repository | Missing acceptance evidence |
|---|---|---|
| Tari/Xari | Xari README scaffold; Tari/Xyra source generations remain in staging. | Authenticated canonical router, capability registry, upstream execution adapters, tracing and failure handling. |
| NPL | Pure policy kernel and architecture tests; threshold of three unique rejection events. | Durable store, uniqueness/transaction guarantees, service API, lifecycle/deletion and CAL integration against a database. |
| Virtual Twin | Authenticated API, readiness/capability contract, and API tests. | Trained/licensed reconstruction model, calibration and measured accuracy, secure output storage and validated deployment. |
| Wardrobe | Ownership README only. | Domain model, lifecycle rules, persisted item records, image-asset authorization, catalog adapters, retention/deletion. |
| Click It | Virtual Twin API reports product reconstruction unavailable. | Validated image-to-product reconstruction adapter, consent-aware inputs, output validation, latency/quality benchmark and safe no-result behavior. |
| Confidence engine / FCI | Fit estimate contract, uncertainty bounds, evidence provenance, Brier/ECE offline metrics. | Required-evidence coverage gate, calibrated predictor, representative held-out labels, interval coverage and subgroup/bias validation. |
| Cultural identity | Explicit-declaration policy kernel and tests. Gateway has a separate optional adapter. | Canonical package pipeline integration, declaration lifecycle, reviewed rule catalog, candidate metadata quality and end-to-end CAL evidence. |

## Work being added in this feature-spine branch

1. Move cultural identity evaluation into the canonical package-level decision pipeline; reject caller-injected cultural approval signals and preserve BLOCK/REVIEW outcomes.
2. Add a confidence-engine coverage gate so calibrated numbers cannot enter CAL as a positive fit signal when required evidence is missing or no required evidence fields have been declared.
3. Add a wardrobe domain kernel for owner-scoped item lifecycle changes, opaque image asset identifiers, explicit image-storage consent, versioning, and terminal deletion state.
4. Add Xari's authenticated route-planning contract for chat, skin analysis, marketplace search, Virtual Twin, wardrobe, Click It, and Virtual Try-On. It is deliberately planning-only until each service's request/response contract and authentication adapter are integrated.
5. Define an explicit durable NPL ledger interface. This is not itself a PostgreSQL implementation and must not be described as persistent until a real adapter and transaction tests land.
6. Keep Twin reconstruction and Click It unavailable. Only validated models, measured quality, consented asset handling, and real deployment evidence can enable them.

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

### Virtual Twin and Click It
- Licensed model/adapter and reproducible model revision.
- Input validation, explicit consent, bounds on bytes/pixels/video duration, no arbitrary URLs, safe storage/deletion, and no sensitive output in logs.
- Labeled validation across relevant body shapes, lighting, devices and product classes; report accuracy and uncertainty.
- Capability readiness remains false until real adapter and required secrets are available.

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
- Requirements must trace to a current explicit user declaration and remain scoped to that user.
- Product metadata completeness is measured; unknown requirement status routes to REVIEW.
- Versioned, reviewed, locale-aware attribute catalog with documented provenance and culturally informed review.
- Soft preferences are explanatory; explicit hard requirements can block; no demographic inference from images.
- Canonical CAL tests prove a cultural block always blocks and missing metadata never becomes a pass.

## Non-negotiable release rule

Passing unit/contract CI is necessary but not sufficient. Do not enable real rendering, product reconstruction, skin analysis, or body measurement simply because an API scaffold is healthy. Keep each model-backed feature unavailable until model licensing, data protection, evaluation, deployment configuration, and end-to-end operational evidence have passed review.
