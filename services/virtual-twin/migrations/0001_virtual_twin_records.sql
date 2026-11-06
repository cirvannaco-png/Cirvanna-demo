CREATE TABLE IF NOT EXISTS virtual_twin_records (
  twin_id varchar(128) PRIMARY KEY,
  subject_id varchar(128) NOT NULL,
  representation_type varchar(48) NOT NULL,
  representation_version integer NOT NULL CHECK (representation_version >= 1),
  representation jsonb NOT NULL,
  source_asset_id varchar(36) NOT NULL,
  consent_id varchar(128) NOT NULL,
  consent_version varchar(160) NOT NULL,
  model_version varchar(160) NOT NULL,
  status varchar(16) NOT NULL CHECK (status IN ('active','deleted')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_virtual_twin_records_subject_id ON virtual_twin_records(subject_id);
CREATE INDEX IF NOT EXISTS ix_virtual_twin_subject_status ON virtual_twin_records(subject_id,status);
