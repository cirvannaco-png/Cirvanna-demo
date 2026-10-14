# Sync service

**Owner:** Offline-sync queue, replay, deduplication and conflict resolution. **Status:** scaffold only.

Use idempotency keys, versioned events, bounded retries and auditable conflict decisions. Keep synchronization mechanics separate from domain truth; never apply a replay that silently overwrites a user constraint.