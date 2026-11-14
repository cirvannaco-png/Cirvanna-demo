# Cirvanna release-readiness remediation plan

**Baseline:** `main` at `4e3b5a2ddae3f3386a2f60b320e0911cd330fe29`  
**Plan date:** 2026-11-14  
**Release posture:** BLOCKED. This plan does not change feature flags, provider readiness, release-gate statuses, or production claims.

## Decision summary

The work is split into repository-owned engineering, provider-dependent integration, and independent evidence. A code path, mock, migration, local test, or configured environment variable is not proof that a provider is live or that a production control works.

| Workstream | Current safe posture | Required outcome |
|---|---|---|
| PNELLY + Wardrobe + Complementer | Continue integration on current `main`; PR #197 is not a merge candidate without reconciliation | Authenticated multi-turn discovery, wardrobe-aware recommendations, three daily looks, separately authorized Complementer advice, explicit feedback and deletion |
| Virtual Twin | Generation remains unavailable unless real provider and independent validator are configured | Pinned/licensed full-body mesh generation, exact consent/asset binding, private persistence, repeatable rendering and signed independent validation |
| Marketplace + CAL checkout | Purchase proxy remains off until readiness checks and staging journey pass | CAL authorization for every displayed candidate and purchase mutation; verified quote revalidation, payment and durable reconciliation |
| Merchant + fulfilment | No merchant or fulfilment provider is assumed live | Verified merchant onboarding, market capabilities, inventory, quote, shipment lifecycle, exception handling and settlement/refund procedures |
| Click It | Disabled | Complete image-rights, consent, masking, retention, deletion, publishing and CDN lifecycle; independent privacy verification |
| Production operations | No production deployment is certified by this plan | Exact-commit staging evidence, observability, alert routing, ownership, restore, incident and rollback drills |

## PR reconciliation

- PR #197 (`reconcile/pnelly-complementer-wardrobe-current-main-2026-11-12`) must be treated as a source of candidate changes, not merged wholesale. Current `main` already contains the authenticated Wardrobe conversation and Complementer advisory foundations. Reconcile only missing, non-duplicative behavior onto current `main`; preserve existing subject binding, consent checks, CAL authority and route contracts.
- PR #193 (`feature/bff-cal-purchase-flow-current-main-2026-11-12`) must likewise be reconciled, not merged wholesale. The purchase proxy must remain default-off and fail closed. Do not weaken the Commerce readiness handshake, signed purchase receipt requirement, candidate-bound authorization, identity requirement, or migration checks.
- New changes must be based on current `main`, have focused commits, and pass the exact-head CI suite. Do not force-push or rewrite either draft branch as a shortcut.

## Ordered implementation sequence

### 1. PNELLY, Wardrobe and Complementer

1. Keep one canonical conversational discovery endpoint and one conversation state authority. Do not introduce a second endpoint solely to make PR #197 appear merged.
2. Derive the shopper subject from the verified server-side session. Never accept a subject ID, tenant ID, consent decision, or CAL verdict from browser input as authority.
3. Bind each conversation to its owner, expiry, purpose, and consent state. Enforce per-user isolation, bounded history, reset, export and deletion.
4. Load wardrobe context only for the authenticated subject and only fields authorized for the current purpose. Treat wardrobe data as evidence/context, not permission to bypass CAL.
5. Produce three daily looks only from available wardrobe/catalog facts. Persist rotation state with idempotency; do not fabricate inventory, product availability, body fit, or merchant claims.
6. Call Complementer as an advisory with a separate service identity and explicit request scope. It may return recommendations or uncertainty, but cannot authorize product display, purchase, identity inference, medical diagnosis, or CAL decisions.
7. Record explicit approved/rejected preference feedback only through the correct consented learning path. A click, save, purchase or dwell event is not a suitability label.
8. Add contract tests for owner isolation, expired/revoked consent, missing wardrobe, empty provider response, provider timeout, duplicate feedback, deletion, and CAL denial.

**Acceptance:** a deployed staging test proves registration/session → multi-turn PNELLY conversation → authorized wardrobe context → three explainable looks → optional Complementer advice → explicit feedback → persisted state and deletion. All product candidates remain hidden unless CAL returns SHOW with durable receipt.

### 2. Virtual Twin

