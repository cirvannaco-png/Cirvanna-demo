# Cirvanna system readiness and quality architecture

**Review date:** 9 November 2026  
**Repository:** `cirvannaco-png/Cirvanna-demo`  
**Production status:** BLOCKED. This document is an engineering gap register and acceptance contract, not evidence that the listed providers or deployment are live.

## Executive position

Cirvanna has substantial domain contracts and service code, but the system is not yet a verified integrated product. The next engineering work must connect canonical owners, providers, persistence, deployment, and measurable quality into complete user journeys.

PR #180 is merged. PR #181 is merged into current `main` and establishes Commerce schema revision `20261109_0007` for merchant home/legal country separation, source-price provenance, operating-market and quote/capability evidence tables. It does **not** activate markets, connect FX/tax/fulfilment providers, or implement the full comparison/checkout path.

PR #102's implementation is being ported on a branch based on the current-main integration point. Its old migration identifiers `20261105_0004` and `20261105_0005` are not reused; the port creates `20261109_0008` after `20261109_0007`. The port also tightens tax quotes to an exact destination zone and permits comparisons across different offer currencies only when fresh FX converts each cost component to one requested display currency. Exact-head Commerce, BFF, portal, migration-upgrade and integration checks remain required before merge.

PR #84 and PR #62 also require current-main reconciliation. Their historical green/failing checks are not evidence about a rebuilt candidate. Click It remains disabled.

## Canonical dependency and authority map

| Concern | Canonical owner / source | Dependent flow | Required evidence before release |
|---|---|---|---|
| Product identity and facts | Catalog | All marketplace discovery and comparison | Canonical product and cross-merchant variant identity, attribute provenance/version, real PostgreSQL migration and restore |
| Offers, stock, price and checkout | Commerce | Marketplace BFF, comparison, checkout | Approved merchant, stock invariants, exact variant, durable order/payment state, Stripe test-mode webhook reconciliation |
| User identity and consent | Commerce OIDC subject binding plus Identity Learning / Privacy Governance purpose receipts | Gateway, Wardrobe, Twin, Look It, Click It | Real issuer/audience/JWKS, session lifecycle, scoped consent, revocation and deletion propagation |
| Positive preferences | USI / Identity Learning | Gateway and PNELLY context | Consent, versioned event provenance, export/correction/deletion and durable operation |
| Negative preferences | NPL | CAL and ranking | User-owned active declarations, signed candidate binding, corrections and hard-veto regression |
| Cultural requirements | Cultural Identity | CAL and ranking | Explicit user declarations, signed candidate-bound evidence, no inferred sensitive identity |
| Final display decision | CaTaCaCi / CAL | Every candidate/product detail display path | Sole SHOW authority, durable versioned receipt before release, no REVIEW/BLOCK detail leakage |
| Fit prediction | FCI package and an independently operated provider | CAL fit signal | Trained predictor, observed fit labels, temporal and subject-disjoint holdouts, calibration, subgroup/market analysis, signed model/report provenance |
| Product recommendation | PNELLY / Complementer advisory and ranking components | User shortlist and look composition | Shared benchmark, blinded human relevance, model-specific calibration, hard-constraint safety and randomized exposure data |
| Media processing / publication | Privacy Governance, Vision attestation and Content Lifecycle | Click It, Look It, public profiles/media and shared links | Purpose consent, jurisdiction policy, full-face masking, immutable asset digest, human review, quarantine/delete propagation, route coverage |
| Multi-market commerce | Commerce plus canonical Catalog identity | Marketplace offer search/comparison/checkout | Explicit operating market, source/payable/display currencies, fresh FX/fulfilment/tax/payment evidence, same-variant comparison and checkout revalidation |

**Authority rule:** advisory models may propose or rank candidates; they cannot create product truth, bypass NPL/cultural/safety/legal requirements, or make a CAL verdict. Only CAL SHOW authorizes display. A successful checkout is a separate Commerce authorization, inventory and payment decision.

## Workstream 1 — FCI must become empirically predictive

**Current state:** FCI contains typed estimate contracts, evidence coverage and offline calibration metrics. There is no trained production fit predictor, no registered inference provider and no empirical calibration release. Evidence coverage alone is not fit prediction. A signed estimate proves key provenance, not predictive validity.

**Implemented foundation in this work:** an offline predictive release validator that requires model and dataset digests, a subject-disjoint evaluation cohort, predictions strictly after a declared training cutoff, outcomes observed after predictions, minimum sample/subject/high-confidence counts, predeclared market/category slices, Brier score, expected calibration error, ROC AUC and high-confidence failure rate. It distinguishes inconclusive, rejected and candidate-pass outcomes.

