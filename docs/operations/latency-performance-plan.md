# Cirvanna latency and performance engineering plan

**Status: baseline measurement and optimization are in progress. No production latency improvement is claimed until staging measurements confirm it.**

## 1. Objective

Make shopper-facing journeys consistently responsive under realistic concurrency without weakening verified identity, consent, CAL arbitration, privacy controls, signed evidence, deletion guarantees or commerce correctness.

## 2. Current implementation verified in `main`

- Decision Gateway request counters and histograms are installed through the shared `packages/http_observability` module.
- Dependency histograms use configured, bounded dependency names and record Catalog and Commerce request durations separately.
- Marketplace discovery fetches Catalog product facts and Commerce offers concurrently because those reads are independent. Both remain mandatory; response validation, active-catalog filtering and the canonical product-offer join remain in place.
- A concurrency regression test proves both upstream calls overlap. This verifies concurrency behavior, not real network latency or production throughput.
- Metrics are process-local. The authenticated `/internal/metrics` endpoint must be reachable only from a private monitoring network; the bearer token alone is not a network boundary.

## 3. What must be measured

Capture p50, p95 and p99, throughput, error/timeout rate, saturation and dependency durations. Segment only by service, stable route template, HTTP method, status and allowlisted dependency. Never use user IDs, session IDs, product IDs, image/asset IDs, merchant IDs, raw queries, URLs or tokens as metric labels.

Measure these journeys end to end:

1. Sanctuary and Wardrobe initial hydration and subsequent navigation.
2. PNELLY daily looks and Complementer advisory, separating identity/profile reads from recommendation computation.
3. Marketplace discovery: BFF, Catalog, Commerce offers, ranking, candidate evidence, CAL decision and response serialization.
4. Virtual Twin and try-on: queue wait, image preprocessing, model inference, postprocessing, storage and CDN transfer separately.
5. Cart and checkout: internal validation, inventory/fulfilment, payment-provider wait and idempotent result handling separately.

Use request IDs for correlation. Do not record request bodies, query values, image content, biometric data, authorization headers or sensitive exception payloads.

## 4. Next bottleneck investigations

These are hypotheses, not established bottlenecks:

- Candidate decision processing performs bounded parallel Catalog retrieval followed by per-candidate evidence/profile work. Determine whether repeated preference, consent or evidence reads dominate before batching.
- Several Decision Gateway integrations create short-lived HTTP clients. Measure DNS/connect/TLS, connection reuse and upstream wait before introducing lifespan-managed pools.
- Marketplace BFF and gateway may each call overlapping services. Distributed traces must reveal duplicate work and serial dependencies before removing calls.
- Twin/try-on latency may be dominated by queueing, image transfer or GPU contention rather than application code. Measure each stage independently.
- Database latency must be split into pool wait, query execution, lock wait and serialization. Inspect query plans before adding indexes.

## 5. Safe optimization sequence

1. Establish staging baselines with cold-start and warm steady-state runs, realistic payloads and fixed data fixtures.
2. Run concurrency profiles at 1, 10, 25, 50 and 100 simultaneous shopper sessions. Include p50/p95/p99, throughput, 4xx/5xx, timeouts, CPU, memory, connection-pool saturation and queue depth.
3. Use traces to identify the dominant critical path. Optimize only the measured hot path.
4. Prefer connection reuse, bounded concurrency, request coalescing and database query improvements when evidence supports them.
5. Cache only immutable or versioned public/reference data. Never serve identity, consent, hard declarations, eligibility, CAL decisions, checkout state or private media from stale shared caches.
6. Keep expensive Twin/try-on work in bounded asynchronous jobs. Return explicit job state; never label a result complete before inference and postprocessing finish.
7. Re-run the identical load profile and compare before/after latency and correctness.

## 6. Provisional staging targets

| Journey | Provisional target |
|---|---:|
| Warm public page assets | p95 < 300 ms |
| Authenticated BFF read without model inference | p95 < 500 ms |
| PNELLY/discovery excluding asynchronous model work | p95 < 1.0 s |
| Checkout internal processing, excluding payment-provider wait | p95 < 500 ms |
| Twin/try-on job acceptance | p95 < 300 ms; completion target set after model/hardware benchmark |

These are proposed targets, not achieved SLOs. Separate device/network, external provider and model-compute time from Cirvanna internal processing.

## 7. Release gates

- Every critical synchronous service emits privacy-safe request and dependency histograms.
- Distributed trace correlation spans BFF through internal services without identity leakage.
- Representative load tests run against staging, not developer mocks alone.
- Cold and warm performance are reported separately.
- No performance optimization bypasses verified identity, consent, CAL, signed evidence, privacy deletion or payment idempotency.
- No production speed claim without reproducible baseline and post-change comparison.

## 8. Current limitation

Code-level metrics and concurrent Catalog/Commerce reads are present in `main`. Central collector configuration, distributed tracing backend, dashboards, alert routing, production ingress restrictions for metrics, and staging load-test evidence are not yet verified. The next engineering task is to establish that measurement pipeline, then optimize the measured critical path.