# ADR-0003: CRFP marketplace and system-wide scopes

- **Status:** Accepted naming and scope decision; detailed runtime contracts remain open
- **Date:** 2026-11-03
- **Supersedes:** ADR-0002's incorrect separation of CRFP and CFRP

## Context

The product owner clarified that **CFRP was a typo**. The canonical acronym is **CRFP**. There are two CRFP scopes: one belongs to marketplace workflows; the other applies throughout Cirvanna. They share a name but are not interchangeable implementations.

## Decision

1. Use **CRFP** as the only canonical spelling in current architecture, code, contracts, documentation, and telemetry.
2. Treat **Marketplace CRFP** and **System-wide CRFP** as separate scopes with separately documented responsibilities, contracts, tests, and ownership.
3. System-wide CRFP defines shared semantics for the system. Marketplace CRFP defines the marketplace-specific scope and must integrate with shared system-wide contracts where applicable.
4. Do not collapse the two scopes into one generic implementation, and do not create a competing system-wide authority from marketplace-specific behavior.
5. Retain historical archive filenames and hashes when changing them would damage provenance. A historical CFRP filename is a known typo, not a separate capability.
6. Do not infer detailed CRFP semantics from the acronym or a historical source label. Runtime promotion requires the authoritative specification for each scope, typed/versioned contracts, explicit authority and failure semantics, tests, privacy/security review, and integration evidence.
7. FCI continues to own fit-confidence estimation and calibration. CAL remains the sole final SHOW/BLOCK/REVIEW display arbiter under ADR-0001 unless a separately reviewed ADR explicitly changes that architecture.

## Scope boundaries

| Dimension | System-wide CRFP | Marketplace CRFP |
|---|---|---|
| Reach | Across Cirvanna domains and system components | Marketplace workflows |
| Responsibility | Shared CRFP semantics and contract | Marketplace-specific CRFP requirements and integration |
| Contract | System-wide versioned contract | Marketplace-scoped contract compatible with shared semantics |
| Ownership | Shared system-wide CRFP ownership; accountable owner to be formally assigned | Marketplace-specific ownership; accountable owner to be formally assigned |
| Prohibited shortcut | Must not absorb marketplace-only assumptions | Must not fork or override shared system-wide authority |

The table establishes scope boundaries, not unverified business rules. Exact inputs, outputs, algorithms, data ownership, and authority semantics remain specification work.

## Consequences

- The source registry and migration inventory represent one CRFP concept with two scope entries.
- The old CFRP-vs-CRFP test is replaced with a regression test asserting both scopes exist and remain distinct.
- Historical source artifacts remain intact for lineage; no runtime implementation is promoted by this correction.
- Production readiness remains blocked until each scope's contract and integration evidence are verified.
