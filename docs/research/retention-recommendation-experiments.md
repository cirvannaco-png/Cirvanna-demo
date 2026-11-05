# Cirvanna retention and recommendation experiments

**Status:** Proposed experiment protocol; no outcome or benchmark is claimed  
**Date:** 5 November 2026

## Research principle

These five experiments are hypotheses, not industry benchmarks, validated targets or promises of uplift. Register hypotheses, primary outcomes, guardrails, analysis plans and stopping rules before examining outcomes. Distinguish descriptive association from causal effects.

## Shared standards

- Randomize at user/account level where practical; keep assignment stable.
- Stratify only on relevant, minimally collected baseline factors such as new/returning status, platform and wardrobe completeness. Do not collect sensitive attributes merely for stratification.
- Use intention-to-treat as the primary analysis. Report exposure and compliance separately.
- Predefine eligibility, exclusions, sample-size calculation, minimum detectable effect, alpha/power, duration and stopping rules from observed baseline rates and variance. Do not invent sample sizes or durations.
- Report confidence intervals, absolute and relative effects, missingness, attrition, contamination and cohort composition.
- Avoid overlapping experiments unless a pre-registered, adequately powered factorial design explicitly tests interactions.
- Maintain a useful baseline and opt-out. Privacy, consent, safety, accessibility and user choice are hard guardrails.
- Clicks and saves are not purchases.

## 1. Wardrobe-only vs integrated experience

**Hypothesis:** connecting wardrobe, daily looks, genuinely available Twin preview, discovery and feedback increases meaningful repeat use.

**Control:** wardrobe experience without integrated daily-look journey.  
**Treatment:** wardrobe plus three daily look roles, contextual explanation, optional authorized Twin preview and feedback actions.

**Primary:** D28 meaningful retention, defined before launch as at least one qualifying wardrobe/look action on a later distinct day in the observation window.  
**Secondary:** D7 retention, active days, look saves/modifications/marks-worn and return after feedback.  
**Guardrails:** relevance, hard-exclusion violations, opt-outs, complaints, duplicate looks, latency and unauthorized access.

An app open or passive notification view is not meaningful retention.

## 2. PNELLY/Complementer with wardrobe context vs without

**Hypothesis:** wardrobe context improves recommendation relevance and reduces unnecessary purchase suggestions.

**Control:** same authorized preferences and declared context, without wardrobe inventory.  
**Treatment:** additionally provide minimal owner-scoped wardrobe snapshot/references.

**Primary:** user-rated relevance using the same prompt and scale in both arms.  
**Secondary:** save, modify, reject, mark-worn and missing-item suggestion rates.  
**Guardrails:** consent violations, unauthorized reads, hard-exclusion violations and unsupported claims.

Do not expose more wardrobe data than needed. Xari remains the canonical assistant under ADR-0005 unless a separate ADR changes the name; do not introduce a second Tari runtime.

## 3. Visual discovery connected to wardrobe vs standalone

**Hypothesis:** connecting visual discovery to owned wardrobe items produces more useful discoveries.

**Control:** standard visual discovery and canonical policy gating.  
**Treatment:** discovery may additionally use authorized wardrobe references to explain compatibility or gaps.

**Primary:** qualified discovery rate: candidate is CAL SHOW, viewed and explicitly saved or marked relevant.  
**Secondary:** user-rated usefulness, wardrobe pairing actions and return to discovery.  
**Guardrails:** CAL bypasses, false matches, stale offers, unauthorized image/wardrobe access and mistaken fit claims.

Visual similarity is not product identity, fit, purchase intent or relevance.

## 4. 30 km default vs user-expanded marketplace radius

**Hypothesis:** preserving 30 km as the default while making expansion clear and user-controlled improves qualified discovery for people who need broader coverage.

**Control:** 30 km default with existing radius-change capability.  
**Treatment:** same default plus clearer radius-expansion control and explanation.

**Primary:** qualified product discovery rate among users exposed to local discovery.  
**Secondary:** radius changes, relevant offer saves, merchant availability and user-rated usefulness.  
**Guardrails:** user control, location minimisation, stale inventory, fulfilment feasibility and no identity/cultural inference.

Never silently expand radius or use precise location without permission. Record only the minimum radius/location provenance needed.

## 5. Feedback-informed recommendations vs baseline

**Hypothesis:** recommendations informed by explicit, consented, reversible feedback improve subsequent user-rated relevance.

**Control:** baseline recommendation policy without feedback-derived profile updates.  
**Treatment:** eligible, consented TAL observations, respecting correction, expiration and deletion.

**Primary:** change in user-rated relevance on subsequent recommendations.  
**Secondary:** repeated rejection of the same attribute, modification frequency, save/wear actions and opt-outs.  
**Guardrails:** consent-revocation latency, correction/deletion success, repeated disliked suggestions, accidental NPL vetoes and overfitting.

NPL remains authoritative in both arms. A soft rejection must never become a hard veto merely because of experiment assignment.

## Analysis and interpretation

For each experiment publish the registered hypothesis, experiment ID, assignment and eligibility, allocation, baseline and sample-size rationale, exposure/contamination, outcome definitions, absolute and relative effects with confidence intervals, guardrail results, subgroup limitations, missingness/attrition and decision (ship, iterate, reject or continue).

A positive correlation between feature usage and retention does not prove the feature caused retention. Causal estimates rely on randomized assignment and are still subject to implementation quality, noncompliance, attrition and interference assumptions.

## Rollout sequence

1. Instrument and validate event quality.
2. Run an A/A test to detect assignment or instrumentation imbalance.
3. Start with the lowest-risk experiment and verify guardrails.
4. Run one experiment at a time unless a justified factorial design is pre-registered.
5. Stage rollout only after primary outcome and guardrails meet predeclared criteria.
6. Monitor novelty decay, drift, complaints and opt-outs after rollout.

## Minimum event taxonomy

Use pseudonymous subject IDs; never include raw image or sensitive-context payloads.

- experiment_assigned
- daily_look_generated
- daily_look_viewed
- daily_look_saved
- daily_look_modified
- daily_look_rejected
- daily_look_marked_worn
- daily_look_preview_unavailable
- visual_discovery_qualified
- marketplace_radius_changed
- recommendation_feedback_submitted
- consent_revoked
- profile_corrected_or_deleted

Events include experiment/variant, policy/model version, timestamp, source, purpose and event ID. Keep schemas versioned and idempotent. Retention, access, deletion and aggregation follow applicable jurisdiction-specific privacy requirements.
