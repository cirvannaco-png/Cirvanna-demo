# Cirvanna Readiness Audit — 2026-10-23

## Audit identity and reproducibility

This report is pinned to the repository state inspected on 2026-10-23. It does not claim that all services were deployed or that all tests passed.

- Repository: `cirvannaco-png/Cirvanna-demo`
- Baseline `main` commit: `553777cfe7e19d4d05ee92445073cfe8945ab41a`
- PR #60 head inspected: `c64188c736edc308ae66b68f3bd14122fc21e8c9`
- PR #62 initial audit head: `c731231ce2e80e0cda2df4865321d91139f3b609`
- PR #62 follow-up implementation head: `5a0b8468bc2e235ea11b4596cb1820c70a55d904`
- PR #62 latest follow-up head: `c9c17dab733c490ea5525c7d2e4b454bcb7408f1`
- Branch inventory: 58 refs returned by GitHub at audit time.
- Method: GitHub commit comparisons against `main`, pull-request changed-file inventories, source inspection of service contracts/readiness routes and current tests.
- CI log limitation: GitHub reports failed jobs, but the connected job-log endpoint returns `BlobNotFound`; therefore the exact failing commands could not be independently recovered.

## Executive decision

**Not production-ready. Do not merge PR #60 or PR #62 yet, do not enable a public governed checkout, and do not mark AI capabilities complete.**

The repository has meaningful service foundations and deterministic decision logic. It does not yet prove a live, complete identity-to-evidence-to-CAL-to-display-to-checkout-to-payment-audit journey. Code presence, mocked tests, a successful build and live deployment are distinct evidence levels.

## Purchase governance and checkout

The PR #62 branch contains:
- A per-candidate BFF gateway that calls the evidence provider and canonical decision endpoint, and exposes candidates only for a matching CAL `SHOW` / `may_display=true` result.
- A new `services/governance-evidence-provider` implementation candidate that composes catalog metadata, NPL evidence, explicit cultural declarations, USI profile, user context and a signed fit estimate into a short-lived evidence envelope.
- A catalog `attributes_complete` attestation, defaulting to false, and a migration. Evidence assembly refuses to assert complete product attributes unless the catalog record is explicitly attested.
- A private `/internal/cal/authorize` BFF endpoint for service-to-service checkout revalidation.
- Commerce checkout code that calls the CAL gateway for each canonical catalog product, fails closed on denial/unavailability, and persists CAL audit rows linked to the order in the same transaction as stock reservations.
- A Commerce migration for `commerce_cal_decision_audits`, plus tests for fail-closed checkout and receipt linkage.

These changes remain an **implementation candidate**, not validated production behavior. In particular:
- A persistent USI/context service implementation candidate has now been added, with explicit-confirmation writes, user-bound profile/context reads, a PostgreSQL migration and change-event rows. Its deployment and tests are not verified. The calibrated fit provider remains unimplemented.
- A trained, calibrated FCI inference provider is not present or empirically validated. A signature proves possession of a key, not scientific calibration.
- The evidence provider cannot become operationally ready until all upstream URLs, tokens, databases, signing keys and migrations are configured.
- The Catalog and Commerce migrations have not been applied to a live non-production PostgreSQL instance in this audit.
- A complete payment journey was not run against real test-mode payment services, nor was an audit receipt observed in a deployed database.

**Required next evidence:** provider readiness checks, real shared-key verification at the decision service, stale/mismatched/missing/unsigned/unavailable integration tests against deployed services, checkout denial without inventory reservation, successful checkout with linked decision receipts, verified payment webhook and duplicate webhook replay, plus an audit query proving the persisted receipt/order linkage.

## Personalization and fit

