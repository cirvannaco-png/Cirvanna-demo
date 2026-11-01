# Skincare routine service

**Status:** initial API and persistence contract. It is not yet wired to the user-facing app or a live skincare recommendation provider.

This service organizes user-approved skincare steps into separate **morning** and **evening** routines. Users can create, list, edit, version-check, delete, and share routines. It stores product and recommendation references, not skin-analysis images or diagnostic results.

## Service boundaries

- DermalSight remains a non-diagnostic cosmetic skin-attribute inference service. It does not prescribe products or generate routines.
- This service is a routine organizer and persistence layer; it does not generate skin recommendations.
- The calling recommendation/application layer must pass only recommendations that have already cleared applicable catalog, consent, safety, and CaTaCaCi/CAL display gates. A routine reference is not authorization to display or sell a product.
- Product metadata remains owned by the catalog. Each step may retain a canonical catalog UUID and/or an opaque recommendation ID, plus user-facing label and instruction text.
- The routine service does not ingest, store, or share user skin photos, skin scores, diagnosis claims, profile attributes, or private analysis payloads.

## API

Authenticated internal routes require `Authorization: Bearer $SKINCARE_ROUTINE_SERVICE_TOKEN`:

- `POST /v1/routines` — create a routine with `morning_steps` and/or `evening_steps`.
- `GET /v1/routines?owner_user_id=...` — list an owner's active routines.
- `GET /v1/routines/{routine_id}?owner_user_id=...` — retrieve one routine.
- `PUT /v1/routines/{routine_id}` — replace routine content using `expected_version`; stale writes return `409`.
- `DELETE /v1/routines/{routine_id}?owner_user_id=...&expected_version=...` — delete the routine and invalidate its shares.
- `POST /v1/routines/{routine_id}/share` — issue a read-only public link, valid for 1–90 days (30 by default). Only the token hash is stored; the plaintext token is returned once.
- `DELETE /v1/routines/{routine_id}/share?owner_user_id=...` — revoke the current share link.
- `GET /public/routines/{token}` — read a shared routine without authentication.

Creating a replacement share link revokes the prior link. Sharing is opt-in and anyone holding the link can view the routine until it expires or is revoked. Share responses omit owner IDs. Share responses are `no-store` and marked `noindex`; links are bearer capabilities, not identity proof.

## Identity, privacy, and safety

All authenticated routes are internal. The trusted ingress must authenticate the end user and bind `owner_user_id` to the verified principal; it must reject a client-supplied owner ID that does not match. The shared service token is service-to-service authentication, not user authentication. Do not expose this service directly to browsers or the public internet.

Routine text and product/recommendation references are user-controlled content. Users should share only content they intend to make visible to anyone with the link. Do not include inferred skin attributes or sensitive profile context in shared routine text. The service is not a medical advice engine and does not diagnose, prescribe, or make claims about product efficacy. Product selection and display remain subject to the upstream decision and safety pipeline.

## Persistence and operations

- `SKINCARE_ROUTINE_DATABASE_URL` must use `postgresql+psycopg://` in deployed environments.
- `SKINCARE_ROUTINE_SERVICE_TOKEN` must be a randomly generated secret of at least 32 bytes.
- `SKINCARE_ROUTINE_ALLOW_SQLITE_TESTS=1` is test-only.
- Apply `migrations/0001_initial.sql` using the deployment's controlled migration process; application startup does not create production tables.
- `GET /ready` checks service auth configuration, database connectivity, and the expected schema.

## Local tests

    python -m pip install -r requirements.txt
    python -m pytest -q

SQLite is permitted only when `SKINCARE_ROUTINE_ALLOW_SQLITE_TESTS=1`.

## Verified CI snapshot — 1 November 2026

On PR #69 head `6f8fdedf92815088df48da4a8d9d656255cf1c7e`, the [skincare routine service workflow](https://github.com/cirvannaco-png/Cirvanna-demo/actions/runs/41334245920) completed successfully:
- Dependency installation and `pip check` passed.
- Python compilation passed.
- **15 API tests passed**.
- The Docker image built successfully.

The [architecture validation workflow](https://github.com/cirvannaco-png/Cirvanna-demo/actions/runs/41334245950) also passed on the same PR head. The test run emitted one Starlette/httpx deprecation warning; it did not fail the workflow.

This evidence validates the isolated service and architecture checks only. It does not prove the application UI, end-user identity integration, a live recommendation provider, production PostgreSQL operation, or a production deployment.

## Remaining integration gates

1. Bind end-user identity at the authenticated API gateway before public app use.
2. Connect the approved skincare-recommendation source; it must supply product/recommendation IDs only after the relevant display and safety checks.
3. Integrate the routine UI (AM/PM editor, saved-routine list, explicit share action, expiry/revoke controls).
4. Run PostgreSQL migration, backup/restore, concurrent update, link-expiry, share-revocation, ingress-identity, security, and staging end-to-end tests.
5. Validate product instructions and user-facing claims through the relevant domain review before launch.

A passing service test suite validates the API and persistence contract, not live recommendations, user identity integration, or production readiness.
