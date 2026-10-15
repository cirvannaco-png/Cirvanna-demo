# API gateway / decision composition

**Status:** initial deterministic EEPL + NPL → CaTaCaCi CAL composition implemented; HTTP routing, authentication, persistence, and production integration are not certified.

`app/decision_pipeline.py` composes typed domain results without calculating scores:

1. EEPL `PASS` supplies a context gate pass; `BLOCK` maps age bounds to legal-eligibility vetoes and location/occasion/climate violations to context vetoes; missing required context maps to unknown/review.
2. NPL hard exclusions map to CAL hard-veto signals. A clean NPL result only says no hard exclusion was found.
3. The composed request is evaluated by CaTaCaCi CAL. Only CAL `SHOW` authorizes display; NPL/EEPL passing alone never does.

The adapter checks candidate and user consistency and preserves source/policy versions. It intentionally has no HTTP framework, database access, or model inference. Production work remains: API schema/versioning, auth/consent, durable audit events, persistence adapters, observability, concurrency tests, and end-to-end request tests.

Run the current domain and integration tests from the repository root:

```bash
python -m unittest discover -s tests/architecture -v
python scripts/validate_architecture.py
```
