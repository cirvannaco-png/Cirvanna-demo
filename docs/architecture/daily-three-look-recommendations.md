# PNELLY Daily Three-Look capability: product and service contract

**Status:** Initial executable slice implemented on the feature branch; production integration remains gated  
**Date:** 5 November 2026

The current slice includes a deterministic three-role composer, an authenticated internal recommendation endpoint, a verified-subject decision-gateway route, a same-origin authenticated Wardrobe BFF route, and a Wardrobe page action. The gateway filters persisted NPL hard-vetoed closet items and uses only allowlisted positive USI fashion signals when profile-storage consent permits. The implementation does not yet provide a persistent Virtual Twin, a validated renderer, live weather ingestion, durable daily-look history, or experiment assignment/event instrumentation. The current Twin preview is explicitly unavailable.

## Product decision

**PNELLY** is the name of Cirvanna's daily-look recommendation capability. It should offer exactly three distinct daily looks:
1. **Everyday** — practical and compatible with the user's stated day.
2. **Elevated** — a polished option for a user-declared work, meeting, evening or other occasion.
3. **Explore** — a meaningfully different styling direction that remains within declared preferences and exclusions.

These are recommendation roles, not stereotypes. Never infer gender, culture, religion, modesty, body characteristics, occupation or occasion from a face, name, location or behavioural proxy. Context must be user-declared or supplied by an explicitly enabled, purpose-limited provider. In the first UI slice, occasion and climate are user-declared; live weather is not yet connected.

## Canonical assistant naming

ADR-0005 (4 November 2026) establishes Xari as the sole canonical assistant identity. Preserve that decision: Xari remains the conversational assistant/orchestrator, while **PNELLY is the named daily-look capability** coordinated by Xari and powered by the existing Complementer. PNELLY is not a second assistant, service, API, token family, profile store or runtime. This preserves the user's PNELLY product concept without creating duplicate assistant infrastructure or silently reversing the accepted naming ADR. Any future decision to make PNELLY the canonical conversational assistant requires a separate ADR and jurisdiction/category-specific trademark review.

## Authenticated request and response contract

The trusted application/BFF resolves the user from a verified principal. Never trust browser-supplied user IDs, Twin IDs, wardrobe owner IDs or consent booleans as authorization.

A request carries a unique idempotency ID, server-resolved subject reference, trusted date/timezone, explicit optional context, active USI/NPL/TAL version references, authorized Twin and wardrobe snapshot references, and active purpose-specific consent receipts for each capability used.

Return exactly three role slots. Each contains:
- stable recommendation ID and role (everyday, elevated, explore);
- canonical wardrobe item IDs actually present in the authorized wardrobe;
- optional canonical Catalog product/variant IDs for missing items;
- explanation tied to declared preferences, supplied context or a named styling rule;
- missing inputs and uncertainty notices;
- provenance and policy/model versions;
- Twin preview status (available, unavailable, not_requested), plus an opaque render reference only when a real renderer returns one;
- reversible actions: save, modify, reject, mark-worn and report issue.

Never fabricate wardrobe items, SKUs, merchant offers, stock, prices, product links, body measurements, fit claims or Twin renders. If persistent Twin or renderer capability is unavailable, return the styling plan and clearly mark preview unavailable. Never substitute a pose skeleton or synthetic placeholder while implying it is the user's Twin.

## Composition and domain ownership

1. Resolve identity and authorization at the trusted BFF.
2. Verify current purpose-specific consent and revocation state for wardrobe, personalization, Twin imagery and rendering.
3. Hydrate positive preferences from USI only when active profile-storage consent permits; accept only the allowlisted non-sensitive fashion namespaces for ranking. Apply persisted NPL hard vetoes to each owned wardrobe item before composition. Consented TAL observations may inform future profiles through their canonical owner; this first slice does not write learning events. Complementer must not own a duplicate profile.
4. Retrieve the current owner-scoped wardrobe; exclude deleted, unavailable, unverified or unauthorized assets.
5. Resolve only explicit context: user-declared occasion and climate in the first slice; any future schedule or weather integration must be separately enabled and sourced. Radius/budget belong to separate marketplace discovery.
6. Compose PNELLY's three roles with Complementer, invoked through the existing Xari orchestration or the authorized daily-look application flow. Prefer existing wardrobe items; use marketplace candidates only to fill a clearly identified gap.
7. Retrieve product facts from Catalog/Commerce. Every candidate passes required NPL, context, safety, fit-evidence and CAL checks. Only CAL SHOW may be displayed; BLOCK, REVIEW, missing evidence and pending decisions stay hidden.
8. Generate a Twin preview only through the separately authorized Twin/Try-On path after verifying Twin ownership, asset authorization, active server-side consent and renderer readiness.
9. Return explanations and reversible actions. One rejection is not an automatic permanent NPL veto.

## Diversity, utilisation and feedback

Require meaningful distinction between the three looks, not just reordered versions of the same combination. Track repeated combinations and recent wear history only when enabled. Prefer underused items without penalising favourites. Limit look completion to two optional changes unless the user asks for more. Novelty or marketplace revenue never overrides NPL or user choice.

Support explicit feedback: loved, not my style, too expensive, uncomfortable, already worn recently, show something different, save, modify and mark worn.

Personalization learning requires a current, explicit, revocable consent receipt verified server-side. Store idempotent events with recommendation ID, time, policy/model version, source and purpose. Rejection is a soft TAL observation, not an NPL veto. An explicit avoid instruction goes to NPL. Too expensive is scoped to the stated budget/currency or item; it is not a global preference without confirmation. Uncomfortable must not become a body or medical inference. Users must be able to inspect, correct, export and delete observations through canonical owners. Do not send raw face/body media to Complementer or log it.

## Failure behavior and release gates

Fail closed for identity, consent, NPL, CAL, asset ownership and renderer authorization. If context, wardrobe, Twin or renderer data is unavailable, degrade only the affected part and disclose it. If the persistent NPL provider is unavailable, do not release looks from an item-bearing wardrobe snapshot. Never claim a Twin preview was generated unless a real renderer returns a verified artifact.

Production release requires verified BFF identity binding and cross-tenant tests; deployed wardrobe persistence and deletion lifecycle; end-to-end USI/NPL/TAL hydration and consent/revocation; CAL for every product candidate; persistent Twin ownership and real renderer readiness; accessibility, latency, rate-limit and privacy tests; and measured cohort evidence.

Primary outcomes: meaningful weekly repeat use, D7/D28 retention, save/modify/wear rates, user-rated relevance and repeat use after feedback. Guardrails: hard-exclusion violations, unauthorized access, consent failures, repetitive looks, unsupported product facts, render failures, deletion SLA, complaints and opt-outs. Do not optimize opens, clicks or marketplace exposure as substitutes for user value.
