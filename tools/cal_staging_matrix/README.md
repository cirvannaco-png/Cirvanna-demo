# CAL staging adversarial matrix runner

This is the single release-candidate runner for the CAL shopper-surface acceptance matrix. It is deliberately an external black-box test: it sends requests to the deployed staging services and records only response status, latency, cache-control and assertion failures. It does not call local test clients or silently replace real services with mocks.

## Safety and execution contract

- The manifest must declare `"environment": "staging"`; production is rejected.
- A dedicated staging fixture-control service is required. It must create isolated synthetic merchant, Catalog, offer, consent, identity and payment fixtures and return opaque fixture/request IDs.
- Fixture-control credentials and every service token are read from environment variables. Secrets are never printed into the report.
- Each scenario must exercise all ten shopper surfaces: Marketplace, PNELLY, Wardrobe, Look It, Click It, saved products, comparison, cart, checkout and PNELLY daily looks.
- Consent/session and payment-race scenarios execute selected shopper requests concurrently with the authoritative revocation, then re-run every surface after revocation. This catches late responses and stale browser/API/CDN state.
- Every shopper surface in every scenario, every raced surface and every post-revocation surface must have explicit semantic JSON assertions; HTTP status alone is insufficient. The runner has no permissive fallback such as treating 200/401/403/503 as interchangeable evidence.
- Fixture teardown must be confirmed. A failed teardown fails the suite.
- No customer photos, real payment instruments, real customer identities or production merchant accounts belong in the fixture set.

## Run

```bash
python tools/cal_staging_matrix/run.py --config /secure/path/cirvanna-staging-matrix.json
```

Exit codes: `0` all assertions passed; `1` one or more adversarial assertions failed; `2` missing/invalid configuration or a transport/setup failure. The report defaults to `cal-staging-matrix-report.json`; set `report_path` in the manifest to a restricted evidence location.

## Manifest contract

Top-level fields:

- `environment`: exactly `staging`.
- `fixture_control.url`: HTTPS base URL of the dedicated staging-only fixture controller.
- `fixture_control.token_env`: environment variable holding a random token of at least 32 bytes.
- `surfaces`: exactly the ten shopper surfaces below. Each entry has `url`, `method`, optional `headers`, optional `token_env` (omit for intentionally public probes such as the disabled public Click It route), `body` and default `assertions`.
- `scenarios`: all eight required scenario IDs below. Each scenario provides a synthetic `fixture`, an `exercise_surfaces` list containing all ten surfaces, per-surface semantic `assertions`, and optional `revoke`, `race`, `race_assertions`, `recheck_after_revoke` and `post_revoke_assertions`. Revocation scenarios must provide explicit semantic JSON assertions for all ten post-revocation surfaces. Race scenarios must provide explicit semantic JSON assertions for every raced surface; status-only assertions are rejected. `race.surfaces` names requests to execute concurrently with `race.revoke`. Every revocation request must use HTTPS and a dedicated `token_env`; public shopper probes may omit their token.

The fixture controller must implement:

- `POST /v1/scenarios/{scenario_id}/activate` with the scenario's fixture object; return `fixture_id` and `request_id`.
- `POST /v1/scenarios/{scenario_id}/deactivate` with the opaque fixture ID; return 200/204 only after all synthetic state and provider test artifacts are cleaned up.

The controller is a staging orchestration dependency, not a production application API. It must drive the real identity/consent, Catalog, Commerce, merchant sandbox, payment sandbox and cache/CDN test dependencies. It must not fake provider results or mutate production data.

A surface request may interpolate `{{scenario_id}}`, `{{fixture_id}}` and `{{request_id}}` in URL, headers or JSON body. Assertions support:

- `status`: one HTTP status or a list of accepted statuses.
- `require_no_store`: require `Cache-Control: no-store`.
- `require_json`: require a JSON response.
- `json_equals`: exact dotted JSON path values.
- `json_present`: JSON paths that must exist.
- `json_absent`: JSON paths that must be absent. Wildcard arrays are supported, e.g. `$.products[*].image_url`.
- `json_one_of`: a list of `{ "path": "$.decision.verdict", "values": ["BLOCK", "REVIEW"] }` assertions.

Every denied/reviewed product-display scenario should assert that product name, merchant, variant, price, image URL and offer identifiers are absent from shopper responses. Checkout denial should assert no order/payment/stock reservation was created. A successful display scenario must assert a candidate-bound CAL SHOW receipt and the exact expected Catalog version. Purchase scenarios must separately assert fresh purchase authorization; display SHOW is never reusable as checkout authorization.

## Required scenario intent

| ID | State injected by fixture controller | Required result |
|---|---|---|
| `mapped_approved` | Active mapped product, approved merchant, fresh offer, active consent | Only explicitly authorized surfaces may expose product details after candidate-bound CAL SHOW and CIL eligibility. |
| `unmapped_candidate` | Candidate/variant has no canonical mapping | No product or offer detail; no Commerce comparison or checkout. |
| `merchant_suspended` | Merchant or operating market suspended/revoked | Suppress details and purchase; saved references must not revive the offer. |
| `stale_offer` | Expired stock/price snapshot or changed offer hash | REVIEW/BLOCK; no stale display or purchase. |
| `merchant_disconnected` | Merchant disconnect, deletion and reauthorization variants | No stale token, listing or cache may revive the prior offer. |
| `consent_session_revoked` | Consent and user session revoked concurrently with PNELLY, Wardrobe and Look It requests | No late response, old browser state or prior-session data may appear after revocation. |
| `cache_after_revocation` | Warm API/browser/CDN cache, then revoke publication/display authority | Post-revocation probes must not return prior product details; CDN evidence must include cache status and purge verification outside this runner. |
| `payment_revoked_race` | Cart and checkout requests race a real purchase-authorization revocation | No new order/payment authorization; any ambiguous or already-submitted payment must reconcile/compensate idempotently. |

## Evidence limitations

This runner is only as trustworthy as its fixture controller and configured endpoints. A green run proves the configured requests and assertions passed at that moment; it does not prove unconfigured routes, every CDN POP, backups, external merchant records or independent privacy review. Store the manifest and report under restricted access, redact secrets and customer data, and attach provider request IDs / trace IDs in the restricted evidence store. Never put bearer tokens, source photographs, ID documents, raw DOB or payment credentials in the report.
