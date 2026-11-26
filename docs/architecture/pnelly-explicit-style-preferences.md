# PNELLY explicit style-preference learning

**Status:** explicit save path merged in PR #283; management and EEPL journey follow-up is under review.
**Owners:** Marketplace BFF (presentation boundary), Identity Learning Service (USI persistence), Decision Gateway (verified profile hydration), Complementer daily-look composer (ranking).  
**Scope:** PNELLY + Wardrobe only. This does not change Click It, Look It, Virtual Twin, Try-On, Catalog, NPL, or CAL ownership.

## Behaviour

A Complementer advisory is request-scoped. Its prose and the generic **Helpful / Not for me** reaction are not silently promoted into an aesthetic preference. The Wardrobe UI offers a separate preference control after the advisory. The user must select one value and press **Save this preference**.

The current bounded taxonomy is:

- Style: minimalist, elegant, romantic, bold, streetwear, classic, editorial.
- Colour: teal, navy, earthy, monochrome, pastel.
- Silhouette: relaxed, tailored, oversized, structured.
- Material: linen, cotton, denim, silk.
- Pattern: solid, floral, striped, geometric.

Free-form model output, raw advisory text, and inferred user traits are not accepted as saved preferences. Extending this taxonomy requires a reviewed contract and tests.

## Request and persistence path

1. The browser sends the opaque Complementer `request_id`, the exact `profile_storage` consent receipt ID, and one allowlisted attribute to the same-origin Marketplace BFF.
2. The BFF resolves the user through Commerce `/me`; it does not accept a subject ID from the browser.
3. The BFF checks that the exact receipt belongs to the verified subject, has scope `profile_storage`, is granted, is not revoked, and has not expired.
4. The BFF reads the subject's canonical USI profile, derives a stable preference ID from the verified subject, request ID, and selected attribute, and writes the updated profile with optimistic `expected_version` plus the same consent receipt ID.
5. The Identity Learning Service rechecks that exact receipt inside the profile-write path. A different active receipt cannot authorize a stale client receipt.
6. The preference is stored in the existing USI profile JSON field with `source=pnelly_user_confirmed` and `source_request_id`. The Identity Learning Service validates both the controlled taxonomy and request provenance.
7. The next PNELLY daily-look request hydrates the verified USI profile. The Decision Gateway forwards only active positive fashion preference namespaces to the existing daily-look composer. The composer uses these as bounded ranking hints and may explain a match as a saved style preference.

The profile API's existing version conflict is returned rather than overwritten. A retry with the same request ID and selected value is idempotent; a conflicting reuse of the derived preference ID is rejected. A duplicate active attribute returns `already_present` without adding a second entry.

## Preference management

The Marketplace BFF exposes a private, same-origin management surface for PNELLY-owned entries only:

- `GET /api/wardrobe/pnelly/preferences?consent_receipt_id=...` verifies the exact active profile-storage receipt and returns the PNELLY-owned subset plus the USI profile version.
- `POST /api/wardrobe/pnelly/preferences/{preference_id}/replace` requires the current profile version and a newly selected taxonomy value. The prior entry is deactivated and a new provenance-bearing entry is created; deterministic IDs make a committed retry replay-safe.
- `POST /api/wardrobe/pnelly/preferences/{preference_id}/deactivate` marks the entry inactive. It never creates an NPL exclusion or deletes unrelated user-declared preferences.

Both mutation paths recheck the exact receipt, bind the subject through Commerce `/me`, reject profile-version conflicts, and confirm the persisted result before reporting success. Revoking profile-storage consent hides the manager and blocks further reads and writes. Deactivated preferences remain auditable in USI but are filtered out of later ranking hydration.

## EEPL in the PNELLY daily-look journey

The same-origin BFF accepts a user-declared location, occasion and climate, then stamps a server-side observation time. The Decision Gateway applies the existing strict freshness policy (location 24 hours, occasion 7 days, climate 6 hours) and evaluates EEPL before loading USI profile data, NPL wardrobe exclusions or the look composer.

- `PASS`: look composition may proceed. This is context-policy passage only; it is not product-display authorization and does not bypass CAL.
- `REVIEW`: missing, invalid, future-dated or stale required context produces no looks and does not update wardrobe rotation.
- `BLOCK`: an explicit policy violation produces no looks and does not update wardrobe rotation.

