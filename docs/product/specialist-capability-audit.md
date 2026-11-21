# Cirvanna specialist capability audit

- Repository: `cirvannaco-png/Cirvanna-demo`
- Baseline: default branch `main` before the appearance-specialist PR; see the merged PR's base SHA for the exact integration point
- Candidate: `integration/appearance-specialist-current-main`
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

The baseline includes a shared appearance-transformation contract and a consent-aware appearance look-session service, but no canonical seven-domain catalog specialist registry or internal Catalog + NPL + CAL orchestration package. This increment fills only that internal orchestration gap; it does not replace the existing transformation contract or look-session service.

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

1. The catalog adapter reads authenticated active products from the canonical Catalog Service. Incomplete, duplicate, malformed, over-limit, or mid-pagination-changing reads fail closed; no demo fallback is allowed. Because the current Catalog Service exposes no point-in-time snapshot token or transaction boundary, this is not an atomic catalog snapshot under concurrent writes, and it must not replace checkout/stock revalidation.
2. Candidates retain canonical product IDs and catalog attributes. No second product store is introduced.
3. The canonical NPL kernel evaluates every candidate only when the current user's preference state was successfully loaded. A missing NPL snapshot is UNKNOWN and yields CAL REVIEW; an explicit empty tuple means a trusted read succeeded and found no active preferences. Cross-user preference rows are rejected. A hard negative becomes a CAL hard-veto and cannot be reversed or reintroduced by a specialist/composer.
4. Safety and legal/eligibility evidence default to UNKNOWN. Trusted server-side providers must explicitly supply PASS.
5. The CAL product-only profile may omit physical-fit confidence for non-fit-sensitive catalog decisions. It does not invent confidence or waive other required gates. CAL's default remains fit-strict.
6. Apparel and footwear require fit-confidence signals. A complete look needs component SHOW, bundle-level safety/legal/fit evidence, a same-currency budget check, NPL evaluation, and shared catalog-declared look compatibility metadata.
7. Only CAL SHOW produces a positive local preflight. BLOCK and REVIEW are non-displayable. A local preflight is not a durable display or purchase receipt; every user-visible product/offer requires a fresh exact-candidate, market/offer-bound Decision Gateway receipt.

## Release blockers

- The internal orchestrator now loads preferences through the authenticated NPLClient. Before exposing an HTTP endpoint, bind the context user ID only from the authenticated server identity, deploy and verify both internal service credentials/TLS, and use candidate-bound signed NPL evidence when crossing a lower-trust service boundary.
- Integrate trusted safety/legal providers, calibrated fit evidence, and curated compatibility metadata. Missing evidence correctly yields REVIEW.
- Add audit receipt persistence, rate limits, observability, privacy/consent controls, checkout revalidation, and gateway integration before endpoint exposure.
- No real ONNX model, image provider, production preference store, or checkout workflow was added by this increment.
- Candidate-branch validation completed on PR #267: 69 focused appearance/CAL tests, 200 architecture tests, Python compilation and eight exact-head GitHub Actions workflows passed. This is code-contract evidence only; it does not establish live providers, production deployment, visual inference, or independent accuracy.
- The catalog adapter does not have a point-in-time snapshot token; moving totals and duplicate/malformed pages fail closed, but page contents can still change without a total change. NPL list reads use trusted internal bearer authentication but no signed response envelope. Keep both adapters on trusted internal ingress.
- The specialist's `cal_preflight_show` is only a local deterministic preflight. It is not permission to expose a product or offer. The host must verify a fresh durable Decision Gateway receipt bound to the exact candidate, product/catalog version, market/offer snapshot and user action before any user-visible display, then revalidate at checkout.