| Capability | Repository evidence | Readiness |
|---|---|---|
| NPL | Persistent API/store, rejection/correction events and candidate-bound HMAC evidence contract | Foundation exists; deployed PostgreSQL, migration/restore, key rotation and provider-to-CAL live path unverified |
| Explicit cultural declarations | Confirmed declaration/retraction API and signed candidate-bound evidence; no appearance-derived cultural inference intended | Foundation exists; production ingress identity and real consumer verification unverified |
| USI | Decision-service profile contract and alignment logic | Durable authoritative profile store/provider not demonstrated |
| User context / EEPL | Context and policy schema in the decision service | Authoritative context provider and freshness/ownership evidence not demonstrated |
| FCI | Fit estimate contract and signature verification | No validated trained model, calibration study or empirical accuracy evidence |
| CAL | Deterministic arbitration with SHOW/BLOCK/REVIEW semantics | Kernel exists; production evidence chain, durable decision receipts and full downstream enforcement not yet proven |

## Visual experiences

- Virtual Twin pose-skeleton APIs and guarded routes are not proof of full 3D reconstruction, calibrated measurements or a production Twin registry.
- Click It retrieval similarity is not exact product/SKU identification. Candidate results still require candidate-bound CAL authorization.
- Virtual Try-On API boundaries do not prove an actual renderer/model, validated weights, GPU worker, authorized asset lifecycle or quality.
- DermalSight API/ONNX scaffolding does not prove validated production skin inference or bias/quality performance.
- No live model-weight checksum validation, production inference quality benchmark or deployed consent/asset authorization path was demonstrated in this audit.

## Commerce, privacy and scale

- Commerce has substantial code for authenticated accounts, carts, inventory reservations, idempotent orders, Stripe checkout and signed payment webhooks. The new CAL checkout integration and audit migration have not yet been proven in staging.
- Catalog's new `attributes_complete` field is a useful fail-closed attestation, but merchant/catalog workflows must explicitly set it only after validating the attribute taxonomy and required fields.
- No benchmark evidence establishes 300–500 active, usable product records or sub-100 ms vector search under representative load. The repository has not demonstrated the target vector-search path and load test.
- Consent, model governance, retention/deletion, backup/restore, alerting and production access boundaries need deployed evidence. API tests alone are insufficient.

## PR #60 / PR #62 reconciliation

### PR #60 — `feature/twin-clickit-live-inference`

- Head: `c64188c736edc308ae66b68f3bd14122fc21e8c9`
- Compared with main: 61 commits ahead, 1 behind, 27 changed files.
- Unique/required feature work includes Virtual Twin, Vision Intelligence and Xari implementation/test files plus their CI workflows.
- Overlapping files with PR #62 include marketplace HTML, Marketplace BFF files/tests/docs, readiness documentation, Catalog and Commerce files/tests. These must not be merged by taking either branch's complete file versions.
- Latest inspected CI on this branch was failing across multiple workflows. Logs were unavailable.
- Decision: **keep open, do not merge as-is**. Reconcile the overlapping files against PR #62 and preserve the unique Twin/Vision/Xari changes as a reviewed patch set. Do not claim model/renderer readiness from mocked tests.

### PR #62 — `feature/end-to-end-cal-purchase-governance`

- Head: `c731231ce2e80e0cda2df4865321d91139f3b609`
- Compared with main: 73 commits ahead, 0 behind, 23 changed files in the compare response.
- It is the appropriate integration line for candidate-bound display governance and the new checkout-time CAL gate, but its branch history contains many small commits and its required workflows are failing.
- Decision: **keep draft/open; do not merge until the latest CI is green and live non-production integration gates pass**.

## Other branches: classification

