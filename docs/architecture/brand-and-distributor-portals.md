# Brand and Distributor Portals

**Status: acceptance architecture; not implemented as separate tenant products.** The current Commerce partner workspace is a merchant/seller application bound to one owner_user_id. The current /brand-portal UI calls that merchant workflow. It is not yet a separate brand-account service, and the repository does not currently define a distributor tenant or distributor API. Do not present the seller workspace as satisfying either requirement.

## Required business principals

The platform must model three distinct business principals rather than overloading the current merchant record:

1. **Brand** — owns brand identity, approved brand assets, canonical product relationships, product claims/evidence submissions, market availability, brand-approved distributors and brand-level commercial reporting.
2. **Distributor** — an independently verified legal entity authorized to distribute one or more brands in a defined territory, channel and period. It owns its distribution contracts, market coverage, inventory/fulfilment capabilities, wholesale terms where permitted, orders and settlements.
3. **Merchant / retailer** — a business that lists and sells goods to consumers through Commerce. A merchant can be a brand-owned retail channel or a separately authorized retailer, but is not automatically the brand owner or distributor.

A single legal organization may hold more than one business relationship only through explicitly approved, separately scoped memberships. A user account is not a business tenant.

## Portal experiences

### Brand portal

Dedicated route: /brand-portal (future tenant-backed experience).

- Brand application, legal verification, ownership and trademark/representation evidence.
- Organization member invitations, roles, MFA/session controls, access revocation and audit history.
- Canonical Catalog product onboarding/linking. Brands may submit product data, ingredient declarations, claims and supporting evidence; Catalog remains the canonical product owner and CIL rights/evidence review remains mandatory.
- Market-specific availability, authorized seller/distributor relationships, brand-controlled assets and claims.
- Sales and conversion summaries aggregated only from the brand's authorized product/offer/order relationships. No exposure of another seller's customer identities, settlement data or unrelated orders.
- Review queue for Catalog data corrections, CIL evidence requests, CAL outcomes and content-rights actions.

### Distributor portal

Dedicated route: /distributor-portal (not present yet).

- Separate distributor onboarding, legal-entity checks and signed brand-distribution authorization.
- Territory, channel, category, SKU and contract-validity scopes. Authorization must be active at the time a distributor creates or fulfils an offer.
- Market operations: warehouse/location coverage, inventory feeds, fulfilment methods and capacity, service levels, delivery zones and cut-off times.
- Distributor-owned offers, wholesale/retail price schedules where approved, taxes/customs evidence, comparable landed-cost inputs, order allocation, shipment events, returns and reconciliation.
- Distributor performance metrics limited to its authorized orders, offers and fulfilment events. No other distributor's inventory or financial data.
- Contract expiry, suspension, recalls and territory changes must immediately stop new listing/fulfilment activity where the relevant authorization is no longer active.

### Merchant / seller portal

The existing Commerce seller workflow may remain at /merchant-portal and should be named and described as a merchant workspace. It remains responsible for seller listings, variants, inventory adjustments and seller-scoped order lines. It must not acquire brand-owner or distributor privileges merely because a user enters a brand name.

## Tenant and authorization model

Implement a shared organization/membership foundation with typed business relationships, for example:

- business_organizations — legal entity, organization type, verification status, jurisdiction and lifecycle state.
- business_memberships — subject, organization, role, invitation state, granted/revoked timestamps and actor audit.
- brand_accounts — one-to-one or approved many-to-one relation to an organization; verified brand ownership/representation.
- distributor_accounts — verified distributor organization and operational profile.
- brand_distribution_authorizations — brand, distributor, territory, channels, product/SKU scope, contract reference digest, effective/expiry dates and approval status.
- merchant_accounts — a typed merchant principal linked to an organization; migrate the current single-owner merchant record without weakening existing owner checks.
- business_audit_events — append-only evidence of invitations, role changes, verification decisions, authorization grants/revocations and critical commercial mutations.

The exact normalized schema and migration plan must be reviewed before implementation. Existing Commerce rows must be backfilled deterministically; orphaned or ambiguous owner relationships remain REVIEW rather than being assigned to a tenant by guesswork.

Every portal API must derive the active subject from the verified session and resolve an active membership server-side. Never accept organization_id, brand_id, distributor_id, owner IDs or a role from the browser as authorization. Apply tenant predicates to every query and mutation, verify object relationships on nested resources, and return no cross-tenant identifiers in errors. Role checks alone are insufficient without tenant membership and resource-scope checks.

## Data and reporting rules

- Catalog owns canonical product facts; Commerce owns merchant offers, variants, stock, orders, refunds and payment events.
- CIL owns source rights and evidence assessments. CAL remains the final product-display authority.
- A distributor cannot alter a brand's claims or evidence. A brand cannot alter a distributor's stock, shipment or settlement records.
- Price, tax, FX, shipping, landed cost, inventory and fulfilment dashboards must use timestamped provider-backed records. Unknown or stale components are displayed as unavailable, not estimated as facts.
- Reports must identify aggregation windows, currencies, tax/fulfilment inclusions, data freshness and missing providers.
- Personal customer data is not exposed to brands or distributors by default. Any permitted aggregate must meet privacy thresholds and documented purpose.

## Release acceptance

Do not mark REL-19 passed until automated and staging evidence proves:

1. Brand, distributor and merchant principals are separate and can be linked only through approved, auditable relationships.
2. Cross-tenant read/write tests cover every portal route, nested object and report.
3. Invitation acceptance, role elevation, suspension, revocation and contract expiry take effect immediately.
4. A distributor cannot create or fulfil an offer outside an active brand/territory/SKU authorization.
5. A brand cannot inspect another brand's assets, evidence, merchant economics or customer-level data.
6. Inventory, offer, order, fulfilment and settlement metrics are computed from durable service events and reconciled to source records.
7. Managed database backup/restore and tenant-bound migration rollback are exercised in staging.
8. Independent security review signs off the tenant isolation model and audit trail.

## Current implementation inventory

- Commerce has a Merchant entity keyed by one owner_user_id, merchant applications, market activation, listings, variants, inventory and seller-scoped orders.
- BFF serves /brand-portal; that page currently runs the merchant/seller workflow and stores its session token in page memory.
- There is no dedicated Brand entity, distributor entity, distributor authorization graph, distributor API route or /distributor-portal page.
- No production tenant isolation or dashboard analytics claim should be made for brand/distributor principals until the data model, APIs, pages and cross-tenant tests above exist.
