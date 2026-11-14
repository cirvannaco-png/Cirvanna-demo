-- Canonical Twin registry deletion/revocation lifecycle.
-- Binary objects remain in the private Asset Service; this outbox holds only opaque IDs.
BEGIN;

ALTER TABLE twin_registry_twins
  DROP CONSTRAINT IF EXISTS ck_twin_registry_state;
ALTER TABLE twin_registry_twins
  ADD CONSTRAINT ck_twin_registry_state
  CHECK (state IN ('active', 'revoked', 'deletion_pending', 'deleted'));

ALTER TABLE twin_registry_twins
  ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;
ALTER TABLE twin_registry_twins
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

CREATE TABLE IF NOT EXISTS twin_registry_deletion_outbox (
  outbox_id varchar(36) PRIMARY KEY,
  subject_id varchar(128) NOT NULL,
  twin_id varchar(128) NOT NULL
    REFERENCES twin_registry_twins(twin_id),
  asset_ids jsonb NOT NULL,
  command_id varchar(160) NOT NULL UNIQUE,
  status varchar(24) NOT NULL DEFAULT 'pending',
  attempts integer NOT NULL DEFAULT 0,
  last_error_code varchar(80),
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  CONSTRAINT ck_twin_registry_deletion_status CHECK (status IN ('pending', 'complete')),
  CONSTRAINT ck_twin_registry_deletion_attempts CHECK (attempts >= 0),
  CONSTRAINT ck_twin_registry_deletion_asset_ids CHECK (jsonb_typeof(asset_ids) = 'array')
);

CREATE INDEX IF NOT EXISTS ix_twin_registry_deletion_status_created
  ON twin_registry_deletion_outbox(status, created_at);

COMMIT;
