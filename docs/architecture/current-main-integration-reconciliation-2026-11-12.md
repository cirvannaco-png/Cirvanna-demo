# Current-main integration reconciliation — 12 November 2026

Repository: `cirvannaco-png/Cirvanna-demo`

This is an implementation and release-boundary audit against the current `main` lineage. It is not evidence of a deployed staging or production environment. Automated tests prove code contracts; they do not prove live providers, backups, storage/CDN behavior, merchant operations or model validity.

## PR reconciliation

| PR | Decision | What was retained or rejected |
|---|---|---|
| #84 — PNELLY / visual discovery | Do not merge the stale branch wholesale. | Its branch was materially divergent from current `main`. The customer-facing Complementer BFF pattern was selectively ported and hardened: Commerce `/me` establishes the customer subject, the BFF forwards both internal and end-user credentials, the Gateway independently verifies the subject, and the BFF returns only an advisory whitelist. The pre-existing Look It route remains separate from Click It. |
| #62 — multi-market commerce | Do not merge the stale branch wholesale. | Current `main` already contains merchant operating-market records, provider-quote storage for FX/tax/fulfilment/payment capabilities, exact-canonical-variant and freshness checks, and like-for-like comparison logic. These are data contracts and service paths, not proof of live FX, tax, delivery or payment provider integrations. |
| #195 — CIL runtime and review enforcement | Selectively ported; do not merge the conflicted head. | Ported CIL pending-review migration, provider-consent revocation migration and cleanup behavior, batch latest-review lookup, Decision Service review veto and tests. Added the same veto to the customer-facing API Gateway candidate path. Production enforcement is now mandatory when `CIRVANNA_ENVIRONMENT=production` (or `COMMERCE_ENVIRONMENT=production`); a false feature flag cannot disable it. |

No stale PR branch is a safe merge base. The integration branch is based directly on current `main`; all changes remain reviewable there.

## Connected paths on current `main` plus this integration branch

### PNELLY, Wardrobe and Complementer

- Wardrobe is owner-scoped through the verified Commerce customer subject.
- Natural-language wardrobe-aware discovery is exposed through `POST /api/wardrobe/recommendations`. It uses active Wardrobe items, consent-aware preference inputs, live Catalog/Commerce offer retrieval, and candidate-bound CAL/CIL authorization. This is a single-turn discovery request, not yet a multi-turn conversation-memory product.
- The daily-look BFF hydrates the user's active Wardrobe, reads durable rotation state, calls the Gateway's three-slot PNELLY composer, and writes the next rotation state with bounded compare-and-swap retries. The required roles are Everyday, Elevated and Explore; missing wardrobe coverage is returned as `needs_input`, not invented clothing.
- Complementer now has a same-origin BFF route. It is separately authenticated, subject-bound again at the Gateway, returns styling advice only and cannot authorise products, prices, merchants or images. Durable Complementer personal memory remains unavailable.
- Wardrobe item and daily-look feedback is explicitly consent-gated and flows through Wardrobe / Identity Learning / NPL. A like/dislike is a style observation, not automatic proof that a marketplace product is suitable or unsuitable.

### CAL and CIL

- The CIL service stores explicit outcomes, suppresses suitability cohorts below 30 distinct contributors, opens a human CAL review request on the configured threshold and stores final CAL review decisions.
- The Gateway now queries the latest product/context-scoped final CIL review before it returns a product decision. A matching BLOCK is an additional veto; a matching SHOW never overrides ordinary CAL, safety, fit, EEPL/NPL or CIL rights/evidence gates.
- Decision Service performs the same review check on its eligibility response path. Both Gateway and Decision Service require this review integration in production; unavailable, malformed or scope-mismatched review data fails closed.
- CIL review lookup timestamps are normalized to timezone-aware UTC before leaving CIL.

**Remaining learning gap:** there is no first-party adapter from the customer Wardrobe/marketplace experience into CIL `POST /outcomes`. The current Wardrobe event path feeds Identity Learning/NPL, not CIL's suitability cohort store. The CIL event contract requires a purpose-bound `recommendation_outcome_learning` consent receipt, a real CAL SHOW receipt, a keyed contributor pseudonym and an explicit suitability report. It would be unsafe to synthesize these from a Wardrobe dislike, product click, save or purchase. REL-20 remains blocked.

## Multi-market commerce status

Current `main` includes database records and APIs for merchant markets, FX quotes, fulfilment quotes, tax quotes, payment capabilities, and exact same-canonical-variant offer comparison. The comparison logic withholds results when merchant market activation, inventory, canonical variant identity, quote freshness, destination-zone match, authoritative tax or fulfilment evidence is missing.

Still unproven / not connected to a real provider:
- provider-operated FX rate retrieval and settlement currency evidence;
- jurisdiction-matched tax calculation and legally reviewed tax categories;
- real fulfilment/courier/merchant-delivery/collection quote providers and serviceability;
- payment provider availability and settlement for each market;
- merchant KYC activation and cross-border operational procedures;
- localized checkout and order/Stripe/webhook reconciliation using the same final landed-cost snapshot.

BFF's direct marketplace comparison route remains fail-closed where candidate-bound CAL purchase/display authorization cannot be established. A quote schema or unit test is not a live provider integration.

## Virtual Twin status

Twin Registry and Virtual Twin metadata/pose capabilities exist. The current product still does not have independently validated full-body reconstruction, a persistent production mesh, private asset-storage lifecycle evidence or a validated Try-On render path. A registry row or pose skeleton is not a 3D Twin. Try-On stays unavailable until the exact subject/resource/consent/asset authorization, model licence and pinned geometry model, geometry validation, private renderer and output lifecycle are proven.

## Click It privacy status

Click It remains deliberately unavailable at the BFF before multipart parsing. Child-specific restrictions, photo-rights intake and a digest-bound public publication gate exist as guarded contracts. They do not establish that every future public publish, restore, sharing, deletion, object-storage, CDN and cache route is covered by real providers. No Click It activation is authorized by this integration.

## Brand and distributor portals

The current Commerce business model is merchant-centric: a merchant is bound to one owner user, owns listings/variants/stock and declares operating markets. The existing "brand partner" page is functionally a merchant application/seller workspace; the repository does not yet have canonical BrandAccount or DistributorAccount entities, tenant membership/role tables, distributor operations APIs, or independent brand/distributor dashboard read models.

The target is two additional first-class tenant types, not two decorative pages:
- **Brand workspace:** verified brand tenant, member roles, catalog portfolio, brand-owned product governance, approved merchant distribution, market eligibility, sales/availability analytics and rights/claims workflow.
- **Distributor workspace:** verified distributor tenant, member roles, service zones, capacity/serviceability, fulfilment quote and shipment operations, order exceptions and service-level analytics.

Each dashboard must be tenant-scoped by server-derived membership; it must not trust a browser-supplied account ID. Metrics must come from durable business events. REL-19 is a release blocker until those entities, APIs, portals and isolation tests exist.

## Release rule

The release ledger now has explicit gates for the brand/distributor workspaces, the CIL event adapter and the integrated PNELLY conversation/wardrobe loop. All gates remain blocked until evidence is tied to the exact release commit and reviewed by the responsible owners. Click It remains disabled. No production launch is authorized by this integration branch.
