# Cirvanna brand subscription billing

**Initial commercial model:** one flat-rate monthly subscription paid by each brand to Cirvanna for platform access. There are no subscription tiers, seat multipliers, usage charges, marketplace commissions, or per-order fees in this initial model.

**Implementation status:** architecture decision recorded; Stripe objects, application integration, deployed webhook, and end-to-end acceptance are not yet complete. This document is not evidence of a live billing integration.

## 1. Product boundary

- A brand is the billing customer. Its authorized billing owner initiates checkout and manages the subscription.
- The subscription buys access to Cirvanna's brand-platform features. It does not purchase marketplace inventory or settle a buyer's order.
- Buyers continue to pay merchants for products through the separate Commerce checkout flow.
- Cirvanna does not collect tax on merchants' merchandise sales through this subscription integration.
- Do not infer that Cirvanna's own subscription revenue is tax-exempt. Any tax treatment applicable to Cirvanna's platform fee requires a separate legal/accounting determination before automatic tax is enabled.
- Do not introduce seller payouts, marketplace split payments, or transaction commissions as part of this billing feature.

## 2. Initial pricing contract

Use exactly one active recurring monthly Stripe Price for the initial launch.

- The Stripe Product represents **Cirvanna Brand Platform Access**.
- The Price is recurring with interval `month`, fixed amount and one currency.
- Price ID, amount, currency, effective date and product ID are configuration/data, never source-code constants.
- Do not create a live-mode Product or Price during development.
- Do not create a sandbox Price until the founder has approved the amount and currency.
- Do not invent a trial, introductory discount, seat quantity, metered usage, proration policy or grace period. These require explicit product decisions.
- A future price increase must create a new immutable Stripe Price and explicitly migrate subscriptions under a reviewed policy; never mutate an existing price in place.
- Keep tiering and threshold-based expansion out of the initial UI. Record a future plan/entitlement version boundary so additional tiers can be added without changing the buyer Commerce model.

## 3. Stripe integration boundary

Use Stripe Billing in the Cirvanna sandbox account only while implementing and validating this feature. Every sandbox API call must explicitly use `livemode=false` and the approved Cirvanna sandbox account context. No live-mode calls or live credentials are permitted in development or acceptance.

Expected flow:

1. An authenticated brand billing owner requests subscription checkout from the brand portal.
2. The server resolves the brand from the verified session and checks that the actor has billing-owner authority. Never accept a browser-supplied brand ID as proof of ownership.
3. The server loads the currently approved monthly Price ID from server-side configuration and creates/reuses a Stripe Customer mapped to that brand.
4. The server creates a hosted Stripe Checkout Session in `subscription` mode with a stable idempotency key, the approved Price ID and opaque brand/subscription correlation metadata. The server returns only the validated Stripe-hosted URL.
5. The browser redirects to Stripe Checkout. A success redirect is informational only; it must not grant brand entitlements.
6. Stripe sends signed events to a dedicated subscription webhook route. The handler verifies the raw-body signature and timestamp, validates the account/mode and customer/subscription mapping, deduplicates the event ID, and persists the event/state transition transactionally.
7. Entitlements are derived from the verified persisted subscription state, not from the Checkout redirect, client state or an unverified Stripe response.
8. The brand portal opens Stripe Customer Portal for payment-method updates and cancellation. Portal configuration and cancellation-at-period-end behavior must be explicitly approved before enablement.

Do not reuse the buyer-order webhook's order settlement semantics as a substitute for subscription lifecycle handling. A paid buyer order does not activate a brand subscription, and a brand subscription event must never mark an order paid.

## 4. Subscription state and entitlements

Persist a single canonical mapping between Cirvanna brand ID, Stripe customer ID and Stripe subscription ID. Enforce uniqueness and owner scoping. Keep an append-only provider-event/idempotency record.

The entitlement evaluator must handle at least:

- `incomplete` / `incomplete_expired`: no paid subscription entitlement;
- `trialing`: unsupported in the initial offer unless a trial is explicitly approved;
- `active`: eligible for paid brand-platform entitlements after the verified invoice/payment policy passes;
- `past_due`: apply only an explicitly approved recovery/grace policy; do not silently grant indefinite access;
- `unpaid` / `canceled`: revoke paid entitlements according to the persisted effective time;
- `paused`: no entitlement unless a future product policy says otherwise.

