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

## Trusted fit evidence

The service does not contain or claim to train/run an FCI predictor. A separately trusted fit provider must send a FitEvidenceIn object and compute a lowercase hex HMAC-SHA256 signature over its normalized JSON:
- serialize the FitEvidenceIn model with all fields (including null/default values),
- use UTF-8 JSON with sorted keys, compact separators, and ensure_ascii=false,
- sign the bytes with FCI_EVIDENCE_HMAC_SECRET.

The service independently canonicalizes and verifies the signature before evaluating CAL. An uncalibrated but validly signed estimate becomes UNKNOWN in FCI and must result in REVIEW, not SHOW. The HMAC proves the payload came from a holder of the trusted key; it does not prove the provider's science or calibration quality. A production provider still needs empirical calibration, model governance and access controls.

## Configuration

- DECISION_SERVICE_TOKEN: long random internal bearer token; protect service network access as well.
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
- The Marketplace API Gateway's live `/v1/decisions` path consumes the latest context-scoped CIL feedback decision when `CIL_CAL_REVIEW_ENFORCEMENT_REQUIRED=true`; a final human CAL BLOCK becomes a candidate veto and a later SHOW never overrides the ordinary policy pipeline. Commerce must still independently verify the signed candidate-bound purchase authorization at cart and checkout. Do not enable the enforcement flag until the CIL service and separate CAL credential are deployed and the cross-service staging test passes.
- This adapter does not produce Click It reconstructions, Virtual Twin geometry or try-on imagery; those require validated model/rendering integrations.


## Trusted NPL evidence

The decision endpoint also requires `NPL_EVIDENCE_HMAC_SECRET`, shared only with the trusted NPL service. The signature binds the request ID, user ID, candidate ID, normalized candidate attributes and the complete user-scoped negative-preference envelope. Missing, foreign-user or modified NPL evidence fails before CAL evaluation. This verification proves provenance from a key holder; it does not replace end-to-end identity validation, service authorization or a deployed NPL integration.


## Trusted cultural declaration evidence

The decision endpoint requires `CULTURAL_IDENTITY_HMAC_SECRET` and verifies a candidate-bound Cultural Identity evidence envelope before evaluation. The signature binds request ID, user ID, candidate ID, normalized candidate attributes, metadata completeness and the active declaration requirement set. Modified or foreign-user declaration evidence fails before CAL runs. The service key must be shared only with the trusted Cultural Identity service/consumer chain; an internal API token alone does not prove that a cultural declaration is genuine.
