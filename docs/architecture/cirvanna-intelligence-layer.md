# Cirvanna Intelligence Layer (CIL)

**Status:** initial domain contracts and Catalog metadata extension implemented; no durable CIL service or automated ingestion is deployed.

## 1. Purpose and ownership

The platform-wide Cirvanna Intelligence Layer (CIL) provides versioned, attributable intelligence about products, ingredients, research, model validity, context and consented recommendation outcomes.

CIL is not a new product database, identity store, recommendation UI or display authority. Catalog remains the canonical owner of product identity, product attributes and product-version history. USI/NPL/TAL retain ownership of user-declared preferences and temporal personalisation. CAL remains the only final `SHOW` / `BLOCK` / `REVIEW` authority.

There is an existing narrower module at `packages/identity-intelligence/catacaci/cil.py`, named the **Collective Intelligence Layer**. It remains a minimum-contributor cohort aggregation contract inside CaTaCaCi. It is not replaced or overloaded by this platform-wide CIL package; the concepts are related but their ownership and scopes differ.

## 2. Data acquisition and rights registry

Every external source must be registered before its data is used. A `SourceRecord` identifies the owner, source kind, locator, access method, rights status, rights/terms reference, permitted purposes, attribution requirements, collection/review timestamps and expiry.

Rights states are explicit:

- `public_domain`, `open_license`, `licensed`, and `api_terms` can permit only the purposes recorded in the source entry and only while the rights record is current.
- `research_only` is restricted to internal research and model evaluation; it cannot authorize commercial recommendation or model training.
- `permission_required`, `unknown`, and `prohibited` authorize no reuse.

A source must not be treated as commercially reusable merely because a page, review, paper, API or catalogue entry is publicly reachable. The source registry records rights evidence; it does not make a legal determination. Legal review is still required where the source terms or jurisdiction are ambiguous.

The current package validates source records in memory. It does not yet persist them or collect third-party content. No scraping, dataset copying, proprietary model extraction or provider integration is enabled by this change.

## 3. Evidence classification and claim scope

Evidence grades have distinct meanings and are not a single universal score:

| Grade | Meaning | What it can support |
|---|---|---|
| E1 | Independent, product-specific clinical or controlled evaluation | A narrowly scoped finished-product claim when source rights permit and limitations match |
| E2 | Peer-reviewed research | The exact research scope; finished-product claims only when the finished product itself was evaluated |
| E3 | Independently validated model evidence | Model performance and limitations, not cosmetic efficacy claims |
| E4 | Manufacturer or merchant product documentation | Product facts and declared formulation/ingredient information, not independent efficacy proof |
| E5 | Consented, aggregated customer feedback | Reported preference and experience patterns, not clinical proof or causal efficacy |
| E6 | Marketing or unverified assertion | Discovery/review queue only; not substantiation |

The claim assessor checks evidence IDs, source registry membership, rights for the requested purpose, source type, grade and scope. For example, a study about an isolated ingredient cannot support a claim that a particular finished product produces the same result. Missing rights, missing evidence or mismatched scope fail closed.

The first Catalog integration adds structured ingredient declarations and typed product claims to the existing `attributes.product_intelligence` JSON namespace. These records remain versioned by Catalog's existing product-version snapshots; no second product store or schema migration is introduced. Each new structured ingredient/claim reference must carry a CIL `source_id`.

**Catalog intentionally has no `approved` claim status in this phase.** Claims remain `pending_review` or `rejected`. The CIL rights/evidence assessment is not yet called by the Catalog write or serving path, so metadata cannot self-approve or become a user-facing efficacy statement. A later integration must verify source registry rights and signed review evidence before introducing claim publication.

## 4. Ingredient and product intelligence

Structured ingredient declarations preserve the product-level label/test evidence and optional label order. Label order must not be translated into an exact concentration. The current normalizer collapses spaces and case; it is not an authoritative INCI identity resolver and does not merge synonyms without a licensed/approved ingredient authority.

Product claims are limited to ingredient presence, cosmetic intent, formulation description and finished-product efficacy. Safety/diagnostic claims are deliberately excluded from this initial contract. Non-clinical cosmetic intent is not a diagnosis or a guarantee of compatibility.

## 5. Model registry and confidence

A model card records model/provider identity, immutable version, task, intended use, validation dataset/report references, evaluated populations, per-population metrics, known limitations, calibration method, expected calibration error and Brier score.

