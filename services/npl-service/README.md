# NPL service

**Status:** SQLAlchemy persistence API and signed NPL evaluation contract implemented; production deployment and decision-service integration remain gated.

The service stores user-scoped preferences in PostgreSQL and separate rejection/correction event tables. Database uniqueness protects user-scoped rejection and correction event identifiers. Preference changes are transactional with row locking where supported. Duplicate rejection events are idempotent for the same preference and conflict when reused for another preference. Corrections are explicit and auditable; a retracted preference cannot accumulate new rejection evidence.

## Configuration

- NPL_DATABASE_URL: production must use postgresql+psycopg://.
- NPL_SERVICE_TOKEN: internal bearer token, at least 32 bytes.
- NPL_EVIDENCE_HMAC_SECRET: shared with the decision service to authenticate NPL evidence and keyed deletion-receipt digests, at least 32 bytes.

Apply migrations/0001_initial.sql and then migrations/0002_deletion_receipts.sql through the controlled migration process. The API does not create the production schema automatically. /ready becomes ready only when credentials, evidence signing, database connectivity and all required tables are present. SQLite is supported by tests only; it is not a production datastore configuration.

## API

- POST /v1/preferences creates a user-declared or learned-rejection preference.
- GET /v1/preferences?user_id=... lists a user's preferences.
- POST /v1/preferences/{id}/rejections idempotently records a unique rejection event.
- POST /v1/preferences/{id}/retract persists an explicit correction.
- GET /v1/users/{user_id}/export returns the user's complete negative-preference ledger, including rejection and correction event IDs.
- DELETE /v1/users/{user_id} transactionally deletes preferences and all associated rejection/correction events, retaining only a one-way subject digest and aggregate-count deletion receipt.
- POST /v1/evaluate evaluates the persisted ledger and returns a signed evidence envelope for the decision service.
- GET /v1/users/{user_id}/export exports preferences plus rejection and correction event history for the verified user.
- DELETE /v1/users/{user_id} removes all preference, rejection and correction rows in one transaction and keeps only a keyed subject digest plus aggregate counts in a deletion receipt.

This is an internal service; keep it off public ingress. Ingress identity must be validated upstream and the user scope passed by a trusted internal caller. The decision service verifies the HMAC-bound request ID, user ID, candidate ID, candidate attributes and full preference envelope before running CAL.

## Verification

From services/npl-service:

    python -m pip install -r requirements.txt
    python -m pytest -q

Production gates remain a real PostgreSQL integration/restore test, concurrent multi-worker stress test, key rotation procedure, audit delivery and end-to-end decision-service integration against the deployed NPL provider.