| Branch | Comparison against main | Classification / action |
|---|---|---|
| `feature/cal-gateway-integration-v2` | 23 ahead, 0 behind; superseded by PR #62 (PR #62 is 50 commits ahead of this ref) | Historical predecessor; do not merge separately |
| `feature/cirvanna-feature-spine` | 101 ahead, 4 behind; 60 changed files | Contains potentially important unique package/service work, but broad overlap with main and PR #62; audit by path and cherry-pick reviewed files, never merge wholesale |
| `feature/twin-clickit-live-inference` | 61 ahead, 1 behind; 27 changed files | PR #60; preserve unique Virtual Twin/Vision/Xari work, manually reconcile overlap |
| `feature/private-vton-gpu-worker` | 9 ahead, 3 behind; 8 changed files | Unique isolated VTON worker and workflow; keep separate until weights, privacy and inference tests are validated |
| `fix/vision-pose-model-integrity` | 2 ahead, 0 behind; 2 changed files | Unique model-asset integrity fix and test; preserve and review separately |
| `docs/refresh-feature-spine-audit` | 1 ahead, 2 behind; one readiness-document change | Superseded documentation-only change; do not merge over the current commit-pinned audit |
| `feature/catacaci-governance-contracts`, `feature/catalog-service-foundation`, `feature/cultural-identity-explicit-policy`, `feature/eepl-context-policy-core`, `feature/eepl-npl-cal-integration`, `feature/fci-cal-pipeline-integration`, `feature/fci-confidence-contract`, `feature/npl-hard-veto-core`, `feature/usi-explicit-alignment-core`, `feature/marketplace-vertical-slice-2026-10-18`, `feature/virtual-try-on-foundation-2026-10-21` | 0 commits ahead of main in compare results | No unique commit delta to merge; historical refs appear superseded by main |
| Architecture, old audit/docs, source-lineage, migration, maintenance, repair, security and test branches with 0 commits ahead | 0 commits ahead of main in compare results | Their committed content is already ancestral to main; archive candidates. Do not delete automatically without confirming branch ownership/retention requirements |

No branches were deleted. The available GitHub connector exposed no branch-deletion action in this session. Branch comparisons were run for the listed refs, but an ancestry-only result means “no unique commits ahead,” not proof that the branch name is meaningless or that deleting it is harmless.

## CI snapshot and validation limits

At follow-up head `c9c17dab733c490ea5525c7d2e4b454bcb7408f1`, the latest workflow attempts again reported failures for:
- Marketplace BFF checks
- Marketplace contract checks
- Container image builds
- Architecture validation
- Catalog and Commerce service checks
- Vision Intelligence / Virtual Twin / Xari contract checks
- Governance evidence provider tests

The log endpoint returned missing log blobs for sampled jobs, and no artifacts were attached. These failures must be diagnosed from an available runner log or reproduced locally before claiming they are fixed. Rerunning a workflow is not a pass. The private CAL route, Commerce readiness checks and persistent USI/context implementation were refined after the initial audit, but these changes are still unvalidated by passing CI.

## Release gates

1. Restore usable CI logs and make all required PR #62 checks pass.
2. Deploy Catalog, NPL, Cultural Identity, USI/context and decision services to an isolated non-production environment with PostgreSQL migrations and separate credentials.
3. Provision and validate a real fit provider; if no calibrated model is available, expect REVIEW/NO_SHOW and do not expose fit-dependent products.
4. Run signed evidence tests for stale, mismatched, missing, unsigned, foreign-user and unavailable sources against the actual services.
5. Apply Commerce CAL audit migration and test order/stock atomicity, idempotency, webhook signatures, amount/currency checks, duplicate events and persistent audit linkage.
6. Run the entire authenticated browse/search → CAL → display → checkout revalidation → Stripe test webhook → durable audit receipt journey in staging.
7. Run catalog quality/scale tests for 300–500 eligible products and measure retrieval latency at representative concurrency before claiming the <100 ms target.
8. Validate consent, data deletion, backups/restore, access boundaries and operational alerts.
9. Reconcile PR #60's unique files into a reviewed patch set, resolve overlaps manually, and only then decide whether to merge or close PR #60.

**Status policy:** keep current project status as “partially implemented; production readiness not established” until each relevant gate has reproducible evidence pinned to a commit and environment.
