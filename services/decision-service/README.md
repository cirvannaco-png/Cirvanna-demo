# Cirvanna Decision Service

**Status: authenticated CAL/eligibility adapter; no trained FCI predictor is included.**

This service executes the repository's existing deterministic eligibility pipeline from the canonical packages:
- EEPL context/eligibility policy
- NPL hard-negative vetoes
- USI explicit positive-preference alignment
- FCI calibrated-estimate contract
- CaTaCaCi CAL final arbitration

Only the actual CAL verdict SHOW authorizes display. BLOCK is a hard veto; REVIEW is fail-closed. No weighted blended score replaces CAL. Generated EEPL/NPL/USI/FCI signals cannot be injected as upstream signals by the caller; request schema only permits independent safety, legal, hard-constraint, cultural, and other evidence.

## Endpoint

POST /v1/eligibility/evaluate

The service also exposes `GET /v1/cal/feedback-reviews` and `POST /v1/cal/feedback-reviews/{review_id}/decision` as the authenticated CAL bridge to the CIL review queue. The queue contains minimum-cohort recommendation feedback signals; CAL operators review them and submit a final SHOW/BLOCK verdict. When `CIL_CAL_REVIEW_ENFORCEMENT_REQUIRED=true`, the Decision Service also looks up the latest final decision for each product/context during eligibility evaluation. A matching CAL BLOCK becomes a hard veto; a feedback SHOW cannot override the normal EEPL, NPL, FCI, safety or CaTaCaCi result.

All endpoints require Authorization: Bearer with the internal shared token. Configure `CIL_SERVICE_URL`, `CIL_SERVICE_TOKEN`, and `CIL_CAL_SERVICE_TOKEN` to connect the bridge. The Decision Service uses its own internal token for callers, a service token to read the CIL queue, and the CAL-specific token to submit final decisions. Requests fail closed if the bridge is not configured or CIL is unavailable.

## Server-owned CaTaCaCi/CAL policy

The service selects the active CAL policy ID from the server-only `CATACACI_POLICY_ID` setting and resolves its active version and all decision thresholds from `CATACACI_POLICY_REGISTRY_JSON`. The request cannot select a policy ID/version or supply fit-confidence and alignment thresholds; those fields are rejected by the strict request schema. Each registry entry must contain exactly:

```json
{
  "standard-marketplace": {
    "policy_version": "marketplace-policy-1",
    "minimum_fit_confidence": 0.70,
    "maximum_fit_confidence_disagreement": 0.10,
    "minimum_alignment_score": 0.60
  }
}
```

These are illustrative engineering values, not empirically calibrated product-fit claims. A missing, malformed, unregistered or stale policy causes readiness/evaluation to fail closed. Policy changes must be reviewed, versioned and tested before deployment. Do not copy the example JSON into a production secret manager without policy-owner approval and validation.

## Trusted fit evidence

The service does not contain or claim to train/run an FCI predictor. A separately trusted fit provider must send a FitEvidenceIn object and compute a lowercase hex HMAC-SHA256 signature over its normalized JSON:
- serialize the FitEvidenceIn model with all fields (including null/default values),
- use UTF-8 JSON with sorted keys, compact separators, and ensure_ascii=false,
- sign the bytes with FCI_EVIDENCE_HMAC_SECRET.

The service independently canonicalizes and verifies the signature before evaluating CAL. An uncalibrated but validly signed estimate becomes UNKNOWN in FCI and must result in REVIEW, not SHOW. The HMAC proves the payload came from a holder of the trusted key; it does not prove the provider's science or calibration quality. A production provider still needs empirical calibration, model governance and access controls.

## Server-authoritative EEPL policy

The Decision Service resolves the active EEPL policy ID, version, age thresholds, location/occasion/climate allowlists and required-context rules exclusively from `EEPL_POLICY_ID` and `EEPL_POLICY_REGISTRY_JSON` in server configuration. The legacy `eepl_policy` request field is retained temporarily for wire compatibility but is ignored; it cannot select a policy or alter a rule. The same resolver and registry are used by Identity Learning and the API Gateway. An absent, malformed or unregistered active policy fails closed with `SERVER_POLICY_UNAVAILABLE`. Both Gateway and Decision Service also resolve the active CaTaCaCi policy from `CATACACI_POLICY_ID` / `CATACACI_POLICY_REGISTRY_JSON`; the caller cannot choose fit or alignment thresholds.

A verified age attestation must also be redeemed through the private Identity Learning endpoint before it influences EEPL. Configure `AGE_EVIDENCE_REDEMPTION_URL` as the HTTPS URL ending in `/internal/v1/age-evidence/attestations/redeem` and `AGE_EVIDENCE_REDEMPTION_TOKEN` as the separate machine credential. If redemption is unavailable, replayed, revoked or expired, the Decision Service fails closed; a valid HMAC alone is insufficient.

## Configuration

