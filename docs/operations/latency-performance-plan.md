# Cirvanna latency and performance engineering plan

**Status: instrumentation expansion in progress. No production latency baseline or optimization gain is claimed.**

## Objective

Make shopper-facing journeys consistently responsive under realistic concurrency without weakening identity verification, consent, CAL arbitration, privacy controls, provider signatures, or commerce correctness.

## Measurement contract

Measure latency at the public Marketplace BFF and each downstream service. Report p50, p95 and p99, request rate, error rate, timeout rate, saturation and dependency-level duration. Segment by stable route template, service and outcome class only. Never label metrics with user, session, product, asset, image, merchant, query or token values.

Track end-to-end spans for Sanctuary and Wardrobe hydration; PNELLY daily looks and Complementer advisory; Marketplace discovery (Catalog, Commerce offers, ranking and CAL); Twin generation and try-on (queue wait separately from compute and media transfer); and cart/checkout (provider wait separately from internal processing).

## Initial diagnostic hypotheses from code review

These are investigation targets, not confirmed bottlenecks:

1. The Decision Gateway uses synchronous httpx calls in provider integrations and constructs short-lived HTTP clients in some paths. Connection reuse and pool sizing should be measured before refactoring.
2. Discovery joins Catalog and Commerce offers; record each upstream duration and payload/candidate count independently to identify serial or over-fetching costs.
3. Candidate decision processing fetches Catalog products in a bounded thread pool, then performs per-candidate evidence/profile work. Measure this stage by stage before batching or concurrency changes.
4. Some durable preference and evidence lookups occur inside candidate loops. Determine whether they are repeated network round trips, and batch only where service contracts preserve candidate binding, signed evidence and fail-closed semantics.
5. Image/Twin/try-on workloads need queue-wait, preprocessing, inference, postprocessing, object-store and CDN timing separated. Do not optimize model inference based on HTTP duration alone.

## Safe optimization order

1. Establish trustworthy per-service histograms and distributed trace correlation.
2. Capture reproducible baseline with cold and warm requests, realistic concurrency, representative payload sizes, and cache-hit/miss paths.
3. Optimize connection pooling, bounded concurrency and database query patterns where traces show measurable cost.
4. Introduce caching only for immutable or versioned public/reference data. User preferences, identity, consent, hard declarations, eligibility, CAL decisions, checkout state and private media must not be served from stale shared caches.
5. Add bounded asynchronous queues for expensive Twin/try-on tasks; return explicit job state and never present a completed result before the worker finishes.
6. Re-run identical load profiles and compare p50/p95/p99, throughput, 4xx/5xx, saturation and policy correctness.

## Proposed provisional targets (must be validated in staging)

| Journey | Provisional target |
|---|---:|
| Static public page assets (warm CDN) | p95 < 300 ms |
| Authenticated BFF read without expensive inference | p95 < 500 ms |
| PNELLY / discovery request excluding async model work | p95 < 1.0 s |
| Checkout internal processing excluding payment-provider wait | p95 < 500 ms |
| Twin / try-on | asynchronous job acceptance p95 < 300 ms; completion SLO defined by model and hardware benchmark |

These are planning targets, not achieved SLOs. Payment-provider, network, device and model-compute time must be reported separately rather than hidden inside an aggregate.

## Release gates

- Every critical service emits privacy-safe route-level histograms.
- Distributed trace IDs correlate BFF and internal calls without exposing identity.
- Load tests cover 1, 10, 25, 50 and 100 concurrent users with representative journeys.
- Compare cold-start and warm steady-state behavior.
- No optimization may bypass verified identity, consent, CAL, signed evidence, privacy deletion or payment idempotency.
- No release claim of fast without reproducible baseline and post-change comparison.