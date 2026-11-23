# CAL shopper-surface acceptance matrix — 22 November 2026

**Scope:** Code-level route and contract evidence for issue [#237](https://github.com/cirvannaco-png/Cirvanna-demo/issues/237).

**Release posture:** Code-level tests cover the primary shopper surfaces, but the full cross-surface adversarial release matrix is **not complete**. No deployed CDN/cache purge, real identity-provider revocation, or live merchant-provider state-transition run is claimed here. This document is an evidence index, not a production certification.

## Evidence legend

- **Code/CI covered:** a focused regression test exists and has passed in the current mainline test/CI evidence.
- **Constrained by design:** the surface is intentionally non-publishing or unavailable until its provider gate is released.
- **Deployment proof missing:** source and mocked tests cannot prove the live CDN, identity provider, Catalog or merchant-provider behavior.

## Surface-by-surface evidence

| Shopper surface | Current boundary | Representative regression evidence | Remaining proof |
|---|---|---|---|
| Marketplace browse | Product/offer details are returned only from authenticated Gateway discovery with candidate-bound CAL SHOW, exact Catalog version and CIL eligibility. | test_marketplace_offers_use_authenticated_gateway_cal_show_only; test_marketplace_offers_rejects_unbound_or_cil_ineligible_cal_decisions; test_api_error_responses_are_never_cacheable | Run the same mapped/unmapped, suspended, stale-stock, disconnected, deleted and revoked-market fixtures against the deployed route and its caches. |
| PNELLY conversational discovery | Delegates to the wardrobe/CAL discovery pipeline; a conversation or image retrieval is not itself a display authorization. | test_marketplace_pnelly_search_uses_wardrobe_cil_path_and_complementer_advisory; test_pnelly_conversational_discovery_delegates_to_wardrobe_cal_pipeline | Prove current policy and provider state are refreshed across all operating markets in the deployed topology. |
| Wardrobe recommendations | Verified subject, consent and candidate/product/Catalog binding are required before recommendation serialization. | test_wardrobe_recommendations_forward_verified_token_to_cal_decision_gateway; test_wardrobe_recommendations_reject_candidate_id_mismatch_before_display; test_wardrobe_recommendations_block_revoked_conversation_before_gateway | Exercise consent revocation and market/merchant status transitions through the real identity and CAL services. |
| Look It | Image retrieval returns bounded outfit-component descriptions and counts with PENDING_CAL; it does not publish Catalog product, merchant, variant or price details. Request-scoped consent is verified and revoked. | test_look_it_records_verifies_and_revokes_request_scoped_consent; test_look_it_suppresses_results_when_consent_revocation_fails; test_look_it_requires_both_consents_before_identity_consent_or_pnelly_calls | Independently inspect storage, logs, tracing and deployed upload paths to prove no original-photo retention or downstream product display bypass. |
| Click It | Public upload/search is blocked before multipart parsing and before the photo is read or forwarded. | test_click_it_fails_closed_before_reading_or_forwarding_the_uploaded_photo; test_click_it_rejects_before_multipart_form_parser_is_invoked; test_click_it_fails_closed_for_every_upload_type_without_content_inspection | Keep disabled until the masking/publication-attestation pipeline, fail-closed uncertainty behavior, reporting/removal and child protections are independently verified. |
| PNELLY daily looks | Uses the verified customer's own wardrobe; the result is not an external Catalog product feed and explicitly remains outside CAL product-display authorization. | test_pnelly_daily_looks_uses_verified_wardrobe_and_gateway_subject; test_pnelly_daily_looks_rejects_cross_subject_wardrobe_data; test_pnelly_daily_looks_rejects_gateway_response_with_missing_or_reordered_roles | Validate persistent rotation, real wardrobe ownership and production session/consent behavior; do not treat these looks as purchasable product recommendations. |
| Saved products | Listing and save mutation expose canonical product identifiers, not product names/details without a fresh CAL decision. | test_saved_products_are_persistent_and_validate_canonical_catalog; PR #299 removed the ungoverned product_name from the save mutation response. | Confirm no alternate saved-list/export route serializes product details without current display authorization. |
| Product comparison | Comparison is fail-closed without a candidate-bound CAL receipt and does not contact Commerce before authorization. | test_offer_comparison_fails_closed_without_candidate_bound_cal_receipt; test_offer_comparison_never_contacts_commerce_without_cal_authorization | Test cross-market FX, merchant disconnection and stale offer state on deployed provider-backed data. |
| Cart and checkout | Purchase authorization is separate from display authorization. Exact signed offer/subject receipts, expiry and quote revalidation are required; a prior display SHOW is not reused as purchase authorization. | test_cart_add_blocks_and_audits_non_show_purchase_decision; test_checkout_cal_review_creates_no_order_or_stock_reservation; test_checkout_rejects_expired_cal_receipt_and_persists_denial_audit; test_checkout_rejects_offer_change_during_cal_roundtrip_and_keeps_audit; test_existing_idempotent_order_without_cal_audit_cannot_reopen_payment | Run live payment-provider and merchant-provider scenarios, including revocation during checkout and post-payment fulfilment failure. |
| Browser cache/session handoff | BFF/Gateway API responses are no-store; Marketplace fetches use no-store and account switches clear old products/cart and reject late responses. | test_api_error_responses_are_never_cacheable; test_account_switch_immediately_hides_old_products_and_ignores_late_old_session_response; test_discovery_returns_only_products_authorized_by_cal; test_discovery_fails_closed_when_verified_identity_is_disabled. | CDN purge, reverse-proxy behavior, browser back-forward cache, multi-tab logout and live identity-provider revocation remain unverified. |

## Cross-surface scenarios still missing as one release matrix

The individual tests above are not one correlated end-to-end test across every route. Issue #237 remains open until the same scenario set is run across Marketplace browse, PNELLY, Look It, Click It, Wardrobe, saved products, comparison, cart and checkout:

1. Mapped and approved merchant/product/variant.
2. Unmapped product or variant; no candidate may be displayed.
3. Suspended or revoked merchant/market; all display and purchase surfaces must suppress.
4. Stale stock, stale price or changed offer; no display/purchase based on an obsolete snapshot.
5. Disconnected, deleted or reauthorized merchant account; cached and saved references must not revive an unavailable offer.
6. Consent revocation and user-session switch while requests are in flight; no stale response or prior-account state may reappear.
7. Cache/CDN hit after revocation; no previously cached product detail may be served.
8. Payment race after display revocation; checkout must reauthorize independently and compensation must remain idempotent.

For every case, retain the exact candidate ID, Catalog version, market/context, CAL decision ID and policy versions in restricted audit evidence; do not expose raw policy evidence or withheld candidate IDs to the shopper. Record deployed request/trace IDs and provider state snapshots for independent review.

## Closure criteria for issue #237

- Every shopper surface is enumerated and has an explicit allow/deny boundary.
- The complete scenario matrix passes on an exact release candidate against real deployed identity, CAL, Catalog, CDN/cache and merchant-provider dependencies.
- Cache purge and revocation propagation are measured, not inferred from response headers.
- Click It remains disabled until privacy and publication proof is independently signed.
- An independent reviewer verifies no product details escape through an ungoverned route.

Until those criteria are evidenced, CAL is **implemented and locally tested, but not independently production-certified**.


## 2026-11-23 unified staging execution harness

The executable black-box runner is `tools/cal_staging_matrix/run.py`. It requires a dedicated staging fixture-control plane and configured HTTPS endpoints for all ten shopper surfaces: Marketplace, PNELLY, Wardrobe, Look It, Click It, saved products, comparison, cart, checkout and PNELLY daily looks. Required adversarial scenarios are mapped/approved, unmapped, merchant suspended, stale offer, merchant disconnected, consent/session revoked, cache after revocation, and payment-revocation race. The consent and payment scenarios race live shopper requests against the revocation operation and then replay every surface. The runner refuses partial manifests and writes a redacted evidence report.

The Click It privacy tools are `tools/click_it_privacy_eval/score.py` (independent annotation metrics with per-stratum FNR confidence bounds) and `tools/click_it_privacy_eval/rights_smoke.py` (deployed staging photographed-person report/removal intake and quarantine/status checks). These tools are harnesses, not test evidence.

**Execution status: BLOCKED — no Cirvanna staging service URLs or fixture-control endpoint are available.** Supabase `cirvanna-staging` is active, but its identity/Twin/Auth-private tables currently contain zero rows and there are no Edge Functions. Neither connected Render workspace has a Cirvanna service or Cirvanna Postgres instance. The public Click It BFF upload remains blocked before multipart parsing. No live CAL matrix, consent/CDN revocation, rights-provider, masking dataset, merchant or payment-provider run is claimed.
