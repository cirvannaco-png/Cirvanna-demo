# Cirvanna latency engineering plan

## Objective

Reduce shopper-perceived latency across marketplace browsing, PNELLY discovery, Wardrobe recommendations and authenticated account journeys without weakening CAL, consent, identity, ownership, or privacy controls.

This document is a measurement-first plan. No performance improvement is claimed until repeatable before/after measurements exist on the same deployment class and workload.

## Initial repository findings

- The Marketplace BFF creates short-lived `httpx.AsyncClient` instances inside multiple request handlers and helper functions. This prevents connection pools and keep-alive connections from being reused across requests, adding avoidable TCP/TLS setup latency to repeated Commerce, Decision Gateway, Identity and PNELLY calls.
- Several shopper journeys make serial upstream calls. The wardrobe recommendation path verifies the Commerce subject before calling the Decision Gateway; other paths combine identity, consent and policy-provider calls. Each dependency's contribution must be measured before changing call order.
- The BFF's `/ready` checks are synchronous HTTP calls. Readiness should not be on shopper request paths, and health probes must remain bounded.
- The Decision Gateway is a security-critical composition boundary. Optimizations must not cache user-specific policy, consent, cultural declarations, age/identity evidence, CAL decisions or purchase authorization in a way that can outlive their validity.

## Measurement protocol

Capture a baseline before changing runtime behavior.

For each route, record:
- request count and error rate;
- p50, p95 and p99 end-to-end latency;
- BFF/gateway self-time and each upstream span;
- connection reuse versus new connection count;
- upstream timeout, retry and saturation counts;
- cold-start versus warm steady-state latency;
- payload size and concurrency level.

Run the same scenarios at concurrency 1, 10 and 25, with warm-up excluded from steady-state results. Include normal responses, slow upstreams, timeouts, malformed upstream responses and provider outages. Preserve trace/request correlation while redacting bearer tokens, user identifiers, image content and policy evidence.

Priority shopper journeys:
1. Marketplace first-page offers.
2. PNELLY conversational discovery.
3. Wardrobe recommendations and daily looks.
4. Authenticated account/cart reads.
5. Consent-bound image/appearance operations (measure separately; do not compare these to simple JSON routes).

## Safe optimization sequence

1. Add or standardize route and dependency timing spans with low-cardinality labels. Do not log secrets, user IDs, raw prompts, photos, or policy payloads.
2. Reuse one lifespan-managed `httpx.AsyncClient` per service process with explicit connection limits, keep-alive expiry, timeouts, TLS verification, `trust_env=False`, and redirects disabled. Close it during application shutdown. Keep dependency-specific timeout overrides where required.
3. Use bounded concurrency only for independent read-only dependency calls. Do not parallelize steps whose order establishes identity, consent, authorization, revocation, or policy freshness.
4. Add caching only for public, immutable or versioned data. Never cache personalized responses or authorization/policy results without an explicit, reviewed freshness and invalidation design. All account and sensitive responses remain private/no-store.
5. Add load tests and regression thresholds only after collecting a representative baseline. Avoid arbitrary targets that hide slow dependencies or cold starts.

## Acceptance gates

- No regression in auth, CAL, CIL, consent, ownership, privacy deletion, or fail-closed behavior.
- A repeatable baseline and before/after report are attached to the change.
- p50/p95/p99 and error rates are reported per critical journey, not just a single aggregate.
- Connection reuse is demonstrated under repeated requests.
- Slow and unavailable dependencies remain bounded by explicit timeouts; no uncontrolled retries or retry amplification.
- Container and service tests pass; staging load tests use dedicated staging credentials and synthetic accounts only.

## Out of scope for this first pass

- Relaxing CAL or bypassing policy calls to improve response time.
- Caching user profiles, declarations, consent, identity, signed evidence, or display/purchase decisions.
- Reducing image safety checks, deletion guarantees, or model validation.
- Claiming production performance from unit tests or local-only benchmarks.
