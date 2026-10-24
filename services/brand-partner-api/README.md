# Brand partner API security boundary

This service boundary adapts the uploaded brand authentication proposal. It is not yet a complete production authentication service because the repository's canonical database/repository adapter and account lifecycle routes must be wired first.

## Required invariants
- Brand identity comes only from a cryptographically verified access token and authoritative account state, never from client-supplied `brand_id`.
- JWT signing secrets are loaded from a secret manager/environment and validated at startup. Placeholder/default secrets are forbidden.
- Login verifies a stored password hash and rejects pending, suspended or deleted accounts.
- Refresh tokens are distinct from access tokens, rotated on use, stored/revocable server-side, and re-check account status and permissions.
- Every catalog, product, upload and analytics query is scoped to the verified brand. PostgreSQL row-level security is recommended as defence in depth.
- Permissions are loaded from authoritative storage; refresh must never restore a hard-coded permission list.
- Registration persists a pending application and stores only a password hash. Approval requires an authorized actor and audit record.
- Rate limiting, email verification, password policy, security event logging, token revocation, migrations and tenant-isolation tests are release gates.

## Data model direction
The proposed `brands`, `brand_products` and `brand_analytics` tables are candidate schema only. Reconcile them with Cirvanna's existing catalog/product models before adding migrations; do not create duplicate product ownership tables.

## Status
Security design and integration boundary only. No mock login, fake brand identity, hard-coded JWT secret, or simulated account approval is permitted. Keep brand endpoints unavailable until the persistence adapter and lifecycle checks are implemented and tested.
