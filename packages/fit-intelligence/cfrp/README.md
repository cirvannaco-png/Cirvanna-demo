# CRFP — canonical scope index

**Canonical spelling:** CRFP. The former CFRP spelling was a typo, not a separate capability.

CRFP has two separately owned scopes:

- [System-wide CRFP](system/README.md) — the CRFP scope used throughout Cirvanna.
- [Marketplace CRFP](marketplace/README.md) — the CRFP scope belonging to marketplace workflows.

Keep the scopes distinct in contracts, configuration, telemetry, tests, and ownership. Marketplace integration must consume the system-wide contract where applicable and must not create a conflicting system-wide authority. The precise functional responsibilities, typed interfaces, and authority semantics must be recovered from the authoritative CRFP specifications before runtime implementation is promoted.

The historical source artifact retains its original filename under integration-staging for provenance; its CFRP spelling is a known typo. It is not a second acronym or a reason to maintain a parallel package.

**Current maturity:** Scope ownership is documented; runtime contracts and production implementations are not yet verified. FCI continues to own fit-confidence estimation. CAL remains the sole final SHOW/BLOCK/REVIEW display arbiter.
