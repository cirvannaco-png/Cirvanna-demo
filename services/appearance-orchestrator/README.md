# Appearance Orchestrator — initial implementation

**Status: executable library slice; no public HTTP route is exposed.**

The read-only adapters consume the canonical Catalog Service and the existing NPL Service.
Domain evaluation lives in `packages/appearance-intelligence`; the internal application
wiring lives in `orchestrator.py`. This does not create a new product database, duplicate the
preference ledger, write catalog data, or own checkout/payments.

## Included in this increment

- Authenticated read-only pagination of the canonical catalog's `GET /products` endpoint with bounded pagination validation.
- Authenticated read-only loading of the current user's preference records from the canonical NPL Service.
- Internal application methods that wire catalog + NPL reads into specialist evaluation and Look + Makeup composition.
- Seven registered domains: Hair, Face, Skin analysis, Look, Footwear, Makeup, and Skincare.
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

Install the adapter's declared runtime dependency and the test runner, then run tests from the repository root:

```bash
python -m pip install -r services/appearance-orchestrator/requirements.txt "pytest>=8,<9"
PYTHONPATH=packages/appearance-intelligence:packages/identity-intelligence:packages/preferences:services/appearance-orchestrator \
  python -m pytest tests/appearance_intelligence -q
python -m pytest tests/architecture/test_catacaci_core.py -q
```

Tests use fixtures and an HTTP mock. They prove contract wiring, not model accuracy or production readiness.
