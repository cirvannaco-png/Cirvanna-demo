# CDIC TypeScript v7 — source candidate

This directory organizes the TypeScript generation labelled `CDIC .txt` from the uploaded `merged(0).txt` source bundle (source lines 3–1962). It is an isolated migration candidate, **not** promoted into Cirvanna runtime paths.

## Status

- Source files have been grouped by their internal imports under `src/`.
- No claim is made that this candidate builds, passes tests, meets latency claims, or is safe for production.
- Do not use this candidate's `APPROVED` result as a substitute for CaTaCaCi/CAL arbitration.
- Some small type/API adaptations were made during extraction to keep module boundaries explicit; compare against the original source snapshot when reconciling behavior.

## Known audit blockers

1. `OptimizedCache.set` increments the size counter when an existing key is replaced; `stats()` returns a hard-coded hit rate.
2. The final decision hash includes a wall-clock timestamp, so logically identical decisions may not be reproducible.
3. `CircuitBreaker` declares `halfOpenMaxAttempts` but does not enforce it.
4. Identity recognition is based on a fixed list; unknown identity values are not explained to users.
5. Garment coverage is inferred with keyword heuristics. It is not reliable enough to enforce cultural or modesty policy without explicit user rules and tests.
6. The original entry point had a timer-based console-metrics side effect; this candidate omits that side effect.
7. The snapshot did not include verified test results or a dependency lockfile.

## Promotion gate

Align the typed decision contract with CaTaCaCi, fix determinism and cache/circuit-breaker semantics, add validation/identity/coverage/precedence regression tests, run typechecking and secret/dependency scans, and complete architectural review before connecting this candidate to any application or service.
