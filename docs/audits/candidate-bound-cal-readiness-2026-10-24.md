# Candidate-Bound CAL Integration Audit — 2026-10-24

## Audit identity

- Repository: `cirvannaco-png/Cirvanna-demo`
- Target branch: `main`
- Audited integration snapshot: `656cd64629aa60728f6e5e8dce4e4d43477d7731`
- Baseline main snapshot observed during this audit: `553777cfe7e19d4d05ee92445073cfe8945ab41a`
- Integration PR: [#62 — Enforce candidate-bound CAL authorization across marketplace and checkout](https://github.com/cirvannaco-png/Cirvanna-demo/pull/62)
- Status: **DRAFT / NOT MERGE-READY**

This report is an audit of the source snapshot above. It is not a claim that the source has passed CI, been deployed, or completed an end-to-end run.

## Architecture ownership

| Concern | Owning subsystem | Integration boundary |
|---|---|---|
| Marketplace discovery and display gating | Marketplace BFF + `app/governance.py` | Candidate-bound evidence envelope → canonical Decision service |
| Evidence assembly | `services/governance-evidence-provider` | Authenticated NPL, explicit Cultural Identity, Catalog, USI/context, policy evidence and fit provider |
| Eligibility arbitration | `services/decision-service` | Signed evidence; exact request and candidate correlation |
| Purchase-time authorization | `services/commerce-service` | Exact variant/offer ID **and** canonical Catalog product ID |
| Durable purchase audit | Commerce PostgreSQL audit table | Decision request/policy version, decision, both identities, order link and receipt |
| Vision and try-on | Virtual Twin, Vision Intelligence and Xari services | Retrieval/model output is not authorization; CAL remains mandatory |

## Changes in the audited snapshot

1. Commerce checkout revalidates the exact purchasable variant ID together with its canonical Catalog product ID. An approval for a different candidate or product must not authorize checkout.
2. CAL audit rows persist both identifiers. The schema migration creates an index on the Catalog product identity; successful checkout stores the authorization receipts in the same database transaction as the order and stock reservations.
3. Idempotent checkout retries revalidate prior order items before reusing/creating a Stripe session.
4. The internal BFF authorization contract requires a canonical Catalog product ID and checks that the governed response is bound to the same candidate and product.
5. The evidence provider's readiness path checks upstream `/ready` responses. A fit endpoint is not considered ready unless it explicitly attests to an available prediction model and a valid calibration report. The provider also verifies the user binding in context before passing an allowlisted context to fit/policy providers.
6. The PR keeps marketplace display fail-closed while required evidence or decision services are unavailable.

These are source-level changes, not production verification.

## Evidence observed

- Main baseline at the time of comparison: `553777cfe7e19d4d05ee92445073cfe8945ab41a`.
- PR #62 had 117 commits ahead of that baseline and no commits behind at the last comparison; the compare reported 31 changed file paths.
- PR #62 remained open and draft. It was not merged.
- PR #60 was closed as **superseded, not merged**. Its unique-path comparison found no tracked paths exclusive to its branch; shared Twin/Vision/Xari files were identical, while overlapping marketplace/BFF/Catalog/Commerce files were replaced by the guarded PR #62 versions. The branch history remains available.
- The latest visible Actions runs for the integration line were failures across the evidence provider, Marketplace BFF/contracts, Commerce, Catalog, USI/context, Twin/Vision/Xari, container builds and architecture validation. These runs referenced older integration commit `9fba6a9823225e1b76c8c997038f865ee6cf362c`, not the audited snapshot. The workflow-log endpoint returned `BlobNotFound` for inspected jobs, so root causes could not be confirmed from logs.
- No successful CI run on the audited snapshot was established during this audit.
- No deployed staging endpoints, service credentials, PostgreSQL staging migration result, Stripe test webhook run, or durable live audit receipt were available as evidence.

## Release blockers

### P0 — Trust and authorization
- The independent signed policy-evidence service and signing key are not present/configured. The evidence provider must not synthesize safety, legal-eligibility or user-hard-constraint passes.
- A trained, calibrated and empirically validated FCI fit provider is not present/configured. HMAC authenticity is not fit accuracy or calibration.
- User/profile/context providers and the evidence provider have not been proven together against live, authenticated PostgreSQL-backed services.
- Verify the candidate ID's domain semantics end-to-end: marketplace candidate/variant ID must map to the correct active Catalog product ID without allowing a client to substitute either identity.

### P0 — Purchase integrity
- Run real non-production browse/search → CAL SHOW → display → checkout-time revalidation → Stripe test webhook → replay/idempotency → durable order-linked receipt.
- Prove that denied, stale, missing, unsigned, tampered, mismatched, expired and unavailable evidence blocks order creation and stock reservation.
- Verify audit rows survive process restart and database restore; ensure failure receipts and successful receipts are both attributable to the exact candidate/product and request.

### P1 — CI and operations
- Diagnose and clear required CI failures using usable job logs; rerun all required checks on the exact candidate commit.
- Apply and verify migrations on isolated PostgreSQL; verify rollback behavior and schema readiness.
- Benchmark a real 300–500-product catalog, including a measured sub-100 ms vector-search target.
- Validate real Twin/Click It/try-on inference, model checksums/revisions, image rejection, latency/resources, consent, deletion and backup/restore.
- Add monitoring/alerts for CAL unavailable, stale/mismatched evidence, policy-provider failure, payment-webhook replay and audit persistence failure.

## Branch handling

- PR #62 is the current integration line; keep it draft until release gates pass.
- PR #60 is superseded and closed without merging to avoid reintroducing overlapping direct-browser flows.
- Do not delete remaining branches based only on names or age. Before retiring a branch, compare its full tree and commit ancestry to main and active PRs, then record whether its unique behavior is preserved.

## Final disposition

**Not ready for merge, deployment, or production traffic.** The audited source improves candidate identity binding and fail-closed readiness, but CI on the exact snapshot and all live-service/payment/ML evidence remain unverified. Do not promote the branch until those gates have concrete, reproducible artifacts.
