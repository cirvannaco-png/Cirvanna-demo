# Cirvanna specialist capability audit

- Repository: `cirvannaco-png/Cirvanna-demo`
- Baseline: default branch `main`, commit `3f13e53f39e0b02405f1b7fdab985053132d2769`
- Candidate: `feature/specialist-ecosystem-foundation`
- Status: implementation candidate; no production/storefront certification implied

## Existing canonical modules at the baseline

| Capability | Canonical source | Actual boundary |
|---|---|---|
| Product catalog | `services/catalog-service/app/main.py`, `services/catalog-service/tests/test_catalog.py` | Authenticated CRUD/listing, validated metadata, version history and batch read. Not checkout, stock, fit, personalized ranking, or try-on. |
| NPL | `packages/preferences/npl/core.py`, `services/npl-service/` | Deterministic exclusions and rejection-threshold policy. Effective preferences must come from trusted storage/API, never client-supplied rows. |
| CAL | `packages/identity-intelligence/catacaci/core.py`, `catacaci/pipeline.py` | Deterministic SHOW/BLOCK/REVIEW kernel. Marketplace readiness docs do not certify end-to-end display suppression or trusted evidence provenance. |
| Skin analysis | `services/dermalsight/app/main.py`, `app/model_adapter.py`, `app/validation.py` | Consent/auth API and hash-verified ONNX adapter contract. No approved model artifact, taxonomy/evaluation corpus, or signed validation report is in the baseline; inference fails closed. |
| Xari | `services/xari/app/main.py`, `services/xari/xari/routing.py` | Route planning and configuration-gated marketplace search. Several intents remain route-only. |
| Look-generator archive | `integration-staging/source-candidates/18-cirvanna-skeleton-.txt/src/lookgenerator/` | Staged candidate source only, not the canonical, tested runtime implementation. |

No canonical Hair, Face, Makeup, Footwear, Skincare, or complete-look specialist module was found in the baseline outside staged source candidates.

## Specialist capabilities registered by this increment

| Specialist | Available now | Still requires a provider or verified evidence |
|---|---|---|
| Hair | Catalog-category matching, NPL and CAL gates | Hair-image classification, hairstyle generation, virtual hair previews |
| Face | Catalog matching for explicit eyewear/face-styling categories | Face-shape inference, facial analysis, face-aware style selection; fit evidence for physical products |
| Skin | Registered, reports `provider_unavailable` | Validated DermalSight model, signed report, representative evaluation and configuration |
| Look | Apparel category matching and bounded deterministic bundle composition | Bundle fit confidence, safety/legal evidence, curated shared `look_compatibility_group`; visual coordination/try-on |
| Footwear | Catalog matching, fit-sensitive CAL profile | Calibrated fit, size/stock availability and comfort evidence |
| Makeup | Catalog matching and declared constraint enforcement | Shade inference and virtual makeup |
| Skincare | Separate catalog matcher for skincare categories | Product ingredient evidence, sensitivity policy and any reviewed health-related claims; no diagnosis/treatment advice |

## Decision flow and safeguards

1. The catalog adapter reads authenticated active products from the canonical Catalog Service. Incomplete, duplicate, malformed, over-limit, or mid-pagination-changing reads fail closed; no demo fallback is allowed.
2. Candidates retain canonical product IDs and catalog attributes. No second product store is introduced.
3. The canonical NPL kernel evaluates every candidate. A hard negative becomes a CAL hard-veto and cannot be reversed by a specialist.
4. Safety and legal/eligibility evidence default to UNKNOWN. Trusted server-side providers must explicitly supply PASS.
5. The CAL product-only profile may omit physical-fit confidence for non-fit-sensitive catalog decisions. It does not invent confidence or waive other required gates. CAL's default remains fit-strict.
6. Apparel and footwear require fit-confidence signals. A complete look needs component SHOW, bundle-level safety/legal/fit evidence, a same-currency budget check, NPL evaluation, and shared catalog-declared look compatibility metadata.
7. Only CAL SHOW produces a displayable option. BLOCK and REVIEW are not display authorization.

## Release blockers

- Bind authenticated identity and canonical NPL persistence through a trusted internal service boundary before adding an HTTP endpoint.
- Integrate trusted safety/legal providers, calibrated fit evidence, and curated compatibility metadata. Missing evidence correctly yields REVIEW.
- Add audit receipt persistence, rate limits, observability, privacy/consent controls, checkout revalidation, and gateway integration before endpoint exposure.
- No real ONNX model, image provider, production preference store, or checkout workflow was added by this increment.
- Exact PR-head CI evidence is required before calling automated tests passing. Unit fixtures are not production readiness evidence.
