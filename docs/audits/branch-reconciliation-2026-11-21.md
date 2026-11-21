# Branch reconciliation audit — 2026-11-21

## Scope and method

Compared every branch returned by GitHub for `cirvannaco-png/Cirvanna-demo` against the current `main` ref using GitHub's commit comparison endpoint. The inventory contained 235 unique branch names, including `main`. This is a graph comparison, not a semantic code review: it identifies ahead/behind counts but does not prove that unique commits are useful, safe, or unmerged elsewhere.

## Result

| Classification | Count | Meaning |
|---|---:|---|
| Diverged | 160 | Branch contains commits not in main and main contains commits not in branch. Requires selective commit/content review and forward-porting. |
| Behind only | 69 | No unique commits ahead of main; candidate for archival after checking open PRs, external references and any uncommitted work. |
| Ahead only | 5 | Branch is strictly ahead of main; candidate for direct PR review, not automatic merge. |
| Identical | 1 | The `main` branch compared with itself. |
| **Total** | **235** | Every returned branch compared. |

## Strictly-ahead branches

These five branches were ahead of main with zero commits behind:

| Branch | Ahead | Behind | Disposition |
|---|---:|---:|---|
| `fix/commerce-review-races-2026-11-21` | 10 | 0 | Review urgently; compare with merged #239 and inspect whether the race fix is already covered. |
| `integration/virtual-twin-archive-review-2026-11-20` | 1 | 0 | Preserve; assess the archive review as a documentation/review artifact, not a Twin implementation. |
| `reconcile/cil-feedback-reviews-current-main-2026-11-12` | 1 | 0 | Review against open #196 and current CIL behavior; avoid duplicate promotion. |
| `reconcile/pnelly-complementer-wardrobe-current-main-2026-11-12` | 1 | 0 | Review against open #197 and verify end-to-end behavior before promotion. |
| `security/asset-lifecycle-provenance-2026-11-21` | 1 | 0 | Review against open #235; private-only defaults and missing publication/revocation integrations remain explicit blockers. |

## Highest-risk branch-management findings

1. The branch inventory is not a merge queue. The 160 diverged branches must not be merged wholesale.
2. The 69 behind-only branches are not automatically deletable: first check whether an open PR references them, whether their changes were superseded, and whether they contain unique source material.
3. Several feature families have multiple competing generations: Click It privacy, CAL, multi-market commerce, PNELLY/Look It, Wardrobe, Twin/VTON and DSI. Each family needs one canonical forward-port branch and a recorded disposition for the others.
4. The Shopify work is a dependency chain. #242 contains compensation/refund behavior; #243 is stacked on it. Review findings discovered in both must be fixed before either is treated as production-ready.
5. Open PRs are the primary preservation boundary. Do not delete a branch referenced by an open PR or a dependent branch.

## Reconciliation policy

- **Keep:** current main, open-PR heads, active dependency branches, and branches with unique work not yet reviewed.
- **Forward-port:** useful diverged commits onto a new branch created from current main; do not merge stale histories wholesale.
- **Archive candidate:** behind-only branches only after proving their PR is closed/merged and their useful commits are represented in main or another preserved branch.
- **Close as superseded:** duplicate PRs only after the replacement PR is merged and the final diff is verified.
- **Delete:** only after the above disposition is recorded and no open PR/dependent branch references the branch.

## Immediate preservation queue

- Shopify: #242, #243 and remediation PR #245.
- PNELLY/Wardrobe: #197.
- CIL/CAL feedback: #196 and #230.
- Twin archive assessment: #228.
- Asset lifecycle/privacy: #235, #174, #182 and #107.
- CAL purchase authorization: #62 and its newer forward-port/reconciliation branches.
- Multi-market commerce: #102 and newer integration branches.

## Limitations

The comparison endpoint does not expose a semantic patch review for every branch. This audit therefore classifies all branch histories but does not certify all 235 branch contents. The next pass must inspect unique commits for the 160 diverged branches, reconcile open-PR dependencies, and only then archive stale branches. No branch was deleted or force-updated during this audit.