1. Keep the current provider-neutral generation contract as a validation boundary, not a claim that a generation provider exists.
2. Select a commercially licensed full-body mesh provider only after privacy, model-use, data-retention, training-use, region, subprocessor and deletion terms are reviewed.
3. Pin model revision and SHA-256; record provider job, source asset IDs, artifact digest and exact consent bundle/version.
4. Generate to private Asset Service storage. Never return public object URLs or persist source images in BFF, logs, analytics or model-provider metadata beyond approved retention.
5. Run an independent validator that is operationally and organizationally separate from the generator. Validate readable artifact, finite geometry, topology, full-body coverage, scale bounds, privacy scan and absence of embedded source-photo pixels.
6. Register the Twin only after generation contract and independent receipt pass. Persist owner, consent, version, status, asset reference and digest in the canonical registry.
7. Render from the private asset under fresh owner/consent authorization. Verify revocation, expiry, deletion, restore and cache invalidation.
8. Test repeated rendering across sessions/devices, asset corruption, provider timeout, validator mismatch, wrong owner, stale consent and delete propagation.

**Acceptance:** real generated mesh bytes, reproducible render, signed independent validation report and exact-head staging evidence. Skeletons, mock meshes, sample assets, registry rows and provider demos do not pass.

### 3. Marketplace and CAL purchase path

1. CAL remains the sole authority for every candidate display and every purchase mutation. REVIEW/BLOCK/missing/malformed/timeout results fail closed.
2. The BFF derives the user from a verified identity session. Browser payloads cannot supply authoritative subject, merchant approval, stock, price, tax, FX, delivery quote or purchase authorization.
3. Persist and bind the CAL receipt to exact candidate/product/variant, user/session, cart mutation, policy and catalog/offer version. Commit the receipt before releasing the protected response.
4. At checkout, revalidate inventory, market eligibility, FX, tax and fulfilment quote freshness. Recompute totals from authoritative server-side amounts; reject currency/amount mismatch.
5. Use Stripe test mode first. Verify idempotency, signature validation, duplicate/replayed events, expiry, failed payment, ambiguous payment and reconciliation. A redirect or checkout-session creation is not payment evidence.
6. Keep `COMMERCE_CAL_PURCHASE_PROXY_ENABLED` false until deployed Commerce readiness and candidate-bound receipt signer checks pass in staging.
7. Do not expose hidden product/merchant/price/stock details before CAL SHOW. Do not interpret an advisory Complementer result as a CAL verdict.

**Acceptance:** staging journey from identity to CAL receipt, cart, checkout, signed provider webhook, durable order/payment/inventory audit, replay handling and reconciliation. Demonstrate both positive and denied/timeout paths.

### 4. Merchant and fulfilment integrations

The system must support real provider adapters, not hard-coded assumptions. The provider-neutral interface and evidence requirements are in [merchant and fulfilment integration contract](../marketplace/merchant-fulfilment-integration-contract.md).

Required live capabilities include merchant legal/KYC status, market eligibility, catalog ownership, inventory freshness, service zones, fulfilment mode, destination-specific quote, amount/currency, quote expiry, shipment events, delivery exceptions, proof of delivery, returns and refund coordination. Provider adapters must identify the provider, provider reference, observed time, expiry, jurisdiction and source evidence. Missing or stale capability means unavailable, not a guessed estimate.

### 5. Click It privacy lifecycle

Click It stays disabled. The existing face detector is a fail-closed component, not a complete privacy lifecycle or proof that every face is detected. A successful detector response does not prove that no unmasked face escaped.

Implement and independently verify the full lifecycle in [Click It privacy verification plan](../privacy/click-it-independent-verification-plan.md). Include every route that can publish, restore, syndicate, share, cache, thumbnail, export, moderate or serve image bytes. Any uncertain masking, consent, rights, deletion or route authorization must prevent downstream release.

### 6. Monitoring and operating procedures

Use [production operations runbook](../operations/production-operations-runbook.md) as the required operational baseline. Before release, name real owners and recipients, configure dashboards and alerts, run restore/failure/rollback exercises, and attach evidence to the exact release commit. Placeholder owners, example alert routes, local logs and synthetic green checks do not satisfy REL-10 or REL-16.

## Release evidence rules

- Keep all currently blocked release gates blocked until evidence exists. Do not convert documentation or mocked tests into PASS.
- Each evidence record must identify exact commit, environment, test/run ID, timestamp, operator/reviewer, artifact digest where applicable, outcome and sanitized evidence reference.
- Never include access tokens, customer images, raw personal data, private keys or payment secrets in evidence.
- Provider readiness must be demonstrated by authenticated provider health/capability checks and a successful real staging transaction or lifecycle exercise.
- Independent verification must be performed by a reviewer who did not implement the control, against the deployed release candidate.
- Feature flags remain off for Click It and purchase proxy until all their dependent gates pass.
