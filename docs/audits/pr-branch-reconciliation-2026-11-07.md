# PR and branch reconciliation — 7 November 2026

**Repository:** `cirvannaco-png/Cirvanna-demo`  
**Main baseline audited:** `4b515a109da77bc9f98944a81b0b939aa5ebab09`  
**Open pull requests:** 19  
**Branch refs enumerated:** 143  
**Production release status:** blocked; see `docs/release/release-gates.json`.

## Summary

This is a source-control inventory, not production certification. All open PRs below were compared to the current main state or their recorded workflow history. A green workflow on an old, diverged branch is not current-main integration evidence. No conflicting PR was force-merged. No branch ref was deleted: the connected GitHub toolset exposes branch search and ref updates but no delete-ref action, and historical source/audit branches must not be discarded blindly.

Recent reconciled changes:
- Merged #124 private asset-service foundation (fake S3 contract tests; real bucket and policy remain unverified).
- Merged #127 VTON artifact provenance and commercial license guard (real weights/GPU and parser rights remain blocked).
- Merged #117 PNELLY human-review evaluator contract (review dataset remains empty).
- Merged #154 and #156 checklist reconciliation.
- Merged #155 current-main correction so pose-skeleton inference cannot be reported as persistent Twin generation or preview.
- Closed #141, #134, #104, #97, #63, #65 and #125 as superseded/stale with explanatory comments.

## Remaining open PRs and next action

