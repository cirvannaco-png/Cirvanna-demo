-- Downgrade only the Twin Registry deletion lifecycle migration.
-- Caller must ensure no Twin row remains in deletion_pending/deleted state.
BEGIN;

DROP TABLE IF EXISTS twin_registry_deletion_outbox;

ALTER TABLE twin_registry_twins
  DROP CONSTRAINT IF EXISTS ck_twin_registry_state;
ALTER TABLE twin_registry_twins
  ADD CONSTRAINT ck_twin_registry_state
  CHECK (state IN ('active', 'revoked'));

ALTER TABLE twin_registry_twins
  DROP COLUMN IF EXISTS deleted_at;
ALTER TABLE twin_registry_twins
  DROP COLUMN IF EXISTS version;

COMMIT;