Process subscription creation/update/deletion and invoice payment success/failure events. Handle out-of-order delivery by retrieving/reconciling the current subscription from Stripe when event ordering is ambiguous. Duplicate delivery must be harmless. Event IDs, provider account, livemode, object IDs and event timestamps must be persisted for audit.

The exact feature entitlement map, grace period, dunning schedule, cancellation timing, refund policy and access after cancellation remain product decisions; do not guess them in code.

## 5. Security and operational requirements

- Dedicated server-side Stripe secret and webhook signing secret stored only in the deployment secret manager.
- Verify webhook signatures against the exact raw request body; reject missing, invalid, stale or wrong-account/mode events.
- Enforce brand billing-owner authorization and prevent cross-brand Customer/Subscription ID substitution.
- Use stable idempotency keys for Customer and Checkout Session creation; persist request intent before provider calls to recover safely from ambiguous timeouts.
- Validate return URLs against configured Cirvanna origins. Never trust arbitrary redirect URLs.
- Never log secret keys, full payment details, webhook secrets or unnecessary personal data.
- Add structured audit events for checkout requested, session created, subscription activated, payment failed, cancellation requested/effective, and entitlement changes.
- Reconcile local active subscriptions against Stripe on a scheduled, bounded job; alert on orphaned, mismatched or stale mappings.
- Keep the brand portal honest: show pending/unknown states as pending, not paid.

## 6. Tax boundary

The initial subscription integration must not enable Stripe Tax or add tax line items by assumption. Cirvanna has stated that it does not collect tax on merchants' product sales. This does not establish the legal tax treatment of Cirvanna's own subscription revenue. Before enabling any tax calculation on subscription fees, obtain the applicable registered-entity, nexus/registration and invoicing decisions from the business's tax adviser. Do not fabricate a tax registration or head-office address in Stripe.

## 7. Acceptance gates

### Code and contract
- [ ] Brand billing owner authorization is derived from the verified session and brand membership.
- [ ] A single approved monthly Price is configured server-side; no amount/currency is hardcoded.
- [ ] Checkout is subscription mode and cannot create a buyer-order or marketplace-commission charge.
- [ ] Customer Portal actions are restricted to the mapped brand's own Customer.
- [ ] Subscription webhook signature, account/mode, mapping, idempotency, replay, duplicate and out-of-order handling are tested.
- [ ] Entitlement transitions are tested for all supported subscription/invoice states.
- [ ] Browser success/cancel redirects cannot grant or revoke entitlements.
- [ ] No Stripe Tax or merchant merchandise tax is added by this integration.

### Sandbox integration
- [ ] Sandbox Product and monthly Price created only after amount/currency approval.
- [ ] Hosted Checkout completed using Stripe test payment methods.
- [ ] Signed webhook events delivered to a real HTTPS staging endpoint.
- [ ] Invalid signature, duplicate event, replay, delayed/out-of-order event and wrong-mode/account cases rejected or safely deduplicated.
- [ ] Payment failure, cancellation, renewal and portal update tested.
- [ ] Local database state reconciles to Stripe after simulated missed webhook delivery.
- [ ] Test results are tied to exact commit, deployed image digest and sandbox account.

### Release
- [ ] Secrets installed through the approved secret manager; never pasted into source or chat.
- [ ] Database migrations reviewed and applied only through the approved staging migration process.
- [ ] Brand portal shows the actual verified subscription state.
- [ ] Rollback and entitlement-reconciliation procedure rehearsed.
- [ ] Independent security review passes before enabling paid brand access.

## 8. Explicitly out of scope for the first release

- Multiple plans or tiers.
- Threshold-triggered automatic price changes.
- Usage-based or seat-based billing.
- Marketplace commission or seller transaction fees.
- Buyer subscriptions.
- Seller payouts or split payments.
- Cirvanna collecting or remitting tax on merchant product sales.
- Automatic tax on Cirvanna subscription fees before a separate tax determination.
- Production/live-mode Stripe configuration.
