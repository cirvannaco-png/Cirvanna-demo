# Negative Preference Layer (NPL)

**Status:** deterministic policy kernel implemented; persistence and service integration are not yet certified.

NPL enforces explicit negative preferences and durable learned exclusions. It is a veto layer, not a ranking model and not the final display authority. CaTaCaCi/CAL must still return `SHOW` before any candidate is displayed.

## Contract

- Explicit user-declared item or attribute exclusions are hard vetoes while active.
- Learned rejection evidence is idempotent by rejection-event ID. The default threshold is three unique rejection events; at threshold, the exclusion becomes a hard veto.
- Learned hard vetoes do not decay automatically. Reversal requires an explicit, auditable correction event.
- Preferences are scoped to a user; another user's preferences cannot affect the decision.
- The result separates hard-veto IDs from below-threshold soft-negative IDs.
- Inputs and outputs are deterministic and contain no hidden persistence or network behavior.

## Integration boundary

`core.py` is a pure domain kernel. It does not write to a database, infer user identity, update learned state silently, or authorize display. A service adapter still needs versioned persistence, audit-event delivery, concurrency/idempotency guarantees across workers, retention/deletion controls, and contract/integration tests against CaTaCaCi CAL.

Run the tests from the repository root:

```bash
python -m unittest discover -s tests/architecture -v
python scripts/validate_architecture.py
```


## Durable service boundary

`ports.py` defines the required persistence operations and transaction semantics for a future service adapter. It is an interface only. Do not call NPL persistence-complete until a PostgreSQL adapter, unique event constraints, transaction/concurrency tests, and retention/deletion evidence are merged.
