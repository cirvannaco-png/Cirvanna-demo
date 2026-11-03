# ADR-0002: CRFP naming correction and scope reconciliation

- **Status:** Superseded by [ADR-0003](ADR-0003-crfp-marketplace-and-system-scopes.md)
- **Date:** 2026-11-03
- **Scope:** Historical record of the acronym typo and its prior incorrect interpretation.

## Correction

The prior decision incorrectly treated **CFRP** and **CRFP** as two separate concepts. The product owner has clarified that **CFRP was a typo**. The canonical spelling is **CRFP**.

CRFP has two distinct scopes:
1. **Marketplace CRFP** — the CRFP scope belonging to marketplace workflows.
2. **System-wide CRFP** — the CRFP scope that applies throughout Cirvanna.

These are not two acronym variants and must not be merged into one undifferentiated implementation. See ADR-0003 for the corrected ownership and integration rules.

## Historical evidence

The archived source bundle previously labelled `CFRP V6` retains its original artifact filename and provenance for traceability. That filename is a historical typo, not evidence of a separate capability. The artifact's exact mapping to marketplace or system-wide scope must be verified against its contents and source-owner evidence before any implementation is promoted.

## Retained safeguards

This correction does not promote unverified candidate code. CAL remains the sole final SHOW/BLOCK/REVIEW display arbiter under ADR-0001; FCI remains responsible for fit-confidence estimation and calibration. CRFP must not silently acquire either authority without an explicit, reviewed contract and superseding decision.
