# Complementer, Marketplace Product Intelligence and Skin-State Forecasting

**Date:** 2 November 2026  
**Status:** Complementer v2 advisory code and Catalog metadata validation are implemented on the feature branch. Durable preference learning, end-to-end marketplace integration and longitudinal skin forecasting remain gated.

## 1. Architectural ownership

| Capability | Canonical owner | Boundary |
|---|---|---|
| Personal aesthetic coordination | `services/recommendation-service` (Complementer) | Composes advice from trusted preferences and current-look context. It does not own the user's identity profile or product truth. |
| Positive style preferences | USI | Interprets declared style preferences; Complementer must not create a second style profile. |
| Hard negative preferences | NPL | Owns explicit hard exclusions. A rejected recommendation is not automatically a permanent veto. |
| Feedback learning | CaTaCaCi/TAL | Owns consented, versioned approval/rejection observations and the profile correction lifecycle. |
| Product identity and metadata | Catalog | Owns canonical product records, typed product-intelligence metadata and product-version history. |
| Final candidate display | CaTaCaCi/CAL | The only authority that may authorize a catalogue candidate for display. |
| Cosmetic skin attributes and future forecasting | DermalSight | Owns non-diagnostic cosmetic skin signals. Forecasting requires a separately validated longitudinal model. |

Do not create a second product database, user-style database or display arbiter inside Complementer.

## 2. Complementer v2

Complementer is a coordinator for a complete look rather than a list generator.

- Fragrance directions use declared scent families/profiles, occasion, desired longevity, intensity and a currency-scoped budget. A requested longevity is a preference target, not a guarantee about the actual product.
- Colour intelligence coordinates clothing, makeup, jewellery and accessories. The response explains whether a colour came from a saved preference or a curated harmony rule.
- Jewellery and accessory directions include earrings, necklaces, glasses and user-selected accessory categories. Self-reported face shape is optional; visual inference is not performed by this service.
- Aesthetic direction includes minimalist, elegant, classic, romantic, bold, streetwear, editorial, natural and bohemian styles. Cultural styling requires a context the user explicitly selected.
- Look completion should make no more than two optional changes and should state what it recommends preserving. The user's existing silhouette and identity are not defects to fix.

Every suggestion must return a reason tied to a declared preference or current-look attribute. Missing data should produce `needs_input`, not a fabricated personal preference.

## 3. Preference learning and memory

The feedback endpoint accepts `approved` or `rejected` events only with explicit personalization consent. An optional `save_preference` action requires a value explicitly selected by the user.

A rejection is a **soft preference observation**. It must not automatically write an NPL hard veto, permanently alter identity, or override a user correction. Repeated rejections can inform a reversible preference hypothesis, but a durable change must be reviewable and correctable by the user.

The current Complementer API builds a versioned TAL handoff event; it does not persist it. Before marketing this as memory, implement the canonical TAL persistence and replay path, authenticated subject binding, consent receipts, retention, export, correction, deletion, idempotency and audit. The API explicitly reports that durable persistence is not configured.

## 4. Marketplace product-intelligence layer

The canonical product record carries optional typed metadata at `attributes.product_intelligence`. The current contract covers:

- `climate_compatibility`: hot-humid, hot-dry, temperate and cool conditions with provenance.
- `context_usage`: declared contexts such as daily, work, evening, formal, travel and sport.
- `cultural_usage`: product-context tags only when editorially reviewed. These describe a product or styling context; they do not assert the buyer belongs to a culture.
- `skin_response`: ingredient-label, non-clinical cosmetic-intent and caution metadata with source evidence.
- `appearance_complement`: shade families, declared undertone matches, finishes, pairing colours and feature-complement tags.
- `observed_outcomes`: consented aggregate satisfaction/review/repurchase metrics with a minimum cohort of 30, a defined observation window, source reference and limitations.

The existing Catalog JSON attributes and version snapshots own persistence; no new database or migration is introduced. Legacy products remain valid without this optional namespace.

A cohort-size floor is only a disclosure safeguard. It is not differential privacy, proof of representative sampling, or causal evidence. Product evidence remains subject to moderation, data-quality checks and source review. Merchant assertions must not be rendered as laboratory or clinical facts.

At recommendation time, Complementer or the marketplace retrieval layer can match product metadata against explicit user preferences and context. Product candidates must still be passed through the canonical decision pipeline. Similarity scores and historical aggregate metrics are not display authorization or purchase certainty.

## 5. Skin-state forecasting — design and release gates

The requested scenario experience can compare a baseline with user-selected future conditions over a 1–12 week horizon. Candidate scenario variables include:

- the exact canonical product/variant, ingredient-label data, intended use and user-entered application frequency;
- expected ambient humidity and climate conditions;
- user-reported sleep regularity or disruption;
- an optional user-entered cycle phase or self-reported hormonal variation.

Cycle and hormonal context is sensitive personal information. It must be optional, separately consented, minimised, excluded from advertising and never inferred from a face, calendar, name or behaviour. The product must not infer or diagnose a hormonal imbalance. A cycle-phase input is context supplied by the user, not a measurement of hormone levels.

**No skin-state predictions are enabled by this change.** The current DermalSight documentation states that a validated skin-analysis model, representative dataset and calibration evidence are not yet configured. A cosmetic image score cannot simply be extrapolated across several weeks. Returning fabricated improvement/irritation percentages or attributing changes to a product would be misleading.

Before forecasts may be shown, DermalSight needs:

1. A licensed longitudinal dataset with repeated measurements, product exposure details, baseline variation and consent for the intended use.
2. A forecast model distinct from single-image attribute inference, with versioned weights, preprocessing, signed validation report and reproducible evaluation.
3. Calibration and error analysis across relevant skin-tone groups, devices, lighting, climate/humidity bands, sleep patterns and cycle-context coverage. Missing subgroup evidence must remain visible.
4. Scenario outputs expressed as calibrated ranges with uncertainty, forecast horizon, evidence coverage and model/data versions—not deterministic promises or causal claims.
5. Comparison against a no-change baseline, temporal holdouts, drift monitoring and independent review of user-facing claims.
6. Explicit, revocable consent, no-store defaults for sensitive inputs, retention/deletion controls, access logging and a privacy/threat assessment.

Until these gates pass, the UI should say that scenario forecasting is unavailable and may show only the user's scenario inputs or educational context. It must not substitute heuristic scores or a language model's narrative for validated predictions.

## 6. Integration sequence

1. Complete Complementer domain contract tests and Catalog product-intelligence validation.
2. Bind Complementer to verified gateway identity, USI/NPL and user-declared cultural context.
3. Connect its feedback events to durable TAL storage with reversible preference controls.
4. Retrieve canonical product/offer records, preserve exact product and variant identifiers, and submit every displayed candidate to CAL.
5. Build DermalSight's longitudinal forecasting dataset and model as a separately reviewed capability.
6. Add UI, staging integration, security/privacy, load, drift and end-to-end tests before production exposure.

## 7. Release truth

Passing isolated unit tests would establish code-contract behavior only. It would not establish persistent personal memory, trained skin forecasting, catalog enrichment quality, live gateway integration, CAL-gated marketplace behaviour, deployment health or production readiness. Those claims require their own evidence.
