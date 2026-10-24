# Governance Evidence Provider

**Status: implementation candidate; not production-ready.** This internal service assembles a request-bound envelope for the canonical CAL decision service. It does not make decisions and does not invent evidence.

## Data flow

1. Marketplace BFF authenticates the customer through Commerce `/me` and submits the authenticated subject plus canonical catalog product ID.
2. This service reads the active product from Catalog and derives attributes only from catalog metadata.
3. It calls NPL `/v1/evaluate` and Cultural Identity `/v1/evaluate`, forwarding the same request, user, candidate and attributes so their HMAC signatures bind the same context.
4. It fetches the user-scoped USI profile and user context from configured trusted providers, and asks the trusted fit provider for a signed estimate.
5. It fetches independent safety, legal-eligibility and user-hard-constraint signals from a private policy-evidence provider. It validates their request/user/candidate/catalog binding and HMAC over canonical policy evidence before including them in the decision request.
6. It returns the exact decision-service request plus short-lived envelope/source freshness timestamps. The existing BFF calls `POST /v1/eligibility/evaluate`; CAL remains the only authorization authority.

Any missing, stale, unsigned, malformed, mismatched or unavailable source returns an error. The BFF must continue to suppress candidates on every error. The request must provide separate canonical UUIDs for the exact candidate/variant and its canonical Catalog product; they are never silently substituted for one another.

## Required private upstream contracts

- Catalog: `GET /products/{product_id}` returns `product_id`, `status=active`, and a non-empty `attributes` object.
- NPL: `POST /v1/evaluate` accepts request/user/candidate/attributes and returns matching identifiers, `negative_preferences`, and a 64-character `npl_evidence_signature`.
- Cultural Identity: same request fields plus `candidate_attributes_complete`; returns matching identifiers, active `cultural_requirements`, `verdict`, and a 64-character `cultural_evidence_signature`.
- USI profile provider: `GET /v1/profiles/{user_id}` returns a user-bound `usi_profile` with non-empty preferences and an `eepl_policy`.
- User context provider: `GET /v1/context/{user_id}` returns matching `user_id` and a `context` object whose `user_id` is the authenticated subject.
- Fit evidence provider: `POST /v1/estimate` accepts request/user/candidate/catalog/attributes/context and returns `fit_estimate`, `fit_estimate_signature`, and a fresh timezone-aware `generated_at`. It must sign the decision service's canonical normalized FitEvidenceIn payload with `FCI_EVIDENCE_HMAC_SECRET`. Its `/ready` must attest `fci_prediction_model_available=true` and `calibration_report_valid=true`.
- Policy evidence provider: `POST /v1/evaluate` accepts request/user/candidate/catalog/attributes/context and returns the same IDs plus `upstream_signals` containing required `safety`, `legal_eligibility`, and `user_hard_constraint` gates, and a 64-character `policy_evidence_signature`. HMAC-SHA256 uses `POLICY_EVIDENCE_HMAC_SECRET` over canonical JSON with keys `contract_version, request_id, user_id, candidate_id, catalog_product_id, candidate_attributes, upstream_signals`; candidate attributes are unique sorted casefolded strings; signals are normalized to `signal_id,kind,state,reason_code,explanation,required,confidence,source_version` and sorted by signal_id; serialize sorted compact UTF-8 JSON with `ensure_ascii=false` and `allow_nan=false`. Missing kinds or invalid HMAC fail closed.

Readiness probes each configured upstream `/ready` endpoint; URL and credential configuration alone no longer make the evidence provider ready. The fit provider must additionally return `fci_prediction_model_available=true` and `calibration_report_valid=true`. A valid HMAC proves provenance, not calibration or fit quality. The repository contains a persistent USI/context implementation candidate at `services/usi-context-service`, but no trained, calibrated fit-model provider is implemented here. Until these services are deployed, migrated and validated, readiness and product exposure remain blocked.

## Environment

Set `EVIDENCE_PROVIDER_TOKEN`, `NPL_SERVICE_URL`, `NPL_SERVICE_TOKEN`, `CULTURAL_IDENTITY_SERVICE_URL`, `CULTURAL_IDENTITY_SERVICE_TOKEN`, `CATALOG_API_URL`, `CATALOG_API_TOKEN`, `USI_PROFILE_API_URL`, `USI_PROFILE_API_TOKEN`, `USER_CONTEXT_API_URL`, `USER_CONTEXT_API_TOKEN`, `FIT_EVIDENCE_API_URL`, `FIT_EVIDENCE_API_TOKEN`, `POLICY_EVIDENCE_API_URL`, `POLICY_EVIDENCE_API_TOKEN`, and `POLICY_EVIDENCE_HMAC_SECRET` in a secret manager. Tokens must be at least 32 bytes. Upstream URLs must be HTTPS except loopback HTTP in local development. Keep this service off public ingress.

## Validation

`python -m pytest -q` tests provider contract and fail-closed behavior with controlled test doubles. This is not a substitute for live PostgreSQL, real internal authentication, shared HMAC key, model calibration, or staging end-to-end tests.
