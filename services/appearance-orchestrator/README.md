# Appearance Orchestrator — initial implementation

**Status: executable library slice; no public HTTP route is exposed.**

The read-only adapter consumes the canonical Catalog Service. Domain evaluation lives in
`packages/appearance-intelligence`. This does not create a new product database, write
catalog data, or own checkout/payments.

## Included in this increment

- Authenticated read-only pagination of `GET /products` with complete-snapshot validation.
- Seven registered domains: Hair, Face, Skin, Look, Footwear, Makeup, and Skincare.
- Canonical NPL hard-negative enforcement and CaTaCaCi/CAL arbitration.
- `SHOW` is the only display authorization. `BLOCK` and `REVIEW` remain non-displayable.
- Look + Makeup composition uses catalog-declared compatibility metadata and re-arbitrates the bundle total and bundle-level evidence.

## Limits

- Hair/face image inference, virtual makeup, virtual try-on, stock/availability, size/comfort prediction, and model ranking are unavailable.
- Skin reports `provider_unavailable` until DermalSight has a validated model artifact and signed validation report.
- Skincare does catalog metadata matching only; it does not diagnose, prescribe treatment, or guarantee ingredient safety.
- Safety/legal/fit signals and NPL rows must come from trusted server-side providers. They must never be client-supplied. An omitted NPL snapshot is UNKNOWN and forces CAL REVIEW; pass an explicit empty preference tuple only after the canonical NPL store successfully confirms there are no active preferences for that user. Cross-user rows are rejected.
- There is intentionally no public endpoint until trusted identity, NPL persistence, evidence provenance, rate limiting, audit receipts, and checkout revalidation are wired through the gateway.

## Configuration

Set `CATALOG_BASE_URL` and a read-only `CATALOG_READ_TOKEN` of at least 32 bytes. Remote URLs must use HTTPS; HTTP is allowed only for loopback development. Pagination failures, duplicate IDs, invalid records, a moving total, and over-limit snapshots fail closed. The catalog API currently has no point-in-time snapshot token or transaction boundary; the adapter detects total changes and duplicates but cannot guarantee atomic consistency if catalog records change between page reads. Do not treat this read as checkout/stock revalidation.

Run tests from the repository root:

```bash
PYTHONPATH=packages/appearance-intelligence:packages/identity-intelligence:packages/preferences:services/appearance-orchestrator \
  python -m pytest tests/appearance_intelligence -q
```

Tests use fixtures and an HTTP mock. They prove contract wiring, not model accuracy or production readiness.
