# ADR-0001: CaTaCaCi is a decision contract, not a stack of cognitive services

- **Status:** Accepted for the next implementation increment
- **Date:** 2026-10-22
- **Scope:** Product-candidate decisions used by Cirvanna discovery and preview experiences
- **Canonical implementation:** `packages/identity-intelligence/catacaci/core.py`, composed by `packages/identity-intelligence/catacaci/pipeline.py`

## Decision

CaTaCaCi remains Cirvanna's decision-governance concept, but its production-critical core is **one small, deterministic Cognitive Arbitration Layer (CAL)**. The value is the enforceable decision contract—especially hard-veto precedence, treatment of unknown evidence, and auditable verdicts—not the number of named components.

CAL is the only authority that converts normalized evidence into `SHOW`, `BLOCK`, or `REVIEW`. It does not retrieve products, infer preferences, generate fit estimates, render a Virtual Twin, or invent missing evidence. Those capabilities may supply typed evidence to CAL, but cannot authorize display independently.

## Normative decision contract

### Request and evidence

A request identifies the request, candidate, and policy version. Evidence arrives as typed signals with a stable signal ID, kind, state (`PASS`, `BLOCK`, or `UNKNOWN`), reason code, explanation, required/optional marker, source version, and optional confidence. Confidence is finite and in `[0, 1]`.

Signal producers own the correctness of their evidence. CAL can arbitrate supplied evidence; it cannot prove that a safety evaluator, preference store, catalog attribute, or fit model is trustworthy. A production caller must validate source identity, version, freshness, consent, and candidate/user binding before treating a signal as trusted. The current contract carries source versions but does not yet enforce all of these provenance checks.

### Verdict rules

Apply these rules in order:

1. **BLOCK:** at least one trusted hard-veto signal is explicitly blocked. The initial hard-veto kinds are safety, legal eligibility, user hard constraints, NPL hard negatives, cultural requirements, and context eligibility. Neither fit confidence, popularity, trends, nor a model score can reverse such a veto.
2. **REVIEW:** no hard veto exists, but a non-veto signal is blocked; a required gate is missing or unknown; fit confidence is missing, uncalibrated, below policy, or materially inconsistent across sources; or evidence fails validation. `REVIEW` never authorizes display.
3. **SHOW:** every required gate has explicit passing evidence, no veto or unresolved contradiction remains, and the required fit evidence meets the versioned policy threshold. Only this verdict may set `may_display = true`.

A missing gate is not an implicit pass. A provider with no applicable rule must emit an explicit, versioned `PASS` result. A policy provider that is unavailable must emit `UNKNOWN` or fail the request closed.

The fit-confidence minimum and cross-source disagreement tolerance are policy parameters, not claims about measured accuracy. Any production threshold change must be tied to a policy version and validated against a frozen evaluation set before release. The current defaults (0.70 minimum confidence and 0.10 maximum disagreement) are engineering defaults, not calibrated business, clinical, or universal-fit thresholds.

### What CAL does not do

- It is not a weighted recommender or a second ranking model.
- It does not upgrade unknown evidence to a pass, average away a conflict, or let a soft signal override a hard constraint.
- It does not infer cultural identity from a face, body, skin tone, location, or shopping history. Cultural policy must operate on explicit user-declared requirements and permitted context.
- A product-card `SHOW` decision is not checkout authorization, a medical judgment, proof of Virtual Try-On accuracy, or a guarantee that an item will fit.
- It must not expose internal deliberation or unnecessary sensitive profile data. Explanations should be concise, reason-coded, and grounded in permitted evidence.

## Canonical runtime flow

1. Authenticate and authorize the caller; validate request shape, consent, and user/candidate ownership.
2. Fetch the canonical active candidate and assess required attribute coverage.
3. Gather versioned evidence from the domain owners: EEPL/context, legal and safety policy, explicit user constraints, cultural requirements, NPL, USI, and calibrated fit intelligence. Independent checks may run in parallel; hard-veto checks should be run early when that reduces waste. Execution order must not change verdict semantics.
4. Normalize results into the CAL signal contract. Do not inject a second interpretation of an existing signal kind.
5. Call CAL once at the display-authorization boundary.
6. Persist the minimal decision receipt before releasing a decision. The receipt needs the request/candidate IDs, verdict, reason codes, contract and policy versions, catalog version, and the source versions/states of evaluated gates. Store no image, measurement, or unnecessary user profile values in the audit log.
7. Release a candidate to the relevant surface only when CAL returns `SHOW`. Keep `BLOCK` and `REVIEW` out of display/preview paths; a review flow may offer clarification or an explicitly labeled alternative.

