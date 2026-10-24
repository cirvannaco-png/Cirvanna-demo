# ADR-0004: PAMASMMA cognitive services and brand-partner security

- Status: Implementation in progress; production not enabled
- Date: 2026-10-24

## Context
The supplied prototypes propose ten PAMASMMA cognitive endpoints and brand-partner authentication plus brand/product/analytics tables. The cognitive prototype returned fixed placeholder decisions and unverified scores. The authentication prototype used a placeholder JWT secret, mock login identity, no persistent registration, and hard-coded permissions on refresh.

Cirvanna's repository documents the API gateway and catalog service as scaffolds. CaTaCaCi's deterministic core is present at `packages/identity-intelligence/catacaci/core.py`; its documented role is canonical arbitration, not recommendation.

## Decisions
1. Add typed contracts and a fail-closed handler registry. No domain executes until a real handler is registered.
2. Implement four narrow deterministic handlers first: incident triage, support queue routing, explicit required-term preflight, and limited marketing-risk lexical preflight. They do not perform external side effects.
3. Keep CaTaCaCi/CAL authoritative for user-facing suitability, consent and policy decisions. Cognitive services cannot bypass CAL or override hard user constraints.
4. Add brand token primitives and a repository Protocol, but do not expose registration/login/refresh routes until the canonical persistence adapter, password verification, account approval/status checks, refresh-token rotation/revocation and live permission loading are implemented.
5. Do not create brand product tables until the existing catalog model is reconciled. Tenant isolation must be enforced at every data-access boundary and tested across brands.
6. Expand CI to test the new contracts on pull requests targeting the current integration branch.

## Release gates
- Unit/contract tests for every handler and token validation.
- Negative tests for unconfigured cognitive systems, invalid/expired/wrong-type tokens, missing permissions and suspended brands.
- Cross-tenant access tests for product, upload and analytics paths.
- Secret scanning and configuration validation.
- End-to-end tests for account lifecycle and token rotation before enabling brand auth routes.
- Observability, audit provenance, bounded execution, consent and autonomy/approval policies before enabling cognitive actions.

## Consequences
This integration adds executable, bounded logic without representing prototype behavior as production capability. Production capability remains unavailable until the required gates pass.
