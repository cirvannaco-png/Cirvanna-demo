# Governance Evidence Provider

**Status: implementation candidate; not production-ready.** This internal service assembles a request-bound envelope for the canonical CAL decision service. It does not make decisions and does not invent evidence.

## Data flow

1. Marketplace BFF authenticates the customer through Commerce `/me` and submits the authenticated subject plus canonical catalog product ID.
2. This service reads the active product from Catalog and derives attributes only from catalog metadata.
3. It calls NPL `/v1/evaluate` and Cultural Identity `/v1/evaluate`, forwarding the same request, user, candidate and attributes so their HMAC signatures bind the same context.
4. It fetches the user-scoped USI profile and user context from configured trusted providers, and asks the trusted fit provider for a signed estimate.
5. It returns the exact decision-service request plus short-lived envelope/source freshness timestamps. The existing BFF calls `POST /v1/eligibility/evaluate`; CAL remains the only authorization authority.

Any missing, stale, unsigned, malformed, mismatched or unavailable source returns an error. The BFF must continue to suppress candidates on every error. Product IDs passed to this service must be canonical Catalog product UUIDs; variant/offer IDs are not silently treated as product IDs.

## Required private upstream contracts

- Catalog: `GET /products/{product_id}` returns `product_id`, `status=active`, and a non-empty `attributes` object.
- NPL: `POST /v1/evaluate` accepts request/user/candidate/attributes and returns matching identifiers, `negative_preferences`, and a 64-character `npl_evidence_signature`.
- Cultural Identity: same request fields plus `candidate_attributes_complete`; returns matching identifiers, active `cultural_requirements`, `verdict`, and a 64-character `cultural_evidence_signature`.
- USI profile provider: `GET /v1/profiles/{user_id}` returns a user-bound `usi_profile` with non-empty preferences and an `eepl_policy`.
- User context provider: `GET /v1/context/{user_id}` returns matching `user_id` and a `context` object whose `user_id` is the authenticated subject.
- Fit evidence provider: `POST /v1/estimate` accepts request/user/candidate/attributes/context and returns `fit_estimate`, `fit_estimate_signature`, and a fresh timezone-aware `generated_at`. It must sign the decision service's canonical normalized FitEvidenceIn payload with `FCI_EVIDENCE_HMAC_SECRET`. A signature alone does not establish scientific validity or calibration.

USI profile, user-context and fit-model providers are not currently demonstrated as deployed in this repository. Until they exist and pass live tests, readiness and product exposure must remain blocked.

## Environment

Set `EVIDENCE_PROVIDER_TOKEN`, `NPL_SERVICE_URL`, `NPL_SERVICE_TOKEN`, `CULTURAL_IDENTITY_SERVICE_URL`, `CULTURAL_IDENTITY_SERVICE_TOKEN`, `CATALOG_API_URL`, `CATALOG_API_TOKEN`, `USI_PROFILE_API_URL`, `USI_PROFILE_API_TOKEN`, `USER_CONTEXT_API_URL`, `USER_CONTEXT_API_TOKEN`, `FIT_EVIDENCE_API_URL`, and `FIT_EVIDENCE_API_TOKEN` in a secret manager. Tokens must be at least 32 bytes. Upstream URLs must be HTTPS except loopback HTTP in local development. Keep this service off public ingress.

## Validation

`python -m pytest -q` tests provider contract and fail-closed behavior with controlled test doubles. This is not a substitute for live PostgreSQL, real internal authentication, shared HMAC key, model calibration, or staging end-to-end tests.
