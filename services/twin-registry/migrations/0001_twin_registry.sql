-- Canonical Twin metadata only. Asset bytes remain in private Asset Service.
CREATE TABLE IF NOT EXISTS twin_registry_twins (
  twin_id varchar(128) PRIMARY KEY,
  subject_id varchar(128) NOT NULL,
  mesh_asset_id varchar(36) NOT NULL,
  source_image_asset_ids jsonb NOT NULL,
  representation_type varchar(32) NOT NULL DEFAULT 'full_body_mesh',
  consent_id varchar(128) NOT NULL,
  consent_version varchar(80) NOT NULL,
  model_id varchar(160) NOT NULL,
  model_revision varchar(40) NOT NULL,
  model_release_sha256 varchar(64) NOT NULL,
  validation_report_sha256 varchar(64) NOT NULL,
  state varchar(20) NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  CONSTRAINT ck_twin_registry_state CHECK (state IN ('active','revoked')),
  CONSTRAINT ck_twin_registry_representation CHECK (representation_type = 'full_body_mesh'),
  CONSTRAINT ck_twin_registry_sources_array CHECK (jsonb_typeof(source_image_asset_ids) = 'array'),
  CONSTRAINT ck_twin_registry_sha256 CHECK (
    model_release_sha256 ~ '^[0-9a-f]{64}$'
    AND validation_report_sha256 ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT ck_twin_registry_revision CHECK (model_revision ~ '^[0-9a-f]{40}$')
);

CREATE INDEX IF NOT EXISTS ix_twin_registry_twins_subject_id
  ON twin_registry_twins(subject_id);
CREATE INDEX IF NOT EXISTS ix_twin_registry_twins_state
  ON twin_registry_twins(state);
CREATE INDEX IF NOT EXISTS ix_twin_registry_twin_owner_state
  ON twin_registry_twins(subject_id, state);
CREATE INDEX IF NOT EXISTS ix_twin_registry_twin_created
  ON twin_registry_twins(subject_id, created_at DESC);
