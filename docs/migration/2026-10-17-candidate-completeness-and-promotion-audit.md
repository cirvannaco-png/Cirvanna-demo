# Source completeness, conflict resolution and integration audit

**Audit date:** 17 October 2026  
**Audited base:** main at commit 326d37a737a613a6aa616b47d06a282e09607b94  
**Scope:** all 31 preserved source snapshots, the 544-entry extraction manifest, canonical identity/fit/policy contracts, Virtual Twin API and recovered Click It source.

## Executive result

The source archive and 31 extracted source snapshots remain preserved. A path-by-path comparison of integration-staging/source-manifest.json with the repository tree found **17 missing staged files** before this audit. Those were four missing Virtual Try-On model files in each of three variants, four files in the alternate Virtual Try-On variant, and one CFRP secrets-manager file. This change restores all 17 only under their original source-candidates/<source-section>/ paths; each recovered file's UTF-8 byte count matches its manifest record. Nothing was overwritten in a canonical runtime directory.

The candidate source is now expected to satisfy **544/544 staged-file presence checks**. A repository CI test also hashes all 31 extracted source snapshots against source-audit.csv to detect accidental edits to the preserved provenance copies.

## Completeness, duplicates and drift

- **Missing before repair:** 17 staged paths, all restored from the corresponding preserved extracted snapshot using the declared filename section and fenced code block. The secrets-manager and model files remain unpromoted candidates.
- **Exact duplicate source snapshots:** three groups: FCI .txt and Fit Confidence Index repository .txt; Tari improved .txt and the source originally named ```.txt; and virtual Tryon (1).txt, virtual Tryon (2).txt, and virtual Tryon improved.txt. Identical inputs stay preserved for provenance; the duplicates are not treated as independent implementations.
- **Exact duplicate staged file contents:** the pre-repair tree contained 64 repeated-content groups spanning 166 candidate path instances. The restored Virtual Try-On model snapshots introduce more intentional repeated-content files. Candidate-level duplicates are retained because each points back to a different source section; promotion decisions must compare versions, not count copies as separate evidence.
- **Version/conflict markers:** CDIC appears as a TypeScript identity engine plus multiple Python generations (including V4 and V5 source snapshots); EEPL has base and V2.0 sources; FCI has a base repository and V2.0; NPL V2 is a TypeScript architecture; several Virtual Try-On source dumps are exact copies or near-copies. These are conflicting source inputs, not automatically mergeable implementations.
- **Malformed or absent extraction:** seven source sections have zero extracted code files (CDIC V4, FCI (1), the small FCI repository fragment, skin-analysis fragment, and three Virtual Twin text dumps). Their original extracted text remains preserved. An empty code extraction does not mean the source document itself is missing.

## Canonical choices

| Component | Canonical path / decision | Scope and constraints |
|---|---|---|
| CaTaCaCi / CAL | packages/identity-intelligence/catacaci/ | The deterministic Python CAL arbitration core is the sole display authority. CAL is a decision governance layer, not a weighted recommender. TAL, CAM, CIL and VSL are separate governance contracts; persistence, replay, access controls and production approval workflows remain incomplete. |
| CDIC | packages/identity-intelligence/cdic/ remains a compatibility boundary; TypeScript V7 stays under candidates/typescript-v7/ | Do not allow a legacy CDIC status to replace or override CAL. A canonical CDIC runtime/adapter is not certified because source generations disagree about language, interfaces and responsibilities. |
| EEPL | packages/identity-intelligence/eepl/core.py | Explicit age, location, occasion and climate allowlists. Unknown required context is REVIEW; explicit policy violations are BLOCK. Legacy service-oriented candidates remain staged. |
| FCI | packages/fit-intelligence/fci/core.py | Accepts only estimates with explicit calibration and provenance for a passing confidence signal. It is not a trained fit predictor. The exact duplicate legacy FCI repository is not independently promoted. |
| USI | packages/identity-intelligence/usi/core.py | Declared positive style alignment only. It does not decide hard dislikes, override NPL, or authorize display. Incomplete metadata routes to REVIEW. |
| NPL | packages/preferences/npl/core.py | User-declared exclusions are hard vetoes; learned exclusions become hard after the configured three unique rejection events. Its clear result is not display authorization. Durable persistence and event delivery still belong in a consuming service. |
| Click It | Original recovered code remains in integration-staging/recovered-virtual-twin.py; a guarded POST /click-it API contract is added to services/virtual-twin/app/main.py | The API validates authentication, image MIME type and size but returns 503 until product-photo reconstruction and the governance binding are actually configured. It does not process or store the photo while unavailable. |
| Virtual Twin | services/virtual-twin/ | The existing API remains fail-closed. MODEL_ADAPTER_IMPLEMENTED = False; /ready and /twin return 503 and capability flags remain false. Upload handling is not proof of reconstruction. |

## Contract-level vertical slice

A new catacaci.pipeline.evaluate_candidate function wires the canonical EEPL, NPL, USI and FCI contracts into CAL:

1. EEPL becomes a required CONTEXT_ELIGIBILITY signal.
2. NPL becomes a required NPL_HARD_NEGATIVE signal; a matching hard veto is non-overridable.
3. USI becomes the required IDENTITY_ALIGNMENT signal.
4. FCI becomes the required FIT_CONFIDENCE signal; uncalibrated estimates are UNKNOWN.
5. Independently computed safety, legal eligibility, user-hard-constraint and cultural signals must be passed as upstream evidence. Missing required gates are not synthesized as passes.
6. Only the resulting CAL SHOW verdict authorizes display. BLOCK and REVIEW both prohibit display.

Integration tests exercise a complete SHOW path, an NPL veto overriding strong fit, missing upstream signals, EEPL rejection, uncalibrated FCI, missing context, USI review, identity mismatch and duplicate signal rejection. This verifies the **pure contract boundary**, not an end-to-end deployed commerce or Click It journey.

## Validation gates

The PR triggers the repository's existing GitHub Actions gates:

- Python syntax compilation of every staged candidate under integration-staging/source-candidates/.
- Architecture inventory validation and all architecture/unit/integration contract tests.
- Virtual Twin API tests plus installed Python dependency consistency (pip check).
- Redacted credential-pattern scan over the repository.

The original archive contains credentialed local/container database and broker examples in preserved source material. Those files remain provenance-only; a successful pattern scan is not a substitute for threat modeling, secrets rotation when needed, a full SCA report, or production security review. Candidate requirements are not installed indiscriminately: installing every legacy candidate's requirements together would combine conflicting historical stacks and execute unreviewed dependency setup.

## Remaining release blockers

1. A validated Virtual Twin reconstruction/model adapter and assets.
2. A real Click It photo-to-product reconstruction path connected to the user's Virtual Twin, with a verified identity/twin ownership boundary.
3. A deployed orchestration/service connection that gathers trusted profile, product metadata, consent, safety/legal/cultural gates and calibrated fit evidence before calling the pipeline.
4. Persistent/auditable NPL learning and TAL/CAM/CIL/VSL storage, replay, privacy and access controls.
5. Canonical CDIC responsibility and adapter decision, plus broader model/dependency/security evaluation and end-to-end acceptance tests.

This change makes source completeness measurable and adds a tested contract integration point. It does not certify Cirvanna as production-ready.
