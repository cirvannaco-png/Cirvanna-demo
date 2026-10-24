# Cirvanna Branch Reconciliation — 2026-10-24

## Comparison baseline

- Repository: `cirvannaco-png/Cirvanna-demo`
- Baseline: `main` at `553777cfe7e19d4d05ee92445073cfe8945ab41a`
- PR #60: `feature/twin-clickit-live-inference` at `c64188c736edc308ae66b68f3bd14122fc21e8c9`
- PR #62 audited code head: `e77715ac01587d23f34be537fd52ea6eee862cd2`
- PR #62 compare against main: 111 commits ahead, 0 behind; 31 changed paths.
- PR #63 audit documentation is stored on `audit/cirvanna-readiness-2026-10-23` and is not part of main.
- 59 refs were returned by GitHub, including `main`.

A direct tree comparison between PR #60 and PR #62 found 838 tracked files in PR #60 and 858 in PR #62. Every tracked PR #60 path exists in the PR #62 tree (zero PR #60-only paths); 11 shared paths have differing blob contents. The Virtual Twin, Vision Intelligence and Xari implementation/test files and their dedicated workflows are byte-identical across the two branch trees.

Commit comparison identifies unique commit deltas, not semantic safety by itself. A branch with zero commits ahead of main is an ancestor-only branch relative to this baseline; it may be an old work pointer, but deleting it still requires checking ownership/retention needs.

## Branches with unique commits requiring separate treatment

| Branch | Compare against main | Unique changes / decision |
|---|---|---|
| `feature/end-to-end-cal-purchase-governance` | 111 ahead, 0 behind; 31 changed paths | Current integration line for candidate-bound CAL display, signed NPL/cultural/fit/policy evidence contracts, USI/context persistence candidate and Commerce checkout receipt. Keep draft/open until required CI and staging evidence pass. |
| `feature/twin-clickit-live-inference` | 61 ahead, 1 behind; 27 changed paths | PR #60. Tree comparison found no PR #60-only tracked paths; Twin/Vision/Xari feature files/workflows are identical to PR #62. Eleven shared UI/Catalog/Commerce/BFF files differ; PR #62 carries the stricter CAL-only UI, attribute-completeness, exact variant/product checkout revalidation and durable audit behavior. Do not merge PR #60 separately or reintroduce its older direct/demo paths. Mark PR #60 superseded while preserving its branch history. |
| `feature/cirvanna-feature-spine` | 101 ahead, 4 behind; 60 changed paths | Broad package/service changes, including FCI confidence, NPL/Cultural evidence helpers, CAL pipeline, Wardrobe and API gateway. Potentially important but too broad to merge wholesale. Audit each path and retain only reviewed deltas not already represented in main/PR #62. |
| `feature/private-vton-gpu-worker` | 9 ahead, 3 behind; 8 changed paths | Unique isolated VTON worker and workflow. Keep separate pending real model assets, GPU inference, consent/asset authorization, quality and privacy validation. |
| `fix/vision-pose-model-integrity` | 2 ahead, 0 behind; 2 changed paths | Unique model-asset integrity guard and tests. Preserve; review and port as a narrow patch after CI is recoverable. |
| `feature/cal-gateway-integration-v2` | 23 ahead, 0 behind; no commits ahead of PR #62 | Superseded by the current PR #62 integration line. Do not merge separately. |
| `docs/refresh-feature-spine-audit` | 1 ahead, 2 behind; readiness document only | Documentation-only update is superseded by this newer commit-pinned audit. Do not merge over newer status evidence. |

## Branches with zero commits ahead of main

The 50 historical refs listed below had zero unique commits ahead of `main` in their compare results on the unchanged main baseline. The repository now exposes 59 refs including `main`; the new audit branch contains only the audit material. These are archival candidates only after confirming that no external workflow, open review or retention requirement depends on the branch name. No branch was deleted in this work.

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

1. Resolve PR #62's CI failures with usable logs and verify the new signed policy-evidence/fit provider readiness contract against deployed dependencies.
2. Prove checkout-time authorization binds both exact variant and catalog product IDs and durably links the receipt to the order.
3. Do not merge PR #60 separately: its tracked file paths are all represented in PR #62 and its implementation branches are already present. Close it as superseded, not merged, after updating its status/body.
4. Review `feature/cirvanna-feature-spine` as narrow independent patches, not a whole-branch merge.
5. Review `fix/vision-pose-model-integrity` as a narrow security patch.
6. Keep `feature/private-vton-gpu-worker` isolated until model/consent/quality gates pass.
7. Archive zero-ahead historical branches only after repository owners confirm they can be retired.

## Limitations

The latest PR #62 head `e77715ac01587d23f34be537fd52ea6eee862cd2` has 111 commits ahead of main and 31 changed paths. All sampled workflows on that head reported failure; the job-log endpoint returned `BlobNotFound` and no step detail was available, so exact root causes are not asserted. No code branch has been merged or deleted. The comparison records code/tree presence and branch ancestry, not runtime quality or production readiness.
