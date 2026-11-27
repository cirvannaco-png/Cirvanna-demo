# Brand subscription billing — phase-one contract

**Status: architecture decision recorded; implementation and acceptance remain incomplete.**

## Commercial decision

Cirvanna's initial brand monetization model is one flat-rate, recurring monthly subscription paid by each approved brand for access to the platform.

- One monthly recurring price for phase one; not per-seat, metered or volume-based.
- Stripe-hosted Checkout (subscription mode) and Stripe Customer Portal.
- Price ID and currency are server-side configuration; the browser must never choose a Stripe Price ID.
- Amount, currency, billing start date, cancellation policy and grace-period duration remain unapproved configuration decisions. Do not invent them.
- Future price increases or tiers use a versioned plan catalogue and explicit subscription updates with customer notice and a deliberate proration policy. Existing subscriptions must not silently change price.

## Scope and tax boundary

This is a platform-access subscription, not tax on merchandise and not a commission on buyer transactions.

- Do not enable Stripe Tax or automatic tax collection for this phase without a separate legal/tax decision.
- Do not add buyer product tax or seller merchandise tax to this subscription.
- Do not infer that Cirvanna has no tax obligations on its own subscription revenue. Those depend on its legal establishment and registration obligations and require qualified tax advice before production billing.

The existing Commerce order-payment flow separately calculates a seller commission. This design does not silently change it. Before production launch, the commercial owner must decide whether order-level commissions are removed, retained in addition to the subscription, or disabled for subscribed brands. Do not hide or double-collect fees.

## Identity and tenant boundary

The current `/brand-portal` is a merchant/seller workspace backed by the single-owner Commerce Merchant record. It is not a verified Brand tenant. `docs/architecture/brand-and-distributor-portals.md` requires distinct Brand, Distributor and Merchant principals, organization membership and tenant-scoped authorization.

1. Do not attach a brand subscription to `Merchant.id` or `owner_user_id` as a shortcut.
2. Implement the approved business-organization and membership model first, or a reviewed phase-one subset preserving its migration path.
3. A subscription belongs to one verified Brand account, not an arbitrary user-supplied brand name.
4. The server derives the authenticated subject and active Brand membership. Browser-supplied brand IDs are selectors, never authorization.
5. Membership suspension/revocation blocks billing management immediately without deleting financial history.

## Proposed Stripe lifecycle

Use Stripe Billing with hosted Checkout in `subscription` mode and one configured monthly Price ID.

- Create/reuse one Stripe Customer per Brand account under a unique constraint.
- Permit checkout only for an approved Brand and an authorized active member.
- Bind Stripe Customer, Brand and Subscription IDs with server-generated metadata; verify all mappings on every webhook.
- Use stable idempotency keys per Brand and checkout attempt.
- Expose Customer Portal sessions only to authorized Brand members.
- Store a durable local subscription projection. A browser redirect never activates paid entitlements.
- Update entitlements only from verified, signature-checked webhook events; reconcile ambiguous and out-of-order events against Stripe.
- Handle `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed` and `invoice.payment_action_required`.
- Persist Stripe event IDs under a unique constraint. Duplicate deliveries must be harmless. Validate account context, `livemode`, customer, subscription, Brand metadata, Price ID and currency.
- Define a configurable failed-payment/grace-period policy before launch; never guess it.
- Default cancellation to cancel-at-period-end unless explicitly changed. Preserve access through the paid-through timestamp, then revoke only brand-paid entitlements.
- Reconcile subscriptions, invoices and cancellations periodically; webhooks alone are not an accounting ledger.

## Configuration contract

Provision only through the deployment secret/configuration manager:

- `STRIPE_SECRET_KEY`: test-mode secret in staging.
- `STRIPE_WEBHOOK_SECRET`: signing secret for a dedicated staging endpoint.
- `STRIPE_BRAND_MONTHLY_PRICE_ID`: the approved recurring monthly Price.
- `STRIPE_BRAND_SUCCESS_URL` and `STRIPE_BRAND_CANCEL_URL`: HTTPS return routes.
- `STRIPE_BRAND_BILLING_ENABLED`: explicit kill switch, default false until webhook and entitlement checks pass.

Staging must reject live-mode keys and live-mode events. Use only the Cirvanna sandbox Stripe account. Never use live mode.

## Acceptance tests

Before real brand billing, prove:

1. Non-brand users cannot create or manage a Brand subscription.
2. Pending, rejected and suspended Brands cannot start checkout.
3. One approved Brand maps to exactly one Stripe Customer and at most one active subscription.
4. Only a verified webhook for the matching Brand activates its entitlement.
5. Browser return without a verified webhook does not activate paid access.
6. Invalid signature, wrong Stripe account, wrong `livemode`, mismatched Brand metadata, wrong Price ID and wrong currency are rejected.
7. Duplicate, delayed, reordered and replayed events do not duplicate or regress state.
8. Failed payment, action-required, cancellation, paid-through expiry and recovery follow the approved policy.
9. One Brand cannot read or manage another Brand's billing or portal session.
10. Portal sessions are server-generated and restricted to the mapped Stripe Customer.
11. Amount and currency match the owner's approved configuration.
12. Checkout, invoice and subscription reconciliation is repeatable and auditable.
13. No buyer merchandise tax or unapproved seller commission is added to the subscription line item.
14. All staging tests use `livemode=false`; no production key or live payment is used.

## Explicit blockers

- Brand organization/membership entities and APIs do not yet exist; the current portal is a merchant workspace.
- Monthly amount and currency are unspecified. Do not create a Stripe Product/Price or Checkout Session yet.
- Tax treatment of Cirvanna's own subscription revenue is not legally established.
- Existing order-level commission policy needs an explicit commercial decision.
- No deployed staging webhook URL or dedicated signing secret is verified.
- No brand subscription checkout, webhook, entitlement, cancellation, dunning or reconciliation acceptance test has run.

Until these blockers are cleared, describe brand subscriptions as designed, not implemented or accepting payments.
