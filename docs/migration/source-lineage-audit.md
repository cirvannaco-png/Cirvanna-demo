# Source lineage audit — scope and limitations

**Status:** Integrity gate implemented; full candidate-to-source mapping is not yet complete.

## What the audit verifies

- The credential-redacted source archive matches the byte count and Git blob hash pinned in `integration-staging/source-manifest.json`.
- The archive contains the declared number of source sections.
- Historical snapshot-manifest and snapshot-audit records agree with each other.
- Each present extracted snapshot matches the **current** byte count and Git blob hash recorded in `docs/migration/source-snapshot-lineage-ledger.csv`.
- The candidate lineage ledger covers the candidate manifest, and each staged candidate matches its recorded size, blob hash, duplicate count and source identifiers.
- The on-disk staged-candidate file inventory matches the declared candidate paths.

Historical snapshot hashes are retained as provenance. They must not be confused with current snapshot hashes where redaction or reviewed edits changed the content. The audit reports archive-versus-snapshot differences as a count instead of claiming that all historical copies are byte-identical.

## What remains unresolved

The source snapshots contain several incompatible source-dump formats. The current named-code-block parser does not resolve every staged candidate path; those cases are reported as `SOURCE_BLOCK_NOT_FOUND`. Other content mismatches are reported explicitly with hashes and source metadata. The workflow currently invokes `--allow-unreconciled` so known mapping-coverage gaps are visible as warnings while structural integrity checks still fail closed.

**This is not proof that all 544 candidate files exactly match an originating source block, and it does not promote or certify any staged candidate as runtime code.** Improve the parser and review unresolved diffs before treating candidate/source semantic parity as established.

## CFRP V6 exception

Four CFRP V6 candidate files were hardened on PR #41 while remaining under `integration-staging/source-candidates/`. Their current blob hashes and byte counts are recorded in the candidate lineage ledger; the exception ledger explains why these isolated runtime-safety edits differ from their original extracted source. This exception is evidence of reviewed candidate drift, not authorization to deploy CFRP V6.

## Reproduction

From a clean checkout with Python 3.11 or newer:

```bash
python scripts/audit_source_lineage.py --allow-unreconciled
```

The result reports integrity failures separately from unresolved content mappings. A successful run establishes archive/snapshot/candidate ledger integrity only within the checks above; it is not a production readiness result.


## 2026-11-03 CRFP naming correction

References in this lineage record to CFRP V6 describe historical source filenames and candidate changes. The product owner clarified that CFRP was a typo; the canonical acronym is CRFP, with distinct marketplace and system-wide scopes. The archived candidate's scope mapping remains unverified. Historical source hashes and filenames are preserved for provenance. See [ADR-0003](../architecture/adr/ADR-0003-crfp-marketplace-and-system-scopes.md).
