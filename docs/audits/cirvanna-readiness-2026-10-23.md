# Cirvanna Readiness Audit — 2026-10-23

## Audit identity and reproducibility

- **Audit date:** 24 October 2026
- **Repository:** `cirvannaco-png/Cirvanna-demo`
- **main baseline:** `553777cfe7e19d4d05ee92445073cfe8945ab41a`
- **PR #60 inspected:** `c64188c736edc308ae66b68f3bd14122fc21e8c9`
- **PR #62 inspected code head:** `e77715ac01587d23f34be537fd52ea6eee862cd2`
- **PR #62 compare against main:** 111 commits ahead, 0 behind; 31 changed paths.
- **Branches returned:** 59 refs including `main`.
- **Methods:** inspect service source/readiness contracts; compare pull request trees and code paths; inspect workflow-run conclusions; inspect test fixtures and checkout/webhook tests.
- **Validation boundary:** I could inspect source and workflow status, but the GitHub Actions log downloader returned `BlobNotFound` for sampled jobs and the job-step endpoint supplied no step detail. No private staging credentials or active non-production deployment were available. This report therefore distinguishes code/test design from tests confirmed to pass, and neither is presented as a live deployment result.

## Executive decision

**Not production-ready. Do not merge PR #60 or PR #62 yet, do not enable a public governed checkout, and do not mark AI capabilities complete.**

The repository has meaningful service foundations and deterministic decision logic. It does not yet prove a live, complete identity-to-evidence-to-CAL-to-display-to-checkout-to-payment-audit journey. Code presence, mocked tests, a successful build and live deployment are distinct evidence levels.

## Purchase governance and checkout

PR #62 now includes these code-level foundations:
- A per-candidate BFF gateway that requires a matching subject, candidate/variant ID, catalog product ID, request ID, fresh evidence and exact canonical CAL `SHOW` + `may_display=true`.
- `services/governance-evidence-provider` assembles catalog metadata, persistent NPL evidence, explicitly declared cultural requirements, user-bound USI/profile and context, signed fit evidence and a separately HMAC-signed policy-evidence response.
- The policy-evidence contract requires safety, legal-eligibility and user-hard-constraint signals. Signature, subject/request/candidate/catalog binding, source freshness or required-signal failures result in no authorization.
- A catalog `attributes_complete` attestation defaults false. Product metadata is not considered complete just because a candidate is discoverable.
- A private BFF `/internal/cal/authorize` endpoint validates checkout requests. Commerce revalidates the **exact variant/candidate and catalog product as separate identifiers**, including idempotent retries.
- Commerce persists the CAL decision receipt, candidate ID, catalog product ID and order linkage in `commerce_cal_decision_audits`; successful audit rows are committed with stock reservations and order creation. Denial/unavailability is fail-closed with an audit record.

**This is not a verified deployed evidence chain.** The new provider intentionally remains not-ready until its upstream services respond ready. The independent policy-evidence source and calibrated fit provider are not implemented/configured in this repository; their positive responses cannot be invented. The user-context/USI service and Catalog/Commerce migrations have not been proved on a real staging PostgreSQL environment. The BFF/Commerce and provider→Decision integration tests use test clients and fixtures; they do not demonstrate deployed service-to-service authentication.

A full authenticated browse/search → CAL display → checkout-time revalidation → test-mode Stripe webhook → durable order-linked receipt journey **was not run in a deployed non-production environment**. A live payment or production audit is not claimed.

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
- Head inspected: `c64188c736edc308ae66b68f3bd14122fc21e8c9`.
- PR #60 tree: 838 tracked files; PR #62 tree: 858 tracked files. All tracked PR #60 paths are also present in the PR #62 tree; **no file path exists only on PR #60**.
- The Virtual Twin, Vision Intelligence and Xari implementation/test files plus their dedicated CI workflows are byte-identical between the two branch trees. Their implementation is therefore already carried in the PR #62 candidate tree, not unique code requiring a separate merge.
- Eleven shared paths have different content between PR #60 and PR #62: the marketplace HTML and its browser/contract tests; Catalog implementation/tests; Commerce implementation/README/tests; and Marketplace BFF implementation/README/tests.
- The difference is consequential: the PR #60 versions preserve an older demo/direct-catalog account experience. The PR #62 versions replace it with a same-origin, CAL-governed listing boundary; explicit catalog attribute completeness; current candidate-bound checkout revalidation and durable CAL receipt linkage; and tests that reject upstream authorization claims. The governed versions still contain the Click It UI/API route and preserve the Twin/Vision/Xari service implementations.
- All sampled checks on PR #60 were failing, with logs unavailable. The code still does not prove live GPU inference, exact SKU matching, a persistent Twin registry or validated try-on.
- **Decision:** do not merge PR #60 separately. It contains no tracked file path missing from PR #62, and merging it wholesale would reintroduce conflicting, older marketplace/commerce boundary files. It is safe to mark PR #60 superseded by PR #62 while leaving its branch history available for review/reopen if a specific missing semantic change is later demonstrated.

