# System-wide CRFP

**Scope:** CRFP as it applies throughout Cirvanna, across the relevant product domains and system components.

This is a distinct scope of the canonical CRFP concept, not a spelling variant of marketplace CRFP. Its system-wide contract must define the shared semantics and boundaries consumed by domain packages and services.

## Integration constraints

- Define one versioned system-wide contract and its authoritative owner.
- Specify which domains consume it and the explicit non-responsibilities of each consumer.
- Keep marketplace-specific behavior in the marketplace CRFP scope; do not leak marketplace-only assumptions into global policy.
- Do not duplicate FCI fit-confidence estimation or CAL final SHOW/BLOCK/REVIEW arbitration.
- Do not claim runtime capability until the authoritative specification, typed interfaces, tests, security/privacy review, and operational evidence are verified.

**Status:** Scope confirmed by product owner; detailed specification and runtime implementation not yet verified.
