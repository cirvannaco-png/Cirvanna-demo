# Cirvanna Branch Reconciliation — 2026-10-23

## Comparison baseline

- Repository: `cirvannaco-png/Cirvanna-demo`
- Baseline: `main` at `553777cfe7e19d4d05ee92445073cfe8945ab41a`
- PR #60: `feature/twin-clickit-live-inference` at `c64188c736edc308ae66b68f3bd14122fc21e8c9`
- PR #62 initial compare head: `c731231ce2e80e0cda2df4865321d91139f3b609`
- PR #62 follow-up head: `5a0b8468bc2e235ea11b4596cb1820c70a55d904`
- 58 refs were returned by GitHub, including `main`.

Commit comparison identifies unique commit deltas, not semantic safety by itself. A branch with zero commits ahead of main is an ancestor-only branch relative to this baseline; it may be an old work pointer, but deleting it still requires checking ownership/retention needs.

## Branches with unique commits requiring separate treatment

| Branch | Compare against main | Unique changes / decision |
|---|---|---|
| `feature/end-to-end-cal-purchase-governance` | 73 ahead, 0 behind; 23 changed paths | Current integration line for evidence-provider, candidate-bound CAL and Commerce checkout gate. Keep draft/open; required CI and live evidence gates remain. |
| `feature/twin-clickit-live-inference` | 61 ahead, 1 behind; 27 changed paths | PR #60. Preserve unique Virtual Twin, Vision Intelligence, Xari and their tests/workflows. Manually reconcile overlapping Marketplace BFF, marketplace HTML, readiness docs, Catalog and Commerce files against PR #62. Do not merge whole branch. |
| `feature/cirvanna-feature-spine` | 101 ahead, 4 behind; 60 changed paths | Broad package/service changes, including FCI confidence, NPL/Cultural evidence helpers, CAL pipeline, Wardrobe and API gateway. Potentially important but too broad to merge wholesale. Audit each path and retain only reviewed deltas not already represented in main/PR #62. |
| `feature/private-vton-gpu-worker` | 9 ahead, 3 behind; 8 changed paths | Unique isolated VTON worker and workflow. Keep separate pending real model assets, GPU inference, consent/asset authorization, quality and privacy validation. |
| `fix/vision-pose-model-integrity` | 2 ahead, 0 behind; 2 changed paths | Unique model-asset integrity guard and tests. Preserve; review and port as a narrow patch after CI is recoverable. |
| `feature/cal-gateway-integration-v2` | 23 ahead, 0 behind; no commits ahead of PR #62 | Superseded by the current PR #62 integration line. Do not merge separately. |
| `docs/refresh-feature-spine-audit` | 1 ahead, 2 behind; readiness document only | Documentation-only update is superseded by this newer commit-pinned audit. Do not merge over newer status evidence. |

## Branches with zero commits ahead of main

The following 50 refs returned no unique commits ahead of `main` in their compare results. They are candidates for archival/cleanup after confirming no external workflow, open review or retention requirement depends on the branch name. No branch was deleted in this work.

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
- `feature/catacaci-governance-contracts`
- `feature/catalog-service-foundation`
- `feature/cultural-identity-explicit-policy`
- `feature/eepl-context-policy-core`
- `feature/eepl-npl-cal-integration`
- `feature/fci-cal-pipeline-integration`
- `feature/fci-confidence-contract`
- `feature/marketplace-vertical-slice-2026-10-18`
- `feature/npl-hard-veto-core`
- `feature/usi-explicit-alignment-core`
- `feature/virtual-try-on-foundation-2026-10-21`
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

## Merge order

1. Resolve PR #62's CI failures and prove the evidence provider against deployed NPL, Cultural Identity, Catalog, USI/context and fit providers.
2. Prove checkout-time CAL authorization and durable audit linkage in non-production.
3. Reconcile PR #60's overlapping files by manually porting its unique Twin/Vision/Xari implementation and tests; rerun all required checks.
4. Review `feature/cirvanna-feature-spine` as narrow independent patches, not a whole-branch merge.
5. Review `fix/vision-pose-model-integrity` as a narrow security patch.
6. Keep `feature/private-vton-gpu-worker` isolated until model/consent/quality gates pass.
7. Archive zero-ahead historical branches only after repository owners confirm they can be retired.

## Limitations

The connected CI job-log endpoint returned missing log blobs for sampled failing jobs, so root causes were not fabricated. No branch deletions or merges were performed. This report records a commit comparison, not a claim that the feature branches have been runtime-validated.