Search and ranking may shortlist candidates before the final gate. They cannot bypass CAL before a candidate is exposed to the user.

## Component disposition

These are domain responsibilities, not a requirement to create separate services:

| Component | Decision |
|---|---|
| **CAL** | Keep as the sole, synchronous, deterministic display-arbitration kernel. |
| **EEPL, cultural policy, NPL, USI, FCI** | Keep as domain-owned evidence producers. Their results must be normalized once into the CAL contract. |
| **TAL — Temporal Learning** | Keep as a consented, versioned feedback/state workflow outside the per-candidate synchronous arbitration path. Do not make it an extra runtime veto layer. |
| **CAM — Counterfactual Auditing** | Keep as replay/evaluation tooling. Clearly separate observed decisions from simulated alternatives; do not claim counterfactuals prove causality. |
| **CIL — Collective Intelligence** | Defer production integration until consent, aggregation, privacy, retention, and abuse controls are designed. Contributor suppression alone is not differential privacy. It must never override a user's hard constraints. |
| **VSL — Value System Layer** | Treat as policy governance/configuration and a reviewed change process, not an autonomous self-modifying runtime brain. Changes require a distinct approver, versioning, tests, and rollback. |
| **CDIC and CRFP scopes** | Keep behind explicit compatibility/fit contracts until semantics and versions are reconciled. Marketplace CRFP and system-wide CRFP remain separate scopes; neither creates an alternative display authority. |

Do not create separate deployable services for TAL, CAM, CIL, or VSL just to honor their names. Separate them only when concrete storage, privacy/security, scaling, ownership, or release-cadence needs justify the boundary.

## Audit findings and release blockers

The repository currently contains a deterministic CAL core and a package-level vertical slice. The API gateway calls `catacaci.pipeline.evaluate_candidate`; a second composition adapter also exists at `services/api-gateway/app/decision_pipeline.py` and is re-exported by the app package. No internal call to its `arbitrate_candidate` was found in the inspected code search. Keep it only as a documented compatibility adapter or remove it after confirming no external consumers; do not extend both paths with separate policy logic.

The serving gateway explicitly reports that independent safety-policy and calibrated FCI providers are not configured. Its current default evidence therefore fails closed to `REVIEW`; this is safer than fabricating approval, but it is not a useful production recommendation experience. A passing unit test that injects mocked passing signals does not solve that provider gap.

The current SQLite decision audit stores the verdict and reason codes, but it does not retain the evaluated signal states and source versions needed for a strong decision receipt or replay. Before production, extend the receipt and test that it is durably committed before any displayable response is released. Treat the SQLite store as development-only.

## Acceptance tests

The decision contract is not ready for production until tests demonstrate:

- a hard veto always returns `BLOCK`, even with maximum fit confidence;
- missing or unknown required evidence returns `REVIEW`;
- a non-veto block returns `REVIEW`, not approval;
- `SHOW` requires explicit passes for every required gate and valid, calibrated fit evidence meeting the active threshold;
- fit-source disagreement follows the configured policy tolerance without averaging away the conflict;
- input order does not change the verdict or normalized evidence trace;
- malformed, stale, untrusted, cross-user, or cross-candidate evidence cannot authorize display;
- only CAL `SHOW` authorizes display, preview, or downstream generation;
- audit failure prevents release, and a durable receipt identifies the exact policy/contract/source versions;
- changes to NPL, learned preferences, or governance policy are explicit, versioned, reversible, and cannot silently weaken a user-declared hard constraint.

## Consequences

This decision deliberately keeps the synchronous architecture small. CaTaCaCi's defensible differentiation is a **deterministic, fail-closed, versioned, auditable decision boundary** across personalization and fit evidence. TAL/CAM/CIL/VSL can mature around that boundary at the pace justified by working use cases and evidence—not because the diagram contains four more names.
