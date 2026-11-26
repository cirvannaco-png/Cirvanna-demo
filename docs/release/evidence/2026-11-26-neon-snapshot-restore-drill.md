# Neon staging snapshot and restore drill — 2026-11-26

**Status:** staging-only restore drill; not production backup certification.  
**Project:** `cirvanna-catalog-staging` (`twilight-leaf-50209271`)  
**Source branch:** `br-empty-unit-bhpa7igy` (`main`, default)  
**Snapshot:** `snap-lingering-hat-bhgnln33` (`cirvanna-staging-pre-release-2026-11-26`)  
**Snapshot expiry:** 2026-12-03T00:00:00Z  
**Restored branch:** `br-damp-firefly-bhc4lboy` (`cirvanna-staging-restore-drill-2026-11-26`)  
**Restore mode:** new branch; `finalize=false`; source/default branch was not replaced.

## Restore verification

The restored branch contains all 11 source databases. Structural checks on source and restored branches matched:

| Database | Source base tables | Restored base tables |
|---|---:|---:|
| `cirvanna_catalog` | 4 | 4 |
| `cirvanna_commerce` | 30 | 30 |

Decision receipt store:
- `decision_private.catacaci_decision_receipts` exists on both source and restored branches.
- 19 columns are present on both branches.
- Runtime role can SELECT/INSERT, cannot UPDATE/DELETE/TRUNCATE, and has no schema CREATE.

Commerce audit immutability was re-tested on the restored branch using `cirvanna_commerce_runtime`:
- INSERT of a sentinel audit record succeeded within a transaction.
- UPDATE and DELETE were rejected by the immutable audit guards.
- TRUNCATE was rejected.
- The transaction was rolled back and a subsequent query confirmed zero sentinel rows remained.

Catalog and Commerce runtime-role login/privilege checks also succeeded on the restored branch. Catalog runtime has no TRUNCATE. Commerce runtime has ordinary write privileges for its application tables; its CAL audit table remains protected by dedicated triggers and lacks runtime TRUNCATE privilege.

## Limitations

- This is a successful structural/data snapshot restore into a new branch, not a production recovery exercise.
- The current Neon project has a 6-hour instant-restore history window (`21600` seconds). A daily scheduled snapshot schedule is not configured.
- A single manual snapshot is retained for seven days. Snapshot storage and branch/compute usage are subject to the active Neon plan and usage limits.
- No application services were deployed against the restored branch; identity, checkout, webhook, order/inventory reconciliation, and service-level post-restore journeys remain untested.
- No measured production RPO/RTO can be claimed from this drill.

## Disposition

Supporting evidence for REL-03 and REL-10 only. The database/restore gates remain **BLOCKED** pending production-grade backup retention, isolated clean restore with business-data invariants, deployed service checks, measured RPO/RTO and approval by the named reliability owner.