**Remaining work:**
1. Define the fit outcome precisely: successful size/fit confirmation, exchange/return reason verified as fit-related, user-reported fit result, or a separately labelled evaluator outcome. Never silently combine unrelated return reasons or treat non-purchase as fit failure.
2. Acquire a licensed, consented, representative dataset with product size charts, user-declared measurements where justified, garment construction/stretch/material, category and actual outcomes. Keep direct identifiers and raw media outside the evaluation repository.
3. Freeze feature definitions, missingness semantics, model family, training cutoff, calibration policy and subgroup/slice plan before evaluating.
4. Train candidate models and compare against an interpretable baseline using rolling temporal holdouts and subject-disjoint tests. Keep calibration data separate from final holdout data.
5. Evaluate discrimination, Brier score, ECE/reliability curves, interval coverage, uncertainty, confidence-stratified failure, market/category slices, sample sizes and confidence intervals. Examine measurement error, selection bias, label quality and subgroup performance.
6. Pin model and dataset hashes, signed validation report, code/dependency versions, feature schema, calibration version, reviewer sign-off and rollback threshold. Register a provider only after independent validation and staging integration.

Until that work is complete, FCI remains UNKNOWN for production and CAL must continue to route candidates to REVIEW. Do not manufacture fit scores, set `calibrated=true` based on coverage, or ship the test fixtures as a model.

## Workstream 2 — operational infrastructure is not complete

A repository that builds containers is not an operating system. The production baseline still needs:

- Approved deployment workspace/platform, region, cost owner, service/database IDs, network boundaries and secret-manager configuration.
- Managed PostgreSQL for each canonical data owner, reviewed migration execution, encrypted backups, isolated restore drills and documented RPO/RTO.
- Real identity-provider configuration and browser sign-in/refresh/logout; no shopper-pasted JWT workflow.
- Stripe test-mode checkout, webhook signature/replay/idempotency and reconciliation.
- Authenticated provider readiness plus operation-specific staging tests for FX, tax, fulfilment, privacy, safety and FCI.
- Central logs, metrics and traces with PII/image redaction; dashboards, error/latency alerts, on-call ownership and incident escalation.
- Rate limits, secret rotation, SLOs, dependency failure exercises, rollback/restore drills, support/refund/returns and fulfilment/tax operating procedures.

Readiness endpoints are necessary but insufficient. For every dependency, prove one successful operation and the expected fail-closed behavior when it is unavailable, stale, invalid or unauthorized.

## Workstream 3 — one canonical system deployment

The new `infrastructure/deployment/canonical-stack.json` is the single provider-neutral inventory for service ownership, exposure, build context, dependencies, data stores, external providers and release gates. It is validated by `scripts/validate_canonical_stack.py`.

It is **not** an executable deployment or production certification. The production platform is not selected in the repository, and several runtime services still lack verified container-build workflows. The next deployment stage must derive its provider-specific implementation from this inventory and produce one release record bound to:
- the exact full Git commit and immutable image digests for every deployed service;
- a complete service/dependency graph and private/public network policy;
- every migration and schema revision applied;
- managed data-store IDs, backup/restore evidence, RPO/RTO and recovery owner;
- secret references and rotation owners (never secret values);
- provider versions/readiness evidence, dashboard/alert links, on-call and rollback plans.

No service is production-enabled by this inventory. Do not claim that a single deployment exists until the entire required graph is deployed and the same candidate commit passes end-to-end staging.

## Workstream 4 — decision quality monitoring

An offline CAL quality aggregation contract is added under the canonical CaTaCaCi package. It separates:
- verdict distribution (SHOW/BLOCK/REVIEW);
- any displayed non-SHOW candidate (critical policy leak);
- missing required evidence and provider failure rates;
- actual later-observed fit outcomes and their Brier/high-confidence failure rates;
- policy versions represented in the observation window.

**Still missing:** serving-path event instrumentation, durable full decision receipts, managed storage, trace correlation, dashboards, alert thresholds, paging ownership, retention/deletion and replay. The current gateway's development SQLite audit is not a production decision-quality store.

Before launch, persist a minimal, versioned decision receipt before releasing any candidate. It should identify request/opaque decision IDs, exact candidate and Catalog version, CAL verdict/reasons, policy/contract/model/provider versions, timestamps and evidence references/hashes. Do not store raw images or unnecessary measurements. Add alerts for any non-SHOW display, missing receipts, stale/unknown mandatory evidence, provider failure spikes, latency, verdict distribution shifts, calibration drift and sudden changes in human-reviewed fit outcomes. Track delayed outcomes only when genuinely observed; do not infer them from absence of a purchase.

## Workstream 5 — inter-model recommendation calibration

PNELLY, Complementer, the deterministic baseline and any later ranker must be evaluated on the same frozen candidate pools and declared contexts. Their raw scores are not on a common probability scale and must not be compared, averaged or blended as though they were calibrated.

Required protocol:
1. Freeze identical candidate slates, market/category/context, product facts and hard constraints for every model.
2. Produce independent blinded human relevance reviews for every candidate; use a third independent adjudicator for disagreements. Keep a human-reviewed dataset out of Git.
3. Split calibration and final evaluation by participant and time. Never fit score calibration on the same holdout used for final claims.
4. Calibrate each model's raw scores to the same declared relevance target using only its calibration split. Report model-specific calibration version and dataset hash.
5. On the untouched holdout, compare nDCG@k, pairwise ranking quality, Brier/ECE for calibrated relevance probabilities, diversity, coverage/no-result rate, top-k fill, and per-market/category uncertainty.
6. Measure explicit approvals, edits, rejections and repeated rejections only from real consented exposures. Separate randomized cohort arms. Report uncertainty intervals and sample counts.
7. A hard-exclusion violation is a hard release failure and cannot be compensated by relevance, engagement or retention. CAL remains downstream and independent.

