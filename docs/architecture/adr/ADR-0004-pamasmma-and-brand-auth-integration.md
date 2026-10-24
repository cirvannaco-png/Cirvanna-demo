# ADR-0004: PAMASMMA cognitive services and brand-partner security

- Status: Proposed implementation boundary; not production enabled
- Date: 2026-10-24

## Context
Two supplied prototypes propose (1) ten PAMASMMA cognitive endpoints and (2) brand-partner JWT authentication plus brand/product/analytics tables. The cognitive prototype returns fixed placeholder decisions and unverified scores. The authentication prototype uses a placeholder JWT secret, mock login identity, does not persist registration, and restores permissions from a constant during refresh.

Cirvanna already defines CaTaCaCi as canonical decision authority and CAL as the deterministic arbitration kernel. Existing architecture records also require avoiding duplicate decision logic and reconciling new catalog persistence with canonical catalog ownership.

## Decision
1. Add a PAMASMMA-derived cognitive service boundary with typed contracts and a fail-closed handler registry. No domain executes until a real handler is registered. No fabricated scores or mock business decisions are returned.
2. Keep CaTaCaCi/CAL authoritative for user-facing suitability, consent and policy decisions. Cognitive services may provide specialized evidence, drafts, alerts and recommendations; they do not bypass CAL or override hard user constraints.
3. Add brand-token security primitives only. Do not expose registration, login or refresh routes until the authoritative brand repository, password verification, account approval/status checks, refresh-token rotation/revocation and permission loading are implemented.
4. Do not create brand product tables until the existing catalog/product model is reconciled. Tenant isolation must be enforced at every data-access boundary and tested across brands.
5. Ship these changes on an isolated feature branch and validate through CI/review before merging to main.

## Required release gates
- Unit/contract tests for every cognitive handler and token validation.
- Negative tests for unconfigured cognitive systems, invalid/expired/wrong-type tokens, missing permissions and suspended brands.
- Cross-tenant access tests for product, upload and analytics paths.
- Secret scanning and configuration validation.
- End-to-end tests for account lifecycle and token rotation before enabling brand auth routes.
- Observability, audit provenance, bounded execution, consent and autonomy/approval policies before enabling cognitive actions.

## Consequences
This integrates the architecture without representing prototype behavior as live functionality. Production capability remains explicitly unavailable until the gates above pass.
