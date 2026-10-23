# Cultural Identity Declaration Service

**Status:** persistent explicit-declaration API and candidate-bound signed evidence implemented; production deployment and gateway/decision service connection remain gated.

The service stores only structured, user-declared requirements—not inferred cultural profiles or image-derived guesses. Requirements support hard required attributes, hard forbidden attributes, and soft preferences. A declaration requires explicit confirmation and a confirmation-policy version. Retraction is a separate, confirmed and audited correction; retracted declarations are excluded from subsequent evaluations.

## Safety rules

- Never infer culture, religion, ethnicity, modesty or cultural preferences from skin tone, face, name, location, demographic proxies or uploaded images.
- User IDs and declaration IDs are ownership-scoped in every read and mutation.
- Missing catalog attributes for a hard required attribute produce REVIEW, not PASS.
- Hard forbidden-attribute conflicts BLOCK. Soft preferences never create a hard block.
- The evaluation endpoint signs the request ID, user ID, candidate ID, normalized candidate attributes, metadata-completeness flag and active requirement envelope with HMAC-SHA256.
- Keep this service private. A trusted ingress must bind user ID to the authenticated user and keep the HMAC secret server-side.

## Configuration

- `CULTURAL_IDENTITY_DATABASE_URL`: production PostgreSQL URL using `postgresql+psycopg://`.
- `CULTURAL_IDENTITY_SERVICE_TOKEN`: internal bearer token, at least 32 bytes.
- `CULTURAL_IDENTITY_HMAC_SECRET`: trusted decision consumers' shared HMAC key, at least 32 bytes.
- `CULTURAL_IDENTITY_ALLOW_SQLITE_TESTS=1`: test-only switch. Never set in production.

Apply `migrations/0001_initial.sql` using the controlled migration process. The API does not create production schema automatically. `/ready` verifies configuration, database connectivity and all required tables.

## API

- `POST /v1/declarations` creates confirmed explicit declarations.
- `GET /v1/declarations?user_id=...` lists one user's declarations and current status.
- `POST /v1/declarations/{declaration_id}/retract` confirms and audits a correction.
- `POST /v1/evaluate` evaluates the active declarations for one candidate and returns a signed evidence envelope.

## Verification

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```

Production promotion requires a deployed PostgreSQL migration/restore test, real ingress identity binding, shared-key rotation procedure, audit retention and an end-to-end signature-verification test at each consumer.
