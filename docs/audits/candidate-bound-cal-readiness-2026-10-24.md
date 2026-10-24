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


## Expanded branch comparison (2026-10-24)

Branch comparisons were made against `main` and, for non-ancestor candidates, against the current integration line. These are ancestry/path-difference results, not proof that a branch's code is production-ready.

### Fully ancestral / no unique commit diff against main

The following refs each had `ahead_by=0` and no changed file paths relative to `main`; their commits are already ancestors of `main`, so their current tips add no unique source changes:
- `architecture/catacaci-decision-contract-audit`
- `architecture/cirvanna-monorepo-foundation`
- `audit/cfrp-v6-integration-review`
- `audit/full-code-snippet-inventory-2026-10-22`
- `audit/source-completeness-governance-2026-10-17`
- `chore/codespaces-workspace-bootstrap`
- `docs/codespaces-and-vertical-slice-2026-10-22`
- `docs/current-implementation-status-2026-10-22`
- `docs/implementation-status-2026-10-15`
- `docs/implementation-status-v2`
- `docs/update-current-status`
- `docs/update-marketplace-status-2026-10-18`
- `docs/virtual-try-on-model-readiness-2026-10-21`
- `engineering/cirvanna-end-to-end-slice-2026-10-21`
- `engineering/dermalsight-onnx-service`
- `engineering/vertical-slice-plan-2026-10-21`
- `feature/fci-confidence-contract`
- `feature/eepl-context-policy-core`
- `feature/fci-cal-pipeline-integration`
- `feature/npl-hard-veto-core`
- `feature/usi-explicit-alignment-core`
- `feature/virtual-try-on-foundation-2026-10-21`
- `feature/marketplace-vertical-slice-2026-10-18`
- `fix/cfrp-v6-runtime-safety`
- `fix/cultural-policy-unknown-fail-closed`
- `fix/malformed-policy-result-fail-closed`
- `fix/restore-ignored-source-candidates`
- `fix/virtual-twin-upload-limits`
- `integration/catacaci-governance-extensions`
- `integration/fci-source-snippet-promotion-2026-10-22`
- `integration/source-lineage-governor-2026-10-22`
- `integration/source-lineage-integrity-2026-10-22`
- `integration/source-reconstruction`
- `integration/virtual-twin-api-foundation`
- `maintenance/classify-staged-cdic-manifest`
- `maintenance/classify-staged-cdic-manifest-v2`
- `maintenance/rename-cdic-source-fragment`
- `migration/arrange-cirvanna-source-candidates`
- `migration/preserve-all-source-material`
- `migration/source-lineage-governor-2026-10-17`
- `repair/source-candidate-syntax`
- `security/detect-unquoted-password-defaults`
- `security/expand-secret-scan-coverage`
- `security/source-intake-credential-audit`
- `test/secret-scan-regressions`
- `test/virtual-twin-api-contracts`
- `feature/catacaci-governance-contracts`
- `feature/catalog-service-foundation`
- `feature/cultural-identity-explicit-policy`
- `feature/eepl-npl-cal-integration`
- `feature/virtual-try-on-foundation-2026-10-21`
- `integration/catacaci-governance-extensions`

The repeated branch names in the list reflect that the branch census was gathered in multiple comparison batches; the conclusion is unchanged: no unique commit diff relative to main. These refs are candidates for retirement only after checking open PRs, required audit retention, and branch protection/policy. No branch deletion was performed.

### Non-ancestral branches that need selective review

- `feature/cal-gateway-integration-v2`: 23 commits ahead of main and 8 changed paths, but its tree is fully behind the current integration line; no unique diff remains relative to PR #62. Treat as superseded.
- `feature/cirvanna-feature-spine`: 101 commits ahead / 4 behind main, with 60 changed paths. Compared to PR #62 it remains divergent (101 commits on that branch, 122 on the integration branch, 60 changed paths). It contains distinct FCI confidence, NPL/cultural evidence, Wardrobe, Xari and CI/documentation work. Do **not** merge wholesale. Extract and review each still-needed capability against the current tree and active PRs.
- `feature/private-vton-gpu-worker`: 9 commits ahead / 3 behind main, 8 changed paths; compared to PR #62 it has 9 unique commits and 8 changed paths, including a private try-on model-worker Dockerfile/API/tests/workflow. Keep isolated pending model-license, consent, security, image validation and real GPU/runtime tests; no evidence currently justifies promotion.
- `fix/vision-pose-model-integrity`: 2 commits ahead of main with 2 changed paths, and 2 unique paths relative to PR #62. Preserve for selective review of model asset integrity checks; do not cherry-pick blindly without reviewing the exact patch and CI.
- `docs/refresh-feature-spine-audit`: 1 commit ahead / 2 behind main with a single architecture readiness document; documentation-only candidate for reconciliation after its claims are checked against current evidence.
- `feature/twin-clickit-live-inference` / PR #60: 61 commits ahead / 1 behind main with 27 paths, but was closed as superseded. The PR description records no paths unique to its tree versus PR #62; overlapping files were intentionally replaced in PR #62.
- `feature/end-to-end-cal-purchase-governance` / PR #62 is the active integration line and remains draft.

### Branch retirement policy

No destructive branch deletion was performed. A branch that is behind main with zero unique changes is technically redundant at the source level, but may still be referenced by an open PR, used as audit evidence, or retained for provenance. Before deletion, verify the open-PR list, branch protection, deployment/workflow references and required retention. Keep unique model-worker and vision-integrity work quarantined until individually reviewed.