| PR | Title | Disposition |
|---|---|---|
| [#129](https://github.com/cirvannaco-png/Cirvanna-demo/pull/129) | feat(consent): add resource-bound media consent verification | Consent consolidation candidate with #123. Rebase both onto current main, retain one canonical resource-bound verifier contract and test all image-processing, body-measurement, Twin-storage, VTON and Click It scopes. Current main still exposes only profile/personalization scopes; no live provider. |
| [#126](https://github.com/cirvannaco-png/Cirvanna-demo/pull/126) | fix(vton): harden GPU worker readiness and backend selection | Stacked VTON worker hardening with #122. Consolidate with #127 already merged; retain CUDA/VRAM, offline parser cache, concurrency and 429 behavior. Current-head CI absent; no model weights/GPU or commercial parser clearance. |
| [#123](https://github.com/cirvannaco-png/Cirvanna-demo/pull/123) | feat(identity): add resource-bound consent verification for Twin and try-on | Overlaps #129. Port the complete resource-bound consent scope set and bundle semantics into one current-main PR; branch conflicts. Do not merge separately and risk two migrations/API shapes. |
| [#122](https://github.com/cirvannaco-png/Cirvanna-demo/pull/122) | fix(vton): enforce worker trust and real model readiness | VTON worker source/readiness follow-on to #127. Rebase and reconcile with #126; no model weights, real GPU inference or NVIDIA parser commercial license clearance. |
| [#118](https://github.com/cirvannaco-png/Cirvanna-demo/pull/118) | feat(pnelly): migrate canonical assistant identity and preserve Xari contracts | PNELLY/Xari canonical identity migration. Rebase onto current Xari/BFF contracts and confirm one runtime and backward compatibility; branch conflicts are present. |
| [#115](https://github.com/cirvannaco-png/Cirvanna-demo/pull/115) | Add human-reviewed outfit evaluation and simple baseline | Richer outfit-evaluation extension after #117. Rebase only evaluator deltas that are not duplicates; blank dataset and no production candidate/exposure trace. |
| [#111](https://github.com/cirvannaco-png/Cirvanna-demo/pull/111) | Harden outfit evaluation and image publication safety gates | Click It publication-safety work stacked on #107. Keep blocked until base privacy service is rebased and every binary publish/delivery route is gated by current asset-bound attestation. |
| [#110](https://github.com/cirvannaco-png/Cirvanna-demo/pull/110) | Establish human-reviewed outfit evaluation and baseline | Advanced human-evaluation protocol overlaps merged #117 and #115; targeted evaluator workflows failed on the recorded head. Rebase and reconcile useful non-duplicate metrics; real dataset remains empty. |
| [#107](https://github.com/cirvannaco-png/Cirvanna-demo/pull/107) | Click It: add privacy governance, consent and image-rights service | Click It privacy governance/consent foundation. Draft/blocked on provider and publication integration; needs current-main rebase, end-to-end binary-origin/CDN tests, and safe production asset provider. |
| [#102](https://github.com/cirvannaco-png/Cirvanna-demo/pull/102) | feat(commerce): add multi-market offer context and landed comparison | Preferred multi-market Commerce candidate over closed #97. Branch is green on old head but conflicts with current main; rebase, rerun migrations and all workflows. FX/tax/fulfilment provider quotes are not live. |
| [#84](https://github.com/cirvannaco-png/Cirvanna-demo/pull/84) | PNELLY: separate Look It discovery, keep Click It independent | Look It and Click It separation. Port only the distinct Look It conversational discovery contract onto current main; Click It stays independent and disabled until the privacy/consent/provider controls work. Re-run integration. |
| [#77](https://github.com/cirvannaco-png/Cirvanna-demo/pull/77) | Add governed Brand Partner Portal and Founder Commerce Console | Brand Partner Portal / Founder Console. Rebase current main; Founder Console already exists, Brand Partner Portal still needs UI/service integration. Do not merge old overlapping Commerce/BFF code blind. |
| [#76](https://github.com/cirvannaco-png/Cirvanna-demo/pull/76) | Correct CRFP naming and separate marketplace/system scopes | CRFP acronym/scope governance docs. Port documentation/ADR/module inventory updates onto current main after checking canonical naming; old branch is diverged. |
| [#69](https://github.com/cirvannaco-png/Cirvanna-demo/pull/69) | Add saved and shareable AM/PM skincare routines | Standalone skincare-routine service. Rebase and rerun focused API, migration, owner-isolation, expiry/revocation and UI integration checks; provider recommendations remain separate. |
| [#68](https://github.com/cirvannaco-png/Cirvanna-demo/pull/68) | feat: add Cirvanna Living Filters MVP | Living Filters browser-side MVP. Rebase for code quality if retained, but issue #70 physical Android QA remains a separate mandatory acceptance gate; no device evidence exists. |
| [#67](https://github.com/cirvannaco-png/Cirvanna-demo/pull/67) | Add Cirvanna intelligent marketplace filters | Intelligent Marketplace filters. All relevant branch workflows failed; rebase and fix Catalog/Commerce/BFF contracts and tests before reconsideration. |
| [#66](https://github.com/cirvannaco-png/Cirvanna-demo/pull/66) | feat(appearance): governed specialist registry and Look + Makeup slice | Appearance specialist registry / Look + Makeup slice. All relevant branch workflows failed; rebase and verify canonical Catalog/NPL/CAL ownership before merge. |
| [#64](https://github.com/cirvannaco-png/Cirvanna-demo/pull/64) | Add governed PAMASMMA cognitive and brand-auth foundations | PAMASMMA cognitive and brand-auth foundations. Architecture validation failed; separate deterministic cognitive handlers from imported mock auth/security artifacts and revalidate against current governance before any merge. |
| [#62](https://github.com/cirvannaco-png/Cirvanna-demo/pull/62) | Enforce candidate-bound CAL authorization across marketplace and checkout | Candidate-bound CAL marketplace/checkout gate. Its branch workflows failed; rebase, fix tests and verify real evidence providers/decision receipts on staging before use as production authorization. |

### Required consolidation rules

- Keep #123 and #129 as one consent-verifier workstream; select one canonical migration, scope vocabulary and endpoint, then port onto current main.
- Keep #122 and #126 as one VTON worker-hardening workstream layered on merged #127; do not enable inference without licensed models and a real GPU test.
- Keep #110 and #115 as evaluation-tool extensions to merged #117; no synthetic fixtures count as human labels or quality evidence.
- Keep #107 and #111 as one Click It privacy publication-control stack; do not enable Click It until binary storage, every publishing/delivery route, revocation and deletion are provider-tested.
- Keep #102 as the only active multi-market implementation; #97 is closed. Merge only after a current-main rebase and green CI.
- Other PRs should be rebased individually and merged only after current-main tests, architecture ownership and external release-gate review.

## Branch inventory

All 143 branch refs returned by GitHub search are listed below. These include branches for open PRs, merged PRs, experiments, historical audits, source preservation, migration and maintenance. Presence in this list does not mean the branch is production-active. Branches are preserved for provenance until a reviewed retention/deletion plan exists.

### Counts by branch prefix
- `feature`: 48
- `feat`: 33
- `docs`: 15
- `fix`: 11
- `integration`: 6
- `audit`: 4
- `engineering`: 3
- `governance`: 3
- `hotfix`: 3
- `maintenance`: 3
- `migration`: 3
- `security`: 3
- `architecture`: 2
- `test`: 2
- `Cirvannaco-updates`: 1
- `chore`: 1
- `main`: 1
- `repair`: 1

### Complete ref list
```text
Cirvannaco-updates
architecture/catacaci-decision-contract-audit
architecture/cirvanna-monorepo-foundation
audit/cfrp-v6-integration-review
audit/cirvanna-readiness-2026-10-23
audit/full-code-snippet-inventory-2026-10-22
audit/source-completeness-governance-2026-10-17
chore/codespaces-workspace-bootstrap
docs/adr-0007-wardrobe-pnelly-multimarket-commerce
docs/cirvanna-master-product-checklist
docs/codespaces-and-vertical-slice-2026-10-22
docs/current-implementation-status-2026-10-22
docs/implementation-status-2026-10-15
docs/implementation-status-v2
docs/pnelly-brand-clearance-and-migration-gate
docs/reconcile-checklist-after-twin-capability-fix
docs/refresh-feature-spine-audit
docs/update-checklist-after-pnelly-integration
docs/update-current-status
docs/update-marketplace-status-2026-10-18
docs/update-product-checklist-after-integrations
docs/verified-product-checklist-2026-11-07
docs/virtual-try-on-model-readiness-2026-10-21
engineering/cirvanna-end-to-end-slice-2026-10-21
engineering/dermalsight-onnx-service
engineering/vertical-slice-plan-2026-10-21
feat/commerce-wardrobe-sync-worker
feat/daily-look-retention-experiments
feat/daily-look-retention-experiments-v2
feat/pnelly-runtime-persistent-twin-tryon
feat/pnelly-runtime-twin-vton-integration
feat/pnelly-twin-vton-integration
feat/pnelly-wardrobe-rotation-integration
feat/private-asset-service
feat/resource-bound-consent-verification
feat/resource-bound-media-consent
feat/resource-bound-media-consent-v2
feat/resource-bound-twin-consent
feat/saved-outfit-piece-editing-v1
feat/style-color-profile-v1
feat/style-color-profile-v2
feat/style-desk-colour-profile-v1
feat/verified-purchase-wardrobe-outbox
feat/virtual-twin-persistent-registry-v1
feat/virtual-twin-registry-current-main
feat/vton-worker-artifact-integrity
feat/vton-worker-readiness-and-backend-selection
feat/wardrobe-item-edit-ui
feat/wardrobe-item-editing-v1
feat/wardrobe-learning-controls-pnelly-v2
feat/wardrobe-learning-data-controls
feat/wardrobe-learning-data-controls-current-main
feat/wardrobe-outfit-wear-history
feat/wardrobe-revival-rotation-cycle
feat/wardrobe-rotation-state-store
feat/wardrobe-taxonomy-current-main
feat/wardrobe-verified-purchase-ingestion
feat/wardrobe-verified-purchase-ownership
feat/wardrobe-verified-purchase-wear-history
feature/brand-partner-founder-portals
feature/cal-gateway-integration-v2
feature/catacaci-governance-contracts
feature/catalog-canonical-variants
feature/catalog-service-foundation
feature/cirvanna-feature-spine
feature/click-it-privacy-shield
feature/click-it-privacy-shield-v2
feature/click-it-privacy-shield-v3
feature/commerce-like-for-like-comparison
feature/commerce-like-for-like-comparison-stacked
feature/commerce-like-for-like-comparison-v2
feature/commerce-multimarket-offers
feature/commerce-multimarket-offers-rebased
feature/commerce-variant-offer-freshness
feature/complementer-agent
feature/complementer-personal-aesthetic-intelligence
feature/cultural-identity-explicit-policy
feature/eepl-context-policy-core
feature/eepl-npl-cal-integration
feature/end-to-end-cal-purchase-governance
feature/fci-cal-pipeline-integration
feature/fci-confidence-contract
feature/human-reviewed-outfit-evaluation
feature/intelligent-filter-layer
feature/living-filters-mvp
feature/marketplace-vertical-slice-2026-10-18
feature/merchant-and-founder-portals
feature/npl-hard-veto-core
feature/outfit-evaluation-publication-guards
feature/outfit-human-evaluation
feature/pamasmma-cognitive-brand-auth
feature/pnelly-evaluation-benchmark
feature/pnelly-look-it-entrypoint
feature/pnelly-look-it-visual-search
feature/pnelly-outfit-evaluation-benchmark
feature/pnelly-outfit-evaluation-clean
feature/privacy-governance-service
feature/private-vton-gpu-worker
feature/skincare-routines
feature/specialist-ecosystem-foundation
feature/tari-marketplace-assistant
feature/trusted-learning-cal-marketplace-readiness
feature/twin-clickit-live-inference
feature/usi-explicit-alignment-core
feature/virtual-try-on-foundation-2026-10-21
feature/wardrobe-pnelly-npl-eepl
feature/xari-marketplace-assistant
fix/cfrp-v6-runtime-safety
fix/cultural-policy-unknown-fail-closed
fix/malformed-policy-result-fail-closed
fix/restore-ignored-source-candidates
fix/saved-outfit-ci-regressions
fix/virtual-twin-capability-truth-main
fix/virtual-twin-capability-truthfulness
fix/virtual-twin-upload-limits
fix/vision-pose-model-integrity
fix/vton-worker-trust-and-readiness
fix/wardrobe-rotation-data-erasure
governance/correct-crfp-scope-model
governance/crfp-marketplace-and-system-scopes
governance/source-contracts-and-release-gates
hotfix/fail-closed-click-it-unmasked-ingress
hotfix/gateway-withhold-unverified-product-media
hotfix/public-marketplace-image-withholding
integration/catacaci-governance-extensions
integration/fci-source-snippet-promotion-2026-10-22
integration/source-lineage-governor-2026-10-22
integration/source-lineage-integrity-2026-10-22
integration/source-reconstruction
integration/virtual-twin-api-foundation
main
maintenance/classify-staged-cdic-manifest
maintenance/classify-staged-cdic-manifest-v2
maintenance/rename-cdic-source-fragment
migration/arrange-cirvanna-source-candidates
migration/preserve-all-source-material
migration/source-lineage-governor-2026-10-17
repair/source-candidate-syntax
security/detect-unquoted-password-defaults
security/expand-secret-scan-coverage
security/source-intake-credential-audit
test/secret-scan-regressions
test/virtual-twin-api-contracts
```

## Production work not verifiable from repository branches

- **Stripe and ownership:** paid checkout/webhook → Commerce outbox → Sync worker → Wardrobe source contracts exist. Refund/return/chargeback events and Wardrobe ownership reversal policy do not. No live Stripe credentials or webhook endpoint verification was available.
- **PostgreSQL:** CI applies and restores test databases for defined workflows; there is no active Cirvanna production PostgreSQL available through connected services. The one visible company Render database belongs to Midas Touch 2 and was not touched. The connected Cirvanna Supabase project is inactive; migration listing timed out. Connected Neon account returned no Cirvanna project.
- **Twin/consent/assets:** owner-scoped registry and private asset-service source are present; resource-bound media/Twin consent verifier, live S3-compatible bucket, full-body mesh generator/validator and deletion reconciliation remain absent or unprovisioned.
- **Virtual Try-On:** private worker contracts are present; model weights and GPU runtime are absent. The FASHN Human Parser has a non-commercial license restriction unless written commercial permission or a compliant replacement is supplied.
- **Android:** no physical device test evidence. Issue #70 remains open for camera lifecycle, tracking, FPS, memory, thermal and network QA.
- **Color analysis:** current Style Desk data is user-declared colour preference only. No objective skin/undertone/palette model, lighting capture protocol or subgroup validation is certified.
- **FCI:** adapter/contract foundations exist but no calibrated independent provider or representative garment/body dataset is available. No 4% measurement-accuracy claim is validated.
- **Recommendations:** merged #117 adds the review protocol and evaluator, but the labelled dataset is empty and no algorithm-vs-baseline outcome or connected real user feedback metric exists.
- **Release:** all REL-01–REL-12 production gates remain blocked; no gate was marked passed from unit tests or mocks.

## Branch hygiene

Keep `main` as the sole production baseline. Preserve merged feature branches and historic/audit/source-preservation refs until owners review whether each has unique commits or provenance value. For each remaining open PR, either rebase onto current main and rerun its exact workflow set, consolidate it into the canonical workstream above, or close it with an explicit supersession reason. Do not force-push over protected history or delete branches to make the branch count look clean.