The existing PNELLY human-evaluation tool compares Cirvanna ranking with a deterministic baseline, but its reviewed dataset is empty and real exposure telemetry/randomized assignment are not operational. There is therefore no current inter-model calibration or measured recommendation uplift.

## Workstream 6 — Click It privacy, rights and child safeguards

Click It stays disabled. PR #182 adds BFF consent/revocation and photographed-person rights routes but does not enable photo upload or processing. Its external privacy providers and full publication path still require current-main verification and real staging evidence.

Enablement requires all of the following:
- Authenticated Commerce subject and purpose-bound image-processing/Click It consent; revocation blocks further processing and is propagated.
- No facial recognition, identity search, embeddings, age estimation or sensitive-trait inference. Face detection exists only to locate regions to mask.
- Approved, licensed, pinned masking detector; every visible face masked before embedding, retrieval or downstream processing; uncertain/missing/failed detector means block.
- No original-photo retention by default; documented minimal retention exceptions, consent receipts, expiry/purge, export/deletion and auditable proof across source, derived assets, replicas, caches and CDN.
- Trusted jurisdiction resolution and signed, current policy; legal basis and cross-border transfer decisions are not user-supplied hints.
- Rights request, urgent quarantine/unpublish, private status, independently verified requester authority, reviewer workflow and tracked completion.
- For declared minors: no Twin/wardrobe/personalization or behavioural learning, no public face reveal/sharing, and guardian verification when applicable. A checkbox is not guardian verification.
- Complete route inventory covering publish, restore, syndication, media serving, signed URLs, CDN/cache and shared-link activation; every binary public path must verify the same immutable asset digest and current masking/human-review attestation.

Provider `/ready` probes alone do not establish operation. Test real grant/revoke, jurisdiction evaluation, detector output, asset masking, quarantine, unpublish, delete propagation, rights review and every delivery path in staging. Unknown or unsupported jurisdictions and provider outages block the feature.

## Workstream 7 — multi-market marketplace (#102)

Current main has the schema foundation from #181. The current integration port adds revision `20261109_0008` chained after `20261109_0007`; it does not replay the old #102 migration files. The offer-comparison contract now permits different source offer currencies when current FX quotes are available for every component and requires exact canonical Catalog product/variant identity plus destination-zone tax evidence.

The integrated offer contract must preserve:
- brand-home country separately from legal entity country;
- source product price/currency separately from merchant payable offer price/transaction currency;
- market-country operating capability, merchant locale and consumer display currency;
- provider-sourced, fresh FX, fulfilment, authoritative tax and payment-capability evidence with provider IDs, timestamps and expiries;
- distinct shipping, courier, merchant delivery, collection and local transport semantics, including per-unit versus per-quote charging;
- exact canonical Catalog product/variant identity across merchants and markets;
- same-variant, same-source-currency like-for-like comparison; missing, stale or mismatched evidence returns unavailable rather than a guessed total;
- tax inclusion/exclusion without double counting; provider/quote provenance in consumer comparison;
- checkout-time revalidation, consistent total/payment/webhook amounts, idempotency and reservation expiry bounded by quote expiry.

Thirty kilometres remains the default local radius, with explicit user expansion. A new market remains pending until current payment, tax and fulfilment capability evidence is verified. No FX/tax/fulfilment provider is configured by the schema alone.

## Integration order and release gates

1. Complete the PR #102 port against current main and run upgrade-from-current-schema migration, Commerce, BFF, portal, offer comparison, checkout and container tests.
2. Integrate and verify real provider contracts, preserving unavailable responses until evidence is current and authoritative.
3. Reconcile PR #84: preserve PNELLY Look It as a separate conversational discovery path; do not route Look It through Click It; keep real Twin/Try-On/FCI capabilities unavailable until validated providers exist.
4. Reconcile PR #62 against the current Catalog, Commerce, BFF, and CAL architecture. Exercise every display route, cache, saved/cart path and checkout-time revalidation, including missing/stale/unsigned/tampered/foreign-subject/foreign-candidate evidence.
5. Complete FCI predictive validation, privacy operations, decision quality monitoring, inter-model calibration and canonical deployment evidence.
6. Only then consider a scoped staging pilot. Production readiness remains blocked while any required release gate lacks exact-commit evidence and accountable review.

## Non-negotiable engineering rules

- Merge only branches based on current main with one authoritative migration chain.
- A green historical workflow is not current integration evidence.
- No new owner for product truth, identity, consent, hard exclusions, fit validation, or CAL.
- No mock, fixture, heuristic, schema row, endpoint probe or provider-configured flag is described as live operation.
- Missing, stale, uncertain, conflicting or untrusted evidence fails closed.
- Do not merge a PR merely to make a milestone appear complete. A working, integrated, measurable system is the goal.
