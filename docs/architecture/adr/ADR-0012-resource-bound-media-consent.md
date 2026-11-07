# ADR-0012: Resource-bound media consent bundles

- **Status:** Proposed
- **Date:** 2026-11-07
- **Decision owners:** Cirvanna architecture

## Context

Virtual Twin and Click It already call a consent-verification adapter, but the identity-learning service did not expose that endpoint. Its existing receipt model represented one scope per receipt and had no stable bundle identifier or resource binding. A client boolean or an unverified receipt ID is not adequate authority for processing body images or retaining a Twin representation.

## Decision

Extend the existing `identity_tal_consent_receipts` table with:

- `consent_id`: groups multiple scope-specific receipts from one consent action; legacy rows are backfilled to their own receipt ID.
- `resource_id`: optional exact resource binding, such as a Twin ID.

Add internal `POST /internal/v1/consents/verify`. The endpoint requires the identity service's existing machine bearer token and verifies the Commerce-verified subject supplied by the trusted gateway, consent bundle, all requested scopes, active grant state, and exact resource equality. If a grant is resource-bound, a verification request that omits the resource ID must fail. Revoking any scope continues to revoke all active receipts for that subject and scope, so a parallel receipt cannot keep the same purpose authorized.

The API Gateway accepts and forwards the new consent bundle/resource fields only after resolving the end-user through Commerce `/me`. The service continues to use the existing approved managed Postgres database; the migration is additive and does not provision infrastructure.

## Consequences

- Virtual Twin can use the existing adapter contract without trusting form booleans.
- Click It can require a Twin-bound consent bundle and prevent cross-subject or cross-Twin reuse.
- Consent revocation is checked at request time and blocks subsequent processing.
- Legacy consent receipts remain readable; old rows are assigned `consent_id = receipt_id` and have no resource binding.
- Each media purpose remains separately scoped; image processing, body measurements, Twin storage, try-on and Click It are not collapsed into one broad permission.

## Non-goals and release gates

This decision does not implement a persistent Twin registry, asset/object storage, asset authorization, deletion outbox reconciliation, renderer integration, or production migration execution. Those remain separate release gates. The SQL migration and SQLite tests do not prove PostgreSQL production behavior; apply the migration only after backup/restore verification and validate the full consent lifecycle in staging.
