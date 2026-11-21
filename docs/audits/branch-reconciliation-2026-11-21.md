# Branch reconciliation audit — current main, 21 November 2026

## Scope and reproducibility

- Repository: `cirvannaco-png/Cirvanna-demo`
- Comparison base: current-main commit `c09ce323c6dc7f5a9e02a9021896ec87bc430440`
- Branch inventory: 253 unique refs, including `main`.
- Method: paginated GitHub branch search followed by a commit-graph comparison of every returned branch against the same pinned main SHA.
- This is a complete graph inventory for the 252 refs at this snapshot. It is not a semantic review of every unique commit or a certification that every branch's changes are useful, safe, or already represented elsewhere.

## Graph comparison result

| Classification | Count | Interpretation |
|---|---:|---|
| Diverged | 179 | Both branch and main contain commits absent from the other. Requires semantic diff and dependency review; never merge wholesale. |
| Behind only | 71 | No unique commits ahead of main. Candidate for archival only after open-PR, dependency, and source-material checks. |
| Ahead only | 2 | Strictly ahead of main with no commits behind. Both require reviewable PR disposition. |
| Identical | 1 | The `main` branch compared with itself. |
| **Total** | **253** | Every returned branch compared against the pinned base. |

The two ahead-only refs at this snapshot are:
- `security/twin-click-it-policy-current-main-2026-11-21`: 8 commits ahead, 0 behind; open PR #260.
- `docs/branch-reconciliation-current-main-2026-11-21`: this audit branch, created from the pinned main; its only ahead content is this report.

## Canonical workstream dispositions

| Workstream | Current disposition | Reconciliation rule |
|---|---|---|
| Shopify compensation and catalogue sync | PRs #242 and #243 merged; remediation/consolidation PR #254 merged. PRs #245, #247, #248 and #251 closed as superseded. | Do not merge the old stacked branches. Preserve them as history; use current main and the merged #254 implementation. |
| Commerce market activation and fulfilment precision | PR #239 and follow-up PR #244 merged. | Legacy fulfilment distances without precision provenance remain ineligible; merchant-market mutation uses the shared parent-row lock and exact provider evidence. |
| PNELLY + Wardrobe | PR #197 merged; its exact-head CI passed. | Current main contains wardrobe-aware discovery, verified-subject context handoff, Complementer advisory flow and consent-aware feedback. Do not remerge the stale reconciliation branch. |
| CAL feedback and purchase authorization | PR #196 merged; API Gateway, BFF and Commerce tests cover SHOW/BLOCK/REVIEW, candidate-bound receipts, comparison and checkout reauthorization. | CAL remains the sole display authority. Production/staging evidence and live decision-provider operations remain separate release gates. |
| Virtual Try-On | PR #249 merged; exact-head worker, private VTON, BFF and container checks passed. | Real FASHN inference path is restricted to maskless flat-lay garments. Model-worn garment photos remain disabled until parser licensing and validation; real GPU/model-weight acceptance is outstanding. |
| Virtual Twin | PR #250 merged as a research-only SAM 3D Body worker. | The worker is not connected to the public Virtual Twin API or Twin Registry. Persistent generation, calibrated measurements, independent body coverage/scale/privacy validation and customer Try-On remain disabled. |
| Look It privacy | PR #255 merged. | Request-scoped consent revocation is in current main. Do not remerge older Look It branches. |
| Click It privacy | PR #235 merged for asset lifecycle provenance; PR #259 is open for BFF consent and photographed-person rights; PR #260 is open for jurisdiction policy. | Click It stays fail-closed pending independent face masking, publication-path attestation, rights-request fulfilment and deletion acceptance. |
| CIL provider consent cleanup | PR #230 closed without merge; its consent/revocation service content was verified as already represented in current main. PRs #257 and #258 were closed as redundant. | Do not merge stale CIL branches based on commit count alone; compare actual file content and current-main behavior. |
| Production readiness and DSI | PRs #202 and #204 remain open; #206 remains an open evidence-led DSI roadmap. | These are release-evidence and roadmap reviews, not proof of live providers, restore drills, operational readiness or validated DSI models. |

## Superseded and merged PR handling

- Merged: #239, #242, #243, #244, #235, #228, #196, #197, #249, #250, #254 and #255.
- Closed as superseded or redundant: #245, #247, #248, #251, #256, #257, #258 and #182.
- Open at this snapshot: #202, #204, #206, #259 and #260, plus other active work not enumerated above.
- A squash-merged branch can still compare as diverged because its original commits are not ancestors of the squash commit. Treat that as historical graph divergence, not evidence that its implementation is missing.

## Highest-priority remaining semantic review

The largest or highest-risk divergent histories should be reviewed by feature family, not merged as a batch:

1. Outfit-evaluation and publication/privacy branches: `feature/outfit-evaluation-publication-guards`, `reconcile/privacy-publication-gate-hardening-2026-11-08`, `feature/outfit-human-evaluation`, `feature/pnelly-outfit-evaluation-benchmark`.
2. Twin/VTON branches: `feat/pnelly-runtime-persistent-twin-tryon`, `feature/twin-clickit-live-inference`, `feature/twin-generation-contract-2026-11-08`, `feature/twin-vton-orchestration-hardening-2026-11-08`, `fix/vton-worker-real-readiness-current-main`.
3. CAL and multi-market branches: `feature/end-to-end-cal-purchase-governance`, `feature/cal-bound-cart-checkout-authorization-2026-11-10`, `feature/commerce-multimarket-offers-rebased`, `feat/multi-market-commerce-current-main`.
4. PNELLY/Wardrobe branches: `feat/pnelly-canonical-identity-current-main`, `feat/pnelly-wardrobe-rotation-integration`, `feat/wardrobe-learning-controls-pnelly-v2`, `feat/verified-purchase-wardrobe-outbox`.
5. DSI branches: `feat/dsi-p0-capture-provenance`, `feat/dsi-p0-verified-capture-pipeline`, `feat/dsi-android-server-verification`, `feat/dsi-perception-and-consent-integration`.
6. Commerce/provider operations and release evidence: `work/release-readiness-cal-commerce-privacy-ops-2026-11-14`, `integration/release-gate-remediation-2026-11-19`, `security/media-delivery-inventory-2026-11-20`.

For each candidate, inspect unique file content and commits, identify whether another merged PR already carries the behavior, run exact-head tests, and forward-port only the useful changes onto a new current-main branch.

## Retention and deletion policy

- Keep `main`, every open-PR head, active dependency branches and branches with unique unreviewed source material.
- Forward-port useful diverged commits selectively. Do not merge old branch histories wholesale.
- Mark behind-only branches as archive candidates only after checking all open PRs, dependent branches and source-lineage references.
- Close duplicate PRs only after the replacement is merged and the replacement diff is verified.
- Do not delete branches as part of this audit. No branch was deleted or force-updated.

## Remaining limitation

The graph comparison is complete for this 253-ref snapshot. Semantic review is not complete for all 179 diverged branches, and the 71 behind-only branches have not all passed dependency/source-retention checks. The next work is prioritized feature-family review and safe archival, not mass merge or mass deletion.