- DECISION_SERVICE_TOKEN: long random internal bearer token; protect service network access as well.
- `CATACACI_POLICY_ID`: server-selected active CAL policy identifier.
- `CATACACI_POLICY_REGISTRY_JSON`: server-owned, version-pinned CAL thresholds; callers cannot select policy identity/version or supply thresholds.
- FCI_EVIDENCE_HMAC_SECRET: separate strong secret shared only with the approved fit provider.
- `CIL_SERVICE_URL`: private HTTPS URL for the Intelligence Service (HTTP only for loopback development).
- `CIL_SERVICE_TOKEN`: internal token for reading the CIL review queue.
- `CIL_CAL_SERVICE_TOKEN`: CAL-only token for recording final review decisions and retrieving final product/context decisions from CIL.
- `CIL_CAL_REVIEW_ENFORCEMENT_REQUIRED`: keep false until the CIL service, latest-decision endpoint and CAL credentials are deployed and verified; set true in production only after the end-to-end gate test passes.
- `CAL_REVIEW_OPERATOR_TOKEN`: separate credential required by the final-decision endpoint; do not reuse the general Decision Service token.
- DECISION_DOCS_ENABLED is not currently used; do not expose this internal service publicly.

Run locally from this directory:

    python -m venv .venv
    . .venv/bin/activate
    pip install -r requirements.txt
    export DECISION_SERVICE_TOKEN='replace-with-strong-random-secret-at-least-32-bytes'
    export FCI_EVIDENCE_HMAC_SECRET='use-a-different-strong-random-secret'
    uvicorn app.main:app --host 127.0.0.1 --port 8082

The module imports existing packages from the monorepo. Do not run this Dockerfile with the service directory as build context; build from repository root:

    docker build -f services/decision-service/Dockerfile -t cirvanna-decision .

## Boundaries still open

- No FCI prediction model, model weights, inference provider or empirical calibration study is part of this repository. The signed estimate contract validates provenance shape, not model accuracy.
- The internal gateway must provide independently computed safety/legal/cultural signals; missing required evidence yields REVIEW.
- Durable decision audit/replay storage, access audit, key rotation, policy approval and retention/deletion need operational integration.
- The internal eligibility response is not a public product-serving API. Customer-facing product details flow through API Gateway `/v1/discover`, which applies candidate-bound CAL and CIL claim/ingredient checks; when `CIL_CAL_REVIEW_ENFORCEMENT_REQUIRED=true`, it also loads the latest context-scoped human CAL feedback decision and treats BLOCK as a veto. A later SHOW never overrides the ordinary policy pipeline. Commerce independently verifies signed candidate-bound purchase authorization at cart and checkout. Do not enable the enforcement flag until the CIL service and separate CAL credential are deployed and the cross-service staging test passes.
- This adapter does not produce Click It reconstructions, Virtual Twin geometry or try-on imagery; those require validated model/rendering integrations.


## Trusted NPL evidence

The decision endpoint also requires `NPL_EVIDENCE_HMAC_SECRET`, shared only with the trusted NPL service. The signature binds the request ID, user ID, candidate ID, normalized candidate attributes and the complete user-scoped negative-preference envelope. Missing, foreign-user or modified NPL evidence fails before CAL evaluation. This verification proves provenance from a key holder; it does not replace end-to-end identity validation, service authorization or a deployed NPL integration.


## Trusted cultural declaration evidence

The decision endpoint requires `CULTURAL_IDENTITY_HMAC_SECRET` and verifies a candidate-bound Cultural Identity evidence envelope before evaluation. The signature binds request ID, user ID, candidate ID, normalized candidate attributes, metadata completeness and the active declaration requirement set. Modified or foreign-user declaration evidence fails before CAL runs. The service key must be shared only with the trusted Cultural Identity service/consumer chain; an internal API token alone does not prove that a cultural declaration is genuine.


## Verified threshold age evidence

The eligibility endpoint never uses request-body `context.age_years`. It accepts age evidence only as a separately HMAC-signed, closed-contract threshold attestation from the age-evidence service. The verifier binds subject ID, request ID, the fixed `shopper_eligibility` purpose, exact EEPL policy ID/version and minimum-age threshold, and enforces the attestation freshness/maximum TTL contract. A valid OVER result supplies only the threshold and boolean outcome to EEPL; an under-threshold result blocks, while missing/untrusted evidence routes to REVIEW. Threshold-only evidence cannot satisfy a maximum-age policy and is rejected for that policy shape.

Set `AGE_EVIDENCE_HMAC_SECRET` in the Decision Service secret manager to the dedicated age-evidence signing key (minimum 32 bytes). Do not reuse the Yoti API key or the general internal bearer token. The signed envelope must be delivered only over the authenticated internal service path. The durable Yoti session mapping, revocation lookup, provider onboarding and live staging acceptance remain separate release gates; this code does not claim those have been completed.


## Durable CaTaCaCi decision receipts

