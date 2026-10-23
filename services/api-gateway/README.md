# API gateway / decision composition

**Status:** the first HTTP decision vertical slice is implemented on the engineering branch. End-to-end CI evidence is still pending; this gateway is not production-certified.

## Responsibilities

- Authenticate requests to the decision API with a configured bearer token.
- Fetch canonical products from the catalog service; never fall back to invented products.
- Compose the existing EEPL, NPL, USI, FCI contract and CaTaCaCi/CAL kernels.
- Apply only explicit user-declared cultural requirements and separately declared hard constraints.
- Append minimal decision-audit events before returning decisions.
- Allow display only when CAL explicitly returns `SHOW`.

## Routes

- `GET /health` — liveness only.
- `GET /ready` — checks gateway/catalog configuration, catalog readiness, and audit-store accessibility.
- `GET /capabilities` — reports implemented and unavailable capabilities.
- `POST /v1/decisions` — evaluates 1–25 active catalog product IDs against the supplied profile inputs.

Decision requests require `Authorization: Bearer $CIRVANNA_API_TOKEN`. The catalog service uses a separate `CATALOG_API_TOKEN`; the gateway forwards it only to the catalog API.

## Local setup

Use separate terminals/processes. Supply credentials through your shell's secret mechanism; do not commit them.

1. From `services/catalog-service`, install `requirements.txt`, configure `CATALOG_API_TOKEN`, and start the service, for example on port 8081. Its local SQLite default is for development only.
2. From `services/api-gateway`, install this directory's `requirements.txt`, then configure:
   - `CIRVANNA_API_TOKEN` — inbound gateway bearer token.
   - `CATALOG_SERVICE_URL` — base URL of the catalog service, e.g. local port 8081.
   - `CATALOG_API_TOKEN` — outbound service token matching the catalog process.
   - `CIRVANNA_AUDIT_DB` — persistent local SQLite file path for audit events.
3. Start the gateway from `services/api-gateway` with `uvicorn app.main:app --host 127.0.0.1 --port 8080`.
4. Check `/health`, `/ready`, and `/capabilities` before sending a request.

## Container build

Build from the **repository root** so the image includes the shared domain packages:

```bash
docker build -f services/api-gateway/Dockerfile -t cirvanna-decision-gateway .
```

The image runs as a non-root user, uses the platform `PORT` when supplied (otherwise 8080), and stores the local audit SQLite file at `/data/audit.sqlite3`. Mount a persistent volume at `/data` for local/staging persistence. This volume arrangement is not a replacement for a managed production audit store, backup/recovery, or retention controls.

Useful optional policy settings:

| Variable | Purpose |
|---|---|
| `CIRVANNA_POLICY_VERSION` | CAL policy version recorded with decisions |
| `CIRVANNA_EEPL_POLICY_ID`, `CIRVANNA_EEPL_POLICY_VERSION` | EEPL policy identity/version |
| `CIRVANNA_REQUIRED_CONTEXT_FIELDS` | Comma-separated EEPL context fields; default is `location,occasion,climate` |
| `CIRVANNA_MINIMUM_AGE`, `CIRVANNA_MAXIMUM_AGE` | Optional configured age bounds |
| `CIRVANNA_ALLOWED_LOCATIONS`, `CIRVANNA_ALLOWED_OCCASIONS`, `CIRVANNA_ALLOWED_CLIMATES` | Optional comma-separated allowlists |
| `CIRVANNA_REQUIRED_PRODUCT_ATTRIBUTES` | Product attribute keys needed to consider catalog metadata complete; default is `style,material,color` |

The initial context policy requires location, occasion, and climate inputs but does not impose geographic/occasion/climate allowlists unless configured. Missing required context produces `REVIEW`, not a guessed value.

## Request contract

`POST /v1/decisions` accepts a JSON body with:

- `user_id`: caller-supplied identifier. The current shared-token gateway does **not** bind it to an identity-provider session; keep this API internal/staging-only until that integration exists.
- `product_ids`: unique UUIDs from the canonical catalog.
- `context`: optional `age_years`, `location`, `occasion`, and `climate`.
- `style_preferences`: explicit style attributes and optional weights.
- `negative_preferences`: explicit item or attribute exclusions. These are hard vetoes.
- `cultural_requirements`: explicit declaration-linked required/forbidden attributes; no cultural identity is inferred.
- `hard_constraints`: additional required/forbidden attributes supplied explicitly by the user.

A product's attributes are taken from the catalog, not the request. For the initial apparel-focused slice, metadata is considered complete only when the configured required keys exist as non-empty strings.

## Decision safety

At this stage, the safety policy provider and trained/calibrated FCI provider are **not configured**. The gateway emits `UNKNOWN` safety evidence and an uncalibrated fit estimate, so otherwise eligible candidates normally return `REVIEW`. An NPL, legal, context, cultural, or explicit hard-constraint veto can return `BLOCK`. `SHOW` is possible only when all required gates produce valid results; tests can inject fixture-only provider results to validate that path. No fixture or client input is accepted as a live model result.

The API does not persist user profiles. The audit store persists only the request ID, product ID, verdict, reason codes, product catalog version, policy/contract versions, and timestamp; it omits user IDs, measurements, and images. The local SQLite audit file is suitable only for development/testing. Production requires a managed durable audit backend, migrations, retention/deletion controls, and operational monitoring.

## Tests

From the repository root:

```bash
python -m pip install -r services/api-gateway/requirements.txt
cd services/api-gateway
python -m pytest tests -q
cd ../..
python scripts/validate_architecture.py
python -m unittest discover -s tests/architecture -v
python scripts/scan_source_secrets.py
```

The `.github/workflows/decision-gateway.yml` workflow runs these checks plus a Docker image build on relevant pushes and pull requests. A passing workflow validates the tested API contracts only; it does not certify a deployed environment, fit accuracy, safety policy quality, identity authentication, or production readiness.

## Remaining release blockers

- Integrate and validate a real product-safety provider.
- Integrate a trained FCI estimator, including appropriate user fit evidence, calibration, uncertainty, provenance, and model-version tracking.
- Bind user identity to an authenticated principal; replace shared bearer auth with scoped authorization before external exposure.
- Replace local SQLite audit with managed durable storage, migrations, access controls, retention, and tested recovery.
- Add persistence for user profiles only after defining consent, export, correction, and deletion requirements.
- Run real deployment smoke tests, security/privacy review, load/failure tests, and end-to-end user journey checks.

Virtual Try-On remains a separate next phase: rendering/simulation must consume a supported Virtual Twin/model adapter and catalog assets; it must not be simulated by this decision endpoint.


## Durable NPL provider integration

When configured, the gateway loads each candidate's NPL snapshot from the trusted `NPL_SERVICE_URL` using `NPL_SERVICE_TOKEN` and verifies `NPL_EVIDENCE_HMAC_SECRET` over the request/user/candidate/attribute/preferences envelope before applying the veto. A provider that is partially configured, unavailable or returns invalid signature/context causes a fail-closed service error; it never falls back silently to an empty persistent preference set. If no NPL provider is configured at all, only request-local, explicitly supplied hard exclusions are evaluated and the gateway capability reports `persistent_npl_service_integrated=false`.

- `NPL_SERVICE_URL`: trusted internal HTTPS base URL.
- `NPL_SERVICE_TOKEN`: internal service token shared with NPL.
- `NPL_EVIDENCE_HMAC_SECRET`: HMAC key shared only with trusted NPL and consumer services.

This integration does not create persistent preferences from request-local exclusions. User preference creation/correction must use the NPL API and the ingress must bind `user_id` to the authenticated user.
