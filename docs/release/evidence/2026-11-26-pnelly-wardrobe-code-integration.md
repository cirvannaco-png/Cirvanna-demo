# PNELLY and Wardrobe integration review — 2026-11-26

**Classification:** source/CI integration evidence only; not production acceptance.  
**Candidate source revision reviewed:** `bfa8ad52613f2d8e355a659fd5fb0240d5a8e475`.

## Verified implementation boundaries

- PNELLY explicit style preferences are saved only after the user confirms a bounded aesthetic-taxonomy value. The write is subject-bound through Commerce `/me`, requires the exact active `profile_storage` receipt, records the source and originating advisory request ID, uses optimistic profile versioning and is idempotent on retry.
- Identity Learning revalidates the taxonomy and exact consent receipt. Revoked profile-storage consent blocks reads and writes; deactivated preferences are excluded from ranking hydration.
- The daily-look flow evaluates EEPL before profile hydration/composition. Missing or stale required context produces REVIEW; explicit policy violations produce BLOCK. Neither path writes rotation state or composes looks.
- Daily looks are composed from authenticated Wardrobe snapshots and persisted rotation state. The BFF validates owner-scoped Wardrobe responses and rotation-state versioning.
- Complementer remains a separate advisory; it cannot authorize product display. CAL remains the authority for product/offer details, and a PNELLY recommendation or Look It match is not a display authorization.
- Look It remains a separate short-lived image-reference flow and is documented separately in `2026-11-26-click-it-look-it-route-containment.md`.

## CI evidence

The candidate's PNELLY route-contract, Wardrobe persistence, Identity/temporal learning, Marketplace BFF, Decision Gateway, and related service workflows are included in the PR #338 suite. The exact current-head run must finish successfully before this evidence is treated as current. Unit/contract tests are not a substitute for deployed end-to-end evidence.

## Outstanding acceptance evidence

1. Deploy PNELLY, Identity Learning, Wardrobe, Decision Gateway and Marketplace BFF from one immutable candidate and verify exact image digests.
2. Execute real authenticated end-to-end consent grant, preference save/list/replace/deactivate, revoke, export and deletion flows.
3. Verify cross-user isolation, replay/idempotency, concurrent profile-version conflicts and rotation persistence across sessions/devices.
4. Verify real Catalog/Commerce candidate retrieval, CAL SHOW on every surfaced item, CIL rights/evidence approval, and no product details on BLOCK/REVIEW.
5. Run cohort experiments comparing integrated and disconnected journeys; report retention, usefulness, rejection, edit and return outcomes without treating correlation as causation.

## Gate disposition

REL-21 remains **BLOCKED** until deployed end-to-end tests, real service identities, consent lifecycle, CAL/CIL enforcement and cohort evidence are complete.