Every eligibility evaluation must persist its final CAL verdict before the response is released. Configure `DECISION_AUDIT_DATABASE_URL` with a dedicated least-privileged PostgreSQL login and apply:

```bash
psql "$DECISION_AUDIT_DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/0001_catacaci_decision_receipts.sql
```

The append-only `catacaci_decision_receipts` table records the request/candidate, required positive Catalog version, final SHOW/BLOCK/REVIEW, EEPL and CAL policy IDs/versions, contract versions, a digest over candidate ID, Catalog version, candidate attributes and completeness, typed evaluated signal states/reason codes/source versions, reason references and a canonical receipt SHA-256. The internal Decision Service API rejects requests without a real positive integer Catalog version. It deliberately excludes user IDs, raw measurements, images and free-text explanations. Replays are idempotent only when the canonical receipt hash matches; changed evidence under the same request/candidate is rejected. Readiness remains 503 until the PostgreSQL table is reachable. SQLite is not an accepted production receipt store.


## Durable CAM, privacy-budgeted CIL and VSL approval

Create a dedicated login in the database administration console first; set its password directly in the secret manager and never commit it:

```sql
CREATE ROLE cirvanna_decision_audit LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
```

Apply migrations in order using an administrative migration connection. The migrations create the private `decision_private` schema, revoke browser/public access, and grant the runtime login only the SELECT/INSERT/UPDATE privileges needed by the receipt, privacy-budget and VSL state machines:

```bash
psql "$DECISION_AUDIT_MIGRATION_URL" -v ON_ERROR_STOP=1 -f migrations/0001_catacaci_decision_receipts.sql
psql "$DECISION_AUDIT_MIGRATION_URL" -v ON_ERROR_STOP=1 -f migrations/0002_catacaci_governance_store.sql
```

Then configure `DECISION_AUDIT_DATABASE_URL` with the dedicated `cirvanna_decision_audit` login, SSL required. Do not use the Supabase `anon`, `authenticated`, or broad `service_role` keys as this database login. The role has no DELETE privilege; append-only triggers protect receipts, CAM audits, CIL releases and VSL events.

- **CAM:** `POST /v1/governance/cam/audits` appends version-bound observed-versus-simulated verdict comparisons. The record explicitly labels the scenario as non-causal. The database rejects mutation/deletion.
- **CIL:** `POST /v1/governance/cil/contributions` accepts only HMAC-pseudonymous contributor tokens and server-allowlisted low-cardinality cohort keys. `POST /v1/governance/cil/aggregates` releases one monthly aggregate per cohort using independent Laplace noise on the contributor-count/success-count vector. The mechanism assumes one binary contribution per contributor per cohort-month; its L1 sensitivity is 2.0. The minimum release threshold is 30, output is suppressed when the noisy count is below that threshold, and a persistent cohort-month epsilon ledger prevents repeated releases from exceeding the configured budget. Cohort-month transactions are serialized, and individual pseudonymous contribution rows are deleted atomically after the one aggregate is committed; later contributions for a released window are rejected. Unreleased rows expire after 90 days and are purged by `.github/workflows/catacaci-cil-retention.yml` daily. Configure repository Actions secrets `CATACACI_CIL_RETENTION_URL` (the HTTPS `/v1/governance/cil/retention/purge` endpoint) and `CATACACI_CIL_RETENTION_TOKEN` before enabling the schedule. The endpoint has a separate retention credential; a missing secret fails the job rather than silently skipping retention. This is a technical DP mechanism, not an independent privacy certification; its composition, cohort taxonomy, retention and implementation require privacy review before production use.
- **VSL:** `POST /v1/governance/vsl/proposals` records a versioned proposal; `POST /v1/governance/vsl/proposals/{id}/approve` or `/reject` requires a separate approver credential and actor identity. The proposer cannot approve their own change. Safety and legal eligibility remain fixed as the first two priority dimensions. Events are append-only; approved changes update the current version only after the compare-and-swap check succeeds.

Separate secrets and operator identities are mandatory: `CATACACI_CAM_SERVICE_TOKEN`, `CATACACI_CIL_SERVICE_TOKEN`, `CATACACI_CIL_AGGREGATE_TOKEN`, `CATACACI_CIL_RETENTION_TOKEN`, `CATACACI_VSL_PROPOSER_TOKEN`, `CATACACI_VSL_APPROVER_TOKEN`, `CATACACI_VSL_PROPOSER_ID`, and `CATACACI_VSL_APPROVER_ID`. The two VSL actor IDs must be different. Configure `CATACACI_CIL_ALLOWED_COHORT_KEYS` as a comma-separated exact allowlist; never accept browser-supplied cohort keys as policy. Set `CATACACI_CIL_RELEASE_EPSILON` and `CATACACI_CIL_EPSILON_BUDGET` only after privacy-owner approval.

The Decision Service remains not-ready until both the decision receipt and governance migrations are applied and the database is reachable. A successful schema migration does not replace operational backup/restore evidence, least-privilege grants, independent privacy review or human approval-owner assignment.