### PR #62 — `feature/end-to-end-cal-purchase-governance`
- Code head inspected: `e77715ac01587d23f34be537fd52ea6eee862cd2`.
- Compared with main: 111 commits ahead, 0 behind; 31 changed paths.
- This is the active integration line for the evidence provider, USI/context implementation candidate, CAL-only display path and Commerce transaction-time revalidation/audit.
- **Decision:** keep draft/open. Required workflows are failing; logs are inaccessible; no independent signed policy-evidence provider, calibrated FCI model or deployed staging journey has been demonstrated. Do not merge or deploy yet.

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

On PR #62 head `e77715ac01587d23f34be537fd52ea6eee862cd2`, the latest recorded run attempts failed for:
- Marketplace BFF checks (run `40049618056`)
- Twin/Vision/Catalog/Xari contract tests (run `40049618167`)
- Marketplace contract checks (run `40049618223`)
- Vision Intelligence contract tests (run `40049618192`)
- Container image builds (run `40049618072`)
- Commerce service checks (run `40049618016`)
- USI/context service tests (run `40049618019`)
- Governance evidence provider tests (run `40049618266`)
- Catalog service checks (run `40049618026`)
- Architecture validation (run `40049618049`)

The connected job-log endpoint returned `BlobNotFound` for sampled jobs and no step detail was available. The precise failing command is therefore unknown; these are recorded failures, not resolved failures. Rerunning a workflow is not a pass, and I will not claim that local commands ran when execution was unavailable.

## Release gates

1. Recover usable CI failure output; fix the actual root causes and obtain green required checks on the exact final PR #62 head.
2. Deploy Catalog, NPL, Cultural Identity, USI/context and Decision services to isolated non-production PostgreSQL, apply migrations, and verify identity, token scopes, HMAC key separation/rotation, readiness and restore.
3. Deploy a private signed policy-evidence provider that returns current safety, legal-eligibility and user-hard-constraint signals, and a distinct trained/calibrated fit provider with a signed, independently validated calibration report. Until both exist, expect REVIEW/NO_SHOW and expose no candidates requiring those gates.
4. Run stale, missing, malformed, unsigned/tampered, foreign-user, candidate/catalog-mismatched and unavailable-source cases against running services; prove each fails closed.
5. Validate NPL correction/retraction, cultural declaration/retraction, USI/context ownership and consent lifecycle in real PostgreSQL, including concurrency, durable persistence and backup/restore.
6. Prove exact variant/catalog-product revalidation blocks stock reservation/order creation on CAL denial or provider failure; on SHOW, persist a receipt linked to the order and candidate.
7. Run authenticated browse/search → CAL SHOW → display → checkout-time CAL → Stripe test payment/webhook/replay → durable audit query in staging. Use a dedicated isolated test tenant and never real payment credentials.
8. Measure a real catalog of 300–500 usable/attested products and sub-100 ms search latency under representative concurrency; publish methodology and p50/p95/p99, not a target assertion.
9. Evaluate FCI calibration and subgroup performance, Virtual Twin pose accuracy, Click It retrieval precision/false matches, VTON image quality, and DermalSight claims/skin-tone/lighting/device quality on held-out labeled datasets.
10. Validate consent enforcement and revocation, image retention/deletion including worker retry/DLQ, secrets/access controls, incident logs, backups/restore, operational alerts and documented degraded behavior.

**Current status:** partially implemented; production readiness not established. Update this status only when evidence is reproducible and pinned to code commit, environment, commands and artifacts.