The BFF validates the fail-closed response contract. The UI surfaces the reason codes/explanations rather than showing an empty response as a successful recommendation. User-declared values are explicitly identified as user-declared; this path does not infer age, location or climate from appearance or device signals.

## Consent and learning semantics

- Saving a durable USI preference requires active `profile_storage` consent. The exact receipt is checked twice: at the BFF boundary and in the canonical persistence service.
- Wardrobe like/wear feedback and Complementer Helpful/Not for me reactions remain separate consented TAL observations under `style_learning` or `personalization` consent.
- A generic approval/rejection is not a typed preference and does not independently change later ranking.
- A saved preference is positive and soft. It is not an NPL exclusion, a purchase authorization, a fit claim, a CAL decision, or permission to display a product.
- Existing NPL hard exclusions remain authoritative and are evaluated before outfit composition.
- Profile revocation blocks subsequent reads/writes through the canonical profile service. User data export/deletion remains owned by Identity Learning Service.

## Persistence and migration

No database migration is introduced. The existing `identity_usi_profiles.preferences` JSON column stores the additional optional `source` and `source_request_id` fields. Older profile entries remain valid because `source` defaults to `user_declared` and `source_request_id` remains optional for those entries. The existing profile version provides optimistic concurrency.

## Validation evidence

The implementation adds coverage for:

- allowlisted PNELLY values and mandatory request provenance;
- rejection of unbounded values and forged/missing provenance;
- exact-receipt consent enforcement, including a revoked receipt when another profile receipt exists;
- verified Commerce subject binding at the BFF and gateway boundaries;
- idempotent replay and no duplicate profile entries;
- profile-version conflict handling and replay-safe preference replacement;
- inspect/replace/deactivate semantics restricted to PNELLY-owned preference records;
- EEPL PASS, BLOCK, missing-context REVIEW and stale-context REVIEW through the daily-look gateway;
- BFF early-return behaviour that does not write rotation state on BLOCK/REVIEW;
- use of active USI style signals by the daily-look composition path;
- browser contract and inline JavaScript syntax.

Unit and contract tests do not prove deployed PostgreSQL durability, production identity-provider configuration, live cross-service operation, cohort improvement, or production readiness. Those remain separate release gates.

## Rollback

Disable or remove the BFF preference-write route and Wardrobe preference control. No schema rollback is required. Existing profile JSON rows remain readable by the prior profile contract; the optional provenance fields can be ignored by older consumers. Do not delete existing user preferences as part of rollback.


## Independent style dimensions (extension)

**Implementation branch:** `feat/pnelly-independent-style-dimensions`

PNELLY now exposes a compositional style-profile contract with five orthogonal dimensions:

1. **Cultural expression** — only user-selected craft, garment and styling references. These are soft styling signals; explicit hard cultural requirements remain owned by Cultural Identity and are not inferred from identity or appearance.
2. **Personal aesthetic** — one or more aesthetic directions, including classic / old money, minimalist, romantic, streetwear, editorial, bohemian and natural.
3. **Occasion** — the current declared occasion, independently evaluated from aesthetic and cultural expression.
4. **Personal preferences** — preferred and excluded colours, silhouettes, materials, patterns and coverage requirements.
5. **Regional context** — explicitly selected market country, declared location and declared climate. Market selection is not a proxy for ethnicity, religion or style.

The Complementer response adds `style_profile` while retaining the existing response fields. Each dimension reports its own selected/not-selected state. Missing dimensions remain unspecified; the composer does not fill them from demographic or visual inference. The existing USI JSON preference store remains canonical. The BFF and Identity Learning Service share the same allowlisted PNELLY attribute vocabulary, with request provenance and exact profile-storage consent unchanged.

The Wardrobe experience adds a multi-axis personal-atelier selector. Saving selected values uses the existing consent-bound PNELLY BFF route one attribute at a time, so the canonical USI version check, idempotency and persistence confirmation remain in force. The interface does not claim success unless each save is confirmed.

Regional availability, local designers, market pricing and fulfilment remain Catalog/Commerce responsibilities. The `market:XX` preference records a user-selected preferred market only; it does not assert product availability. All product display continues to require CAL authorization.

Rollback: revert the branch. Existing USI profile JSON remains backward-compatible; newly saved attributes are ignored by older recommendation consumers unless explicitly supported. Do not delete user profile records during rollback.
