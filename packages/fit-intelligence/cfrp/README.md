# CFRP V6 — quarantined candidate marker

**Lifecycle:** Candidate / not importable as canonical runtime.  
**Authority:** None. No supported public API, event, schema, scoring authority, veto authority, or deployable service is defined here.

This directory is an intake/status marker only. The preserved CFRP V6 source remains under `integration-staging/source-candidates/05-cfrp-v6.txt/`. Do not copy candidate code into this path or import it from application/service code.

The separately referenced **CRFP** confidence/acceptance concept is not an established implementation and is not an alias for CFRP. The inspected CFRP V6 candidate concerns per-user signal reinforcement, confidence updates/decay, and advisory adjustments. Its persistence adapters are simulated/incomplete; it does not establish durable distributed state or production acceptance semantics.

Use FCI for the current fit-confidence contract and CAL as the sole final SHOW/BLOCK/REVIEW display arbiter. Any proposal to merge, rename, replace, or implement CRFP/CFRP must first satisfy [ADR-0002](../../../docs/architecture/adr/ADR-0002-crfp-cfrp-contract-status.md) and pass the controlled promotion process. Preserve this marker and archive lineage until a superseding ADR records a disposition.