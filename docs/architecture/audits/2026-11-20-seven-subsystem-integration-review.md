# Cirvanna seven-subsystem integration review — 20 November 2026

## Scope and ownership

This review covers the existing `Cirvanna-demo` monorepo. The seven requested capabilities are connected through explicit service boundaries; they do not justify creating seven repositories or moving decision authority into the browser.

| Capability | Canonical owner(s) | Current integration state | Production release condition |
| --- | --- | --- | --- |
| Garment segmentation, fitting and rendering | `services/virtual-try-on`, `services/virtual-twin`, `services/vision-intelligence`, Wardrobe and Fit Confidence Intelligence (FCI) | Consent- and asset-gated try-on orchestration and a separately authenticated GPU renderer exist. Pose landmarks are not fit evidence. Renderer output is a visual preview, not a fit guarantee. | Pinned source, complete weights and offline parser cache; CUDA/ONNX GPU readiness; commercial rights for the human parser and transitive artifacts; device/category QA; calibrated fit evaluation before any fit claims. Anatomical garment/body segmentation and fit accuracy remain unvalidated. |
| DermalSight validated image analysis | `services/dermalsight`, `services/vision-intelligence` | DSI capability reporting intentionally remains `contract_only`; skin-tone intelligence, facial geometry and body-tone alignment remain blocked. No unvalidated substitute model is enabled. | Licensed immutable models, controlled capture and color calibration, signed held-out evaluations across skin-tone/device/lighting slices, uncertainty/repeatability evidence, consent and biometric/privacy review. |
| Click It image discovery and privacy | `services/virtual-twin`, `services/vision-intelligence`, `services/privacy-governance-service`, Marketplace BFF | Vision Intelligence includes pinned face detection/masking before image-quality scoring, embedding and catalog access, without face recognition. The public Marketplace BFF still rejects uploads before multipart parsing; Click It remains unavailable in the UI. | End-to-end evidence for resource-bound consent/revocation, jurisdiction policy, child protections, detector coverage and failure handling, asset-bound privacy attestation and all publishing routes. Keep the BFF kill switch closed until independent verification confirms the complete chain. |
| Look It outfit decomposition and visual search | Marketplace BFF, PNELLY (`services/xari`), `services/vision-intelligence` | Separate from Click It. Look It has consented, ephemeral image processing and outfit-component decomposition with image-to-catalog-text similarity. It does not claim exact visual SKU identification; raw images are not persisted and product/merchant/price details remain pending CAL. | Evaluate on a human-reviewed, consented outfit dataset; measure component recall, relevance, diversity, no-match behaviour and subgroup errors; retain CAL authorization before product display. |
| PNELLY conversational intelligence | Marketplace BFF, `services/xari`, Identity Learning, Wardrobe and Decision Gateway | Marketplace discovery already uses wardrobe-aware discovery and returns only candidate-bound CAL SHOW and CIL-eligible products. Complementer remains advisory-only. This branch wires the existing consent-bound 24-hour structured-context conversation lifecycle into the marketplace UI. Conversation identifiers stay in page memory only; raw transcripts and images are not stored. | Verify live provider wiring, account switching, expiry/revocation, latency and user-approved learning policy. Complementer cannot authorize products or create durable memory by itself. |
| CAL mandatory product authorization | `services/decision-service`, API Gateway, Marketplace BFF, `services/commerce-service` | Discovery enforces candidate/product/catalog-version/offer binding and CIL eligibility before details are returned. Commerce performs fresh purchase authorization for cart and checkout. The browser is not an authorization authority. | Keep all product-serving and purchase routes behind fresh, exact-candidate authorization. Validate production FCI, safety, CIL and Commerce evidence providers; ambiguous or mismatched receipts must abstain. |
| Catalog multi-merchant product intelligence | `services/catalog-service`, `services/commerce-service` | Catalog owns normalized product intelligence and canonical product/variant identity. Commerce owns merchant listings, offers, inventory, operating markets, tax, fulfilment, FX and payment capability evidence. Provider adapters validate exact resources and time-bounded evidence when required. | Connect and independently verify real merchant and market providers; validate canonical variant mapping, stale inventory/price handling, FX/tax/fulfilment quotes, localized display and purchase reconciliation in each operating market. Configuration-only adapters are not live provider integrations. |

## Changes in this branch

1. **PNELLY continuity is reachable from the marketplace discovery surface.** The user explicitly opts in and enables continuity. The browser keeps only the active conversation identifier in page memory. Discovery requests pass an idempotent turn ID; the UI checks conversation binding and state version. The user can end the conversation; the UI requires confirmation that the backend deleted structured context and revoked its purpose-bound consent. The BFF and Identity Learning APIs remain authorities for ownership, consent, versioning and deletion.
2. **Virtual Try-On worker resource lifecycle is tightened.** Decoded person and garment images are closed after success, model failure and GPU-busy rejection. Encoded request buffers are released after decoding. Every generated pipeline image is closed after encoding and validation, including when a result contains multiple images.
3. **This review records service ownership and evidence-based release gates.** It distinguishes implemented contracts and mock tests from model validation, provider readiness and production operation.

## Explicit non-changes

- Click It remains disabled at the public BFF. A masking function alone does not prove that no unmasked photo can reach any publishing or downstream route.
- DermalSight inference remains blocked; no model weights or validation results are fabricated.
- Try-on output is not described as fit prediction or a fit guarantee. Real GPU inference and model licensing remain release gates.
- CAL and Catalog boundaries are not duplicated in the UI or moved into PNELLY. Retrieval output alone cannot authorize product display.
- The stale, divergent PR #197 is not merged or cherry-picked. This branch is based on current `main`.

## Verification performed against `main` commit `fe916168748b873caceb6a44fbd63f550732357b`

| Test scope | Result |
| --- | ---: |
| Virtual Try-On model-worker contract and resource-lifecycle tests | 28 passed |
| Marketplace BFF route and UI contract tests | 125 passed |
| DermalSight service tests, including synthetic ONNX HTTP/runtime fixtures | 74 passed |
| Vision Intelligence API and Click It privacy tests | 38 passed |
| Virtual Twin service tests | 58 passed |
| Decision Gateway service tests | 22 passed |
| PNELLY/Xari service tests | 18 passed |
| Catalog service and product-intelligence tests | 28 passed |
| Identity Learning and conversation lifecycle tests | 61 passed |
| Commerce and market-provider adapter tests | 90 passed |
| API Gateway and marketplace discovery tests | 102 passed |
| Privacy Governance and publication-route guard tests | 42 passed |
| Marketplace static contract and responsive-layout tests | 10 passed, 1 skipped |
| **Total** | **696 passed, 1 skipped** |

Additional checks: Python compilation of modified modules, Node syntax validation of the marketplace page's inline JavaScript, and `git diff --check` all passed. The skipped marketplace test is documented by the UI test module; no headless browser E2E run was performed in this environment.

The service suites exercise mocked provider/model boundaries where configured. DermalSight's ONNX tests use a synthetic contract model, not a trained skin model. These results do not establish live GPU inference quality, real DermalSight accuracy, Click It end-to-end privacy attestation, actual merchant/fulfilment provider coverage or production readiness.

## Release decision

This branch is a safe integration and test improvement, not authorization to enable every feature. Keep Click It, DermalSight inference, customer-facing production try-on, and any unverified merchant/provider flow blocked until acceptance evidence is attached to the release record and independently reviewed.
