# USI and User Context Service

**Status: persistent implementation candidate; deployment and user-ingress integration are not verified.**

This private service stores user-scoped USI style preferences and explicitly confirmed EEPL context. It does not infer cultural identity, style preferences or personal context from images, skin tone, names, location proxies or demographic attributes.

## Contracts used by the evidence provider

- `GET /v1/profiles/{user_id}` returns `user_id`, `usi_profile` and `eepl_policy`.
- `GET /v1/context/{user_id}` returns the same `user_id` and a nested context object.
- `PUT /v1/profiles/{user_id}` upserts an explicitly confirmed profile, including user-bound preference items and policy version.
- `PUT /v1/context/{user_id}` upserts explicitly confirmed age/location/occasion/climate context.
- All routes require the internal bearer token; callers must derive the subject from a verified identity and may only write for that subject.
- Every profile/context mutation appends a durable change-event row.

## Configuration

- `USI_DATABASE_URL`: production must be `postgresql+psycopg://...`.
- `USI_SERVICE_TOKEN`: at least 32 bytes, private to trusted internal callers.
- `USI_AUTO_CREATE_SCHEMA`: local/test only. Production must run `migrations/0001_initial.sql` through controlled migration.
- `USI_ALLOW_SQLITE_TESTS=1`: tests only; never set in production.

The evidence provider can use this service for both `USI_PROFILE_API_URL` and `USER_CONTEXT_API_URL`, with separate service tokens configured as needed. The endpoint paths match its private provider contract.

## Validation

Run `python -m pip install -r requirements.txt pytest` and `python -m pytest -q`. SQLite tests do not prove PostgreSQL locking, restore, production identity ingress, retention/deletion, or operational key rotation. These remain promotion gates.
