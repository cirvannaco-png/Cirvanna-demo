# Brand partner API security boundary

This service boundary adapts the supplied brand authentication proposal. The repository currently documents the API gateway and catalog service as scaffolds; there is no verified canonical brand-account persistence adapter wired to these modules yet.

## Required invariants
- Brand identity comes only from a cryptographically verified access token and authoritative account state, never from client-supplied `brand_id`.
- JWT signing secrets are loaded from a secret manager/environment and validated at startup. Placeholder/default secrets are forbidden.
- Login verifies a stored password hash and rejects pending, suspended or deleted accounts.
- Refresh tokens are distinct from access tokens, rotated on use, stored/revocable server-side, and re-check account status and permissions.
- Every catalog, product, upload and analytics query is scoped to the verified brand. PostgreSQL row-level security is recommended as defence in depth.
- Permissions are loaded from authoritative storage; refresh must never restore a hard-coded permission list.
- Registration persists a pending application and stores only a password hash. Approval requires an authorized actor and audit record.
- Rate limiting, email verification, password policy, security event logging, token revocation, migrations and tenant-isolation tests are release gates.

## Persistence implementation
- `repository_contract.py` defines the async account and refresh-token repository interfaces.
- `postgres_repository.py` implements PostgreSQL account lookup/creation, status changes, permission replacement, audit events, and atomic one-time refresh-session rotation/revocation using an asyncpg-compatible pool.
- `account_service.py` provides normalized-email registration, scrypt password hashing, active-account authentication, and permission-gated status transitions.
- `refresh_tokens.py` issues persisted refresh sessions and rotates them once, returning access tokens built from freshly loaded permissions.
- `schema.sql` is the candidate schema for account, permission, refresh-session, and audit tables.

The adapter and schema are not connected to a configured database or deployed route. Apply the schema through an approved migration process, wire a validated DATABASE_URL through secret storage, and run PostgreSQL integration and tenant-isolation tests before enabling endpoints. The adapter must be tested against the target PostgreSQL version; the in-memory repository used in tests is test-only.

## Data model direction
The proposed `brands`, `brand_products` and `brand_analytics` tables are candidate schema only. Reconcile them with Cirvanna's existing catalog/product models before adding migrations; do not create duplicate product ownership tables.

## Status
Security design and repository contract only. No mock login, fake brand identity, hard-coded JWT secret, or simulated account approval is permitted. Keep brand endpoints unavailable until the persistence adapter and lifecycle checks are implemented and tested.
