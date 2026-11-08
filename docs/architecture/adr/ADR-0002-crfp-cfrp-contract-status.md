# ADR-0002: CRFP naming correction and scope reconciliation

- **Status:** Superseded by [ADR-0003](ADR-0003-crfp-marketplace-and-system-scopes.md)
- **Date:** 2026-11-03
- **Scope:** Historical record of the acronym typo and its prior incorrect interpretation.

## Correction

The prior decision incorrectly treated **CFRP** and **CRFP** as two separate concepts. The product owner clarified that **CFRP was a typo**. The canonical spelling is **CRFP**.

CRFP has two distinct scopes:

1. **Marketplace CRFP** — the CRFP scope belonging to marketplace workflows.
2. **System-wide CRFP** — the CRFP scope that applies throughout Cirvanna.

These are not two acronym variants and must not be merged into one undifferentiated implementation. See [ADR-0003](ADR-0003-crfp-marketplace-and-system-scopes.md) for corrected ownership and integration boundaries.

## Historical evidence and retained safeguards

The archived source bundle previously labelled `CFRP V6` retains its original artifact filename and provenance for traceability. That filename is a historical typo, not evidence of a separate capability. The archived artifact's exact mapping to marketplace or system-wide scope remains unverified.

This correction does not promote candidate code. FCI remains responsible for fit-confidence estimation; CAL remains the sole final `SHOW` / `BLOCK` / `REVIEW` display arbiter under ADR-0001. Neither CRFP scope gains those authorities by acronym or documentation alone.

The pre-correction decision is preserved in [the ADR-0002 historical archive](archive/ADR-0002-crfp-cfrp-contract-status-pre-correction.md).
