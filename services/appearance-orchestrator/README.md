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
- Safety/legal/fit signals must come from trusted server-side providers. They must never be client-supplied. The orchestrator loads NPL rows using the internal bearer-authenticated NPL API; only a successful response whose user scope matches the authenticated context is accepted. An unavailable read returns REVIEW and no candidates. The lower-level evaluator's omitted NPL snapshot remains UNKNOWN; an explicit empty tuple is valid only after a successful canonical read. Cross-user rows are rejected.
- The current NPLClient reads the NPL Service over the authenticated internal channel; it does not verify an HMAC response envelope for the list endpoint. Keep this API on trusted internal ingress. For lower-trust service crossings or signed candidate-bound evidence, use the canonical NPL `/v1/evaluate` envelope and verify its HMAC as the decision service does.
- There is intentionally no public endpoint until trusted identity, NPL persistence, evidence provenance, rate limiting, audit receipts, and checkout revalidation are wired through the gateway.

## Configuration

Set `CATALOG_BASE_URL` and `CATALOG_READ_TOKEN`, plus `NPL_BASE_URL` and `NPL_SERVICE_TOKEN`; both tokens must be at least 32 bytes. Remote URLs must use HTTPS; HTTP is allowed only for loopback development. Keep both services on trusted internal ingress. Pagination failures, duplicate IDs, invalid records, a moving total, and over-limit snapshots fail closed. The catalog API currently has no point-in-time snapshot token or transaction boundary; the adapter detects total changes and duplicates but cannot guarantee atomic consistency if catalog records change between page reads. Do not treat this read as checkout/stock revalidation.

Install the adapter's declared runtime dependency and the test runner, then run tests from the repository root:

```bash
python -m pip install -r services/appearance-orchestrator/requirements.txt "pytest>=8,<9"
PYTHONPATH=packages/appearance-intelligence:packages/identity-intelligence:packages/preferences:services/appearance-orchestrator \
  python -m pytest tests/appearance_intelligence -q
python -m pytest tests/architecture/test_catacaci_core.py -q
```

Tests use fixtures and an HTTP mock. They prove contract wiring, not model accuracy or production readiness.
