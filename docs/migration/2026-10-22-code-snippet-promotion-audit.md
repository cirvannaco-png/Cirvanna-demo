# Cirvanna code-snippet inventory and controlled promotion audit

**Date:** 22 October 2026  
**Base commit:** dd7ebdbd2a31032de263a2a80fa1f9e63b68dbfe  
**Scope:** canonical runtime, extracted source archive, source-candidate bundles, and existing lineage/promotion records.

## Decision

The source snippets must be integrated by reviewed behavior, not copied wholesale into runtime. The repository preserves multiple generations, duplicates, framework assumptions, experimental models, and services that can contradict the current CAL contract. A raw copy would create competing decision paths and could make uncalibrated fit scores or unvalidated image inference look production-ready.

This pass promotes one isolated, testable utility from the staged FCI snippets: outcome-based calibration metrics. It does not promote a fit estimator, train or enable a model, change CAL display authorization, or claim that Cirvanna has calibrated fit intelligence.

## Code added in this pass

- `packages/fit-intelligence/fci/metrics.py`: pure-Python Brier score, equal-width expected calibration error (ECE), observed fit-success rate, high-confidence failure rate, and optional mean interval width. It validates finite probability values, aligned observed labels, bin counts, and interval widths.
- `packages/fit-intelligence/fci/__init__.py`: exports the evaluation utility without changing the existing FitConfidenceEstimate contract.
- `tests/architecture/test_fci_metrics.py`: deterministic tests for normal metrics, edge bins, no high-confidence cohort, malformed inputs, and interval validation.

The implementation is informed by the legacy FCI candidate at `integration-staging/source-candidates/09-fci-.txt/src/fci/metrics.py` and its duplicate/near-duplicate FCI V2 and Fit Confidence Index snapshots. It intentionally removes NumPy and PostgreSQL dependencies from the evaluation helper and corrects ambiguous empty-cohort/high-confidence behavior. These metrics are for offline evaluation only; they do not prove model calibration without a sufficiently representative, independently labelled evaluation set.

## Source-bundle review register

All currently present top-level bundles under `integration-staging/source-candidates/` were inventoried. The original files remain available for provenance.

| Source bundle(s) | Existing canonical destination / decision | Promotion rule |
|---|---|---|
| `01-cdic-.txt` | TypeScript CDIC V7 remains isolated under `packages/identity-intelligence/cdic/candidates/typescript-v7/` | Keep as a candidate until its interface and policy responsibilities are reconciled with CAL. |
| `03-cdic-v5.txt`, `04-cdic.txt` | Legacy Python CDIC generations remain staged | Do not add a second display-authorizing engine. Compare reusable utilities individually. |
| `05-cfrp-v6.txt` | `tests/cfrp_candidate/` plus preserved staged tree | Candidate only; simulated adapters and experimental lifecycle code are not canonical production services. |
| `06-eepl-v2.0.txt`, `07-eepl.txt` | `packages/identity-intelligence/eepl/` | Canonical EEPL owns the runtime contract. Port only behavior covered by tests and explicit policy definitions. |
| `09-fci-.txt`, `10-fci-v2.0.txt`, `11-fit-confidence-index-repository-.txt` | `packages/fit-intelligence/fci/` | FCI contract is canonical; evaluation metrics are promoted here. Do not promote fallback confidence scores or heuristic intervals as calibrated predictions. |
| `12-npl-v2.txt` | `packages/preferences/npl/` | Preserve the canonical hard-veto contract; review TS snippets against unique rejection-event semantics before porting. |
| `13-tari-improved-.txt`, `14-we-have-now.txt`, `15-xyra.txt`, `17-txt` | Xari/assistant-related material remains staged | Reconcile legacy names, permissions, tool boundaries, memory, and privacy before service integration. |
| `18-cirvanna-skeleton-.txt` | Source reference only | Do not promote scaffolding or duplicate policy logic merely to fill target directories. |
| `19-cultural-identity-module-.txt` | `packages/identity-intelligence/cultural_identity/` | Keep user-directed identity settings explicit; do not infer sensitive identity from appearance. |
| `20-identity-decision-engine-.txt` | CAL / canonical decision pipeline | Port only non-conflicting logic; CAL remains the sole SHOW/BLOCK/REVIEW authority. |
| `22-skin-analysis-repo-.txt` | `services/dermalsight/` API and validation boundary | Do not enable unvalidated weights, inference, or diagnostic claims. |
| `23-virtual-tryon-1-.txt`, `24-virtual-tryon-2-.txt`, `25-virtual-tryon-.txt`, `26-virtual-tryon-improved.txt` | `services/virtual-try-on/` and `services/virtual-twin/` | Deduplicate and validate model/renderer lineage, consent, asset authorization, and quality before enabling rendering. |
| `30-wardrobe-2-3-and-4-.txt`, `31-wardrobe-part-1.txt` | Wardrobe feature remains a staged capability | Define canonical wardrobe schema, media permissions, ownership, and deletion before integrating persistence. |

## Promotion protocol for remaining snippets

For each source file, record its source bundle and content hash; classify it as exact duplicate, near-duplicate, unique, malformed, or dependency-bound; map it to one canonical owner; inspect side effects, secrets, network/database assumptions, privacy boundaries, and policy conflicts; port only a small coherent behavior; add tests against the canonical contract; then run the architecture validator, source-lineage audit, unit suite, secret scan, and relevant service workflow.

No staged source is considered runtime merely because it exists in the repository. Source lineage is preserved even when a snippet is rejected, superseded, or left pending. This audit is a controlled first promotion pass, not a claim that every candidate file has been ported.
