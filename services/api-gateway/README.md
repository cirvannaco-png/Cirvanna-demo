# API gateway / decision composition

**Status:** deterministic EEPL + NPL + explicit cultural policy → CaTaCaCi CAL composition implemented; HTTP routing, authentication, persistence, and production integration are not certified.

`app/decision_pipeline.py` composes typed domain results without calculating scores:

1. EEPL `PASS` supplies a context gate pass; `BLOCK` maps age bounds to legal-eligibility vetoes and location/occasion/climate violations to context vetoes; missing required context maps to unknown/review.
2. NPL hard exclusions map to CAL hard-veto signals. A clean NPL result only says no hard exclusion was found.
3. Cultural identity constraints are evaluated only from explicit user declarations. Hard conflicts map to CAL vetoes; incomplete candidate metadata maps to review. No cultural identity is inferred from appearance or demographic proxies.
4. The composed request is evaluated by CaTaCaCi CAL. Only CAL `SHOW` authorizes display; passing any individual gate never does.

The adapter checks candidate and user consistency and preserves source/policy versions. It intentionally has no HTTP framework, database access, or model inference. Production work remains: API schema/versioning, auth/consent, durable audit events, persistence adapters, observability, concurrency tests, and end-to-end request tests.

Run the current domain and integration tests from the repository root:

```bash
python -m unittest discover -s tests/architecture -v
python scripts/validate_architecture.py
```
