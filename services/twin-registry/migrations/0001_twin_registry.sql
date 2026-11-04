-- Persistent Twin ownership and private asset metadata.
-- Object bytes remain in a separately controlled private object store.
CREATE TABLE IF NOT EXISTS twin_registry_assets (
  asset_id varchar(160) PRIMARY KEY,
  owner_subject_id varchar(128),
  tenant_id varchar(160) NOT NULL,
  asset_kind varchar(40) NOT NULL,
  access_scope varchar(20) NOT NULL,
  twin_id varchar(128),
  product_id varchar(128),
  storage_object_key varchar(160) NOT NULL UNIQUE,
  content_type varchar(100) NOT NULL,
  byte_size integer NOT NULL CHECK (byte_size > 0 AND byte_size <= 52428800),
  sha256 varchar(64) NOT NULL,
  state varchar(20) NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  CONSTRAINT ck_twin_asset_access_scope CHECK (access_scope IN ('private','catalog')),
  CONSTRAINT ck_twin_asset_private_owner CHECK (
    (access_scope = 'private' AND owner_subject_id IS NOT NULL AND tenant_id = owner_subject_id)
    OR
    (access_scope = 'catalog' AND owner_subject_id IS NULL AND asset_kind = 'catalog_garment' AND product_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS ix_twin_registry_asset_owner_state
  ON twin_registry_assets(owner_subject_id, state);
CREATE INDEX IF NOT EXISTS ix_twin_registry_asset_product_state
  ON twin_registry_assets(product_id, state);

CREATE TABLE IF NOT EXISTS twin_registry_twins (
  twin_id varchar(128) PRIMARY KEY,
  subject_id varchar(128) NOT NULL,
  mesh_asset_id varchar(160) NOT NULL REFERENCES twin_registry_assets(asset_id),
  model_id varchar(160) NOT NULL,
  model_revision varchar(40) NOT NULL,
  model_release_sha256 varchar(64) NOT NULL,
  validation_report_sha256 varchar(64) NOT NULL,
  state varchar(20) NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_twin_registry_twin_owner_state
  ON twin_registry_twins(subject_id, state);