`UNVALIDATED` and `DEPRECATED` models are not eligible for user-facing assessment. User-facing readiness is assessed against an explicit versioned task policy. The policy names the task, intended use, required evaluation populations, metric thresholds by population, maximum expected calibration error and maximum Brier score. An independent validation badge or vendor-provided confidence score is not sufficient on its own. A model is ineligible when a required population or metric is missing or any policy threshold fails. Thresholds are task-specific; this package does not invent one universal beauty-model cutoff.

A vendor-provided confidence score is not automatically calibrated confidence. Validation must include the actual intended population, relevant skin-tone/image-quality segments where applicable, failure analysis and held-out evaluation. CIL model readiness does not replace independent safety/FCI evidence or CAL arbitration.

## 6. Recommendation outcome learning

A `RecommendationOutcome` is accepted only when the caller supplies an active, purpose-bound `recommendation_outcome_learning` consent receipt and a verified CAL `SHOW` decision reference. The package accepts only a keyed HMAC-SHA256 contributor pseudonym in the form `hmac-sha256:<64 lowercase hex characters>`, not a raw user identifier. The key and token issuance belong to a trusted server-side event adapter; this package does not mint tokens or accept free-text medical or health narratives.

User-declared suitability is distinct from the action taken:

- `rejected`, `ignored`, `opened`, `saved` and `purchased` describe actions, not whether a product worked.
- Only an explicit `suitable`, `unsuitable` or `uncertain` report is an outcome label.
- Missing or ignored feedback is not imputed as a failure or success.

Cohort aggregation requires at least 30 distinct contributors with an explicit suitability response before publishing breakdown metrics. This is a disclosure floor, not differential privacy, statistical representativeness or causal proof. The unsuitable-share threshold is supplied by versioned policy rather than hard-coded as a universal benchmark.

A high unsuitable share returns `review_required`. It does not automatically suppress a product, alter Catalog state, create an NPL hard veto, retrain a model or bypass CAL. Product suppression requires a separate reviewed rule and authorized Catalog/policy action. A single rejection is never a permanent user preference or product-level veto.

## 7. Runtime boundaries and security requirements

The calling service—not these in-memory contracts—must verify:

1. The source ID exists in the durable CIL registry and its rights are active for the exact requested purpose.
2. Consent is current, subject-bound, unrevoked and scoped to outcome learning before an event is accepted.
3. A CAL decision receipt is authentic, current, bound to the exact product/candidate and has verdict `SHOW`.
4. Contributor tokens are pseudonymous and purpose-limited; raw identifiers, images and unnecessary measurements are not copied into the outcome ledger.
5. Data export, correction, deletion, expiry and licence revocation propagate to derived intelligence and aggregates according to documented policy.
6. Model and evidence versions are immutable and every assessment is reproducible from its recorded references.

CIL cannot authorize a display. A CIL-supported claim or positive outcome must still pass the normal product retrieval, user constraints, independent safety/legal/fit evidence and CAL decision path. Marketplace and checkout must continue to revalidate their canonical product/variant and CAL decision.

## 8. Implemented in this increment

- Pure-Python rights-aware source registry contract.
- Evidence grades, scope-aware product claim assessment and source-purpose checks.
- Product ingredient declaration and product intelligence record contracts.
- Model validation cards plus a policy-specific readiness assessor with per-population metric, minimum sample-size and calibration thresholds.
- Consent-gated recommendation outcome contract and distinct-contributor aggregation.
- Catalog schema extension for structured ingredient declarations and typed, non-approved claims.
- Unit/contract tests for rights, evidence scope, model validation, consent, CAL SHOW binding, sample suppression and negative-feedback review signaling.

## 9. Not implemented yet

- Durable source/evidence/model registry storage or administrative review APIs.
- Automated public research, manufacturer or merchant ingestion.
- Licensed API/SDK integration with Perfect Corp, Revieve or other providers.
- Persistent ingredient authority/INCI synonym resolution.
- Signed source-rights decisions and runtime CIL-to-Catalog approval enforcement.
- Production outcome event ingestion, contributor-token issuance, deletion/replay and privacy-preserving analytics.
- Model training, online learning, model deployment or automatic product suppression.
- End-to-end wiring from PNELLY, DermalSight, RadianceScore, Wardrobe and Marketplace.

These are separate release gates, not capabilities implied by the contract package. The next safe increment is a durable source registry and authenticated ingestion/assessment API, followed by provider adapters and a consent-verified outcome event path.
