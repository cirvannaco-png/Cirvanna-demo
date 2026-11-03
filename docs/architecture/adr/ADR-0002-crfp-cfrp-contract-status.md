# ADR-0002: CRFP has marketplace and system-wide scopes

- **Status:** Accepted clarification — one canonical name, two bounded scopes
- **Date:** 2026-11-03
- **Scope:** CRFP naming, marketplace integration, and system-wide architecture
- **Supersedes:** The prior ADR-0002 hold that incorrectly treated CFRP and CRFP as separate concepts.
- **Review trigger:** The two scope contracts are ready for detailed interface and implementation review.

## Context

The earlier `CFRP` spelling was a typo. The canonical name is **CRFP** in both cases. There are two distinct CRFP responsibilities:

1. **Marketplace CRFP** — the marketplace-scoped CRFP capability, responsible for its own marketplace workflows and product/customer-facing integration.
2. **System-wide CRFP** — the cross-platform CRFP capability used throughout Cirvanna, with a reusable system-level responsibility rather than ownership of marketplace-only workflows.

These are not competing names, aliases, or a single component accidentally duplicated. They share a canonical name but must retain explicit scope boundaries. The exact expansions, typed interfaces, state ownership, and detailed behavior must be taken from authoritative product specifications; this ADR does not invent them.

The repository also preserves an earlier source-candidate bundle at `integration-staging/source-candidates/05-cfrp-v6.txt`. The legacy archive path and filename preserve source provenance; the spelling in that historical filename is not a second domain name. The candidate's scope must not be assigned to Marketplace CRFP or system-wide CRFP without evidence.

## Decision

1. **Use CRFP as the sole canonical spelling** in current documentation, contracts, identifiers, package names, and new code. Do not introduce CFRP as a separate capability.
2. **Recognize two explicit scopes:** Marketplace CRFP and system-wide CRFP. They may share domain concepts and common contract primitives, but their responsibilities, inputs/outputs, data ownership, authorization, lifecycle, and release gates must be specified separately.
3. **Keep the system-wide scope reusable and marketplace-independent.** Marketplace CRFP may consume or adapt system-wide CRFP capabilities through a versioned contract; it must not fork or silently redefine the system-wide rules.
4. **Keep marketplace-specific policy and workflow in the marketplace boundary.** Do not leak marketplace persistence, merchant/payment concerns, or storefront orchestration into the system-wide CRFP domain.
5. **Do not infer that either scope is production implemented.** The legacy source candidate remains quarantined pending provenance, scope assignment, contract review, dependency/license/security review, and tests.
6. **Preserve decision authority boundaries.** CRFP may provide its defined evidence or assessment, but it does not create a second final product-display arbiter. CAL remains the sole SHOW/BLOCK/REVIEW display-arbitration authority under ADR-0001. FCI retains fit-confidence estimation and calibration; NPL and other explicit hard constraints retain their existing precedence.
7. **Do not promote by renaming.** Correcting the typo and defining scope does not make an archived candidate production-ready. Any implementation promotion requires the normal source-promotion gate.

## Required scope contracts

Before runtime integration, document and test each scope independently:

| Contract dimension | Marketplace CRFP | System-wide CRFP |
| --- | --- | --- |
| Primary responsibility | Marketplace-specific CRFP workflows and integration | Reusable CRFP capability across Cirvanna |
| Consumers | Marketplace BFF / Commerce / marketplace decision flow as specified | Approved cross-system services and product surfaces |
| Data ownership | Marketplace-owned data only where explicitly required | System-level domain data with explicit owner and tenant/user boundaries |
| Authorization | Marketplace roles and customer/merchant boundaries | Shared identity, service-to-service authorization, and consent rules |
| Failure behavior | Marketplace-safe degradation; no bypass of hard constraints or CAL | Explicit typed unavailable/unknown behavior; no bypass of consumer policy gates |
| Release gate | Marketplace contract and end-to-end storefront evidence | Cross-system contract, compatibility, and consumer integration evidence |

The table establishes boundaries, not unverified API details. Exact request/response schemas, event names, scoring semantics, persistence model, and version policy remain subject to authoritative specifications.

## Legacy candidate handling

The preserved candidate describes per-user signal reinforcement, confidence updates/decay, advisory adjustments, and a process-local actor queue. Its persistence adapters are simulated/incomplete; it does not establish durable distributed state, cross-process consistency, or a validated acceptance contract. This describes the candidate only and does not determine which CRFP scope it belongs to.

Retain its archive and hashes for provenance. Do not import it into either scope until a reviewed dossier maps its behavior to the correct scope and demonstrates compatibility.

## Promotion requirements

A proposal for either scope must include:

1. Source owner, authoritative specification, version, license, complete source bundle, hashes, and modifications.
2. A scope-specific responsibility statement, explicit non-responsibilities, and overlap analysis against FCI, USI, NPL, TAL, EEPL, CAL, Marketplace BFF, Catalog, and Commerce.
3. Versioned typed requests/responses, identifiers, units, null/unknown states, errors, reason codes, and compatibility policy.
4. State ownership, tenant/user isolation, consent, retention, deletion, replay, idempotency, concurrency, and migration semantics.
5. Scoring/assessment equations and evidence semantics where applicable, including uncertainty and calibration claims.
6. Explicit advisory/binding authority. Neither scope may create a second display arbiter or weaken hard constraints.
7. Trust boundaries, subject verification, candidate/product binding, source freshness, signing, authorization, and failure behavior.
8. Unit, property, contract, integration, adversarial, replay, and cross-scope isolation tests.
9. Operational evidence and rollback plan for any deployable implementation.

## Consequences

Current contributors must use the verified existing contracts and must not claim either CRFP scope is live solely because the name appears in documentation. The two scopes are now recognized architecturally; implementation maturity remains evidence-gated.

The historical source archive remains intact. The old CFRP spelling is treated only as a typo in historical provenance, never as a distinct current concept.
