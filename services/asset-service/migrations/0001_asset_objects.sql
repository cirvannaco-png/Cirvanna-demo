CREATE TABLE IF NOT EXISTS asset_objects (
  asset_id varchar(36) PRIMARY KEY,
  owner_user_id varchar(128) NOT NULL,
  purpose varchar(40) NOT NULL,
  parent_id varchar(160) NOT NULL,
  object_key varchar(240) NOT NULL UNIQUE,
  content_type varchar(40) NOT NULL,
  byte_size integer NOT NULL CHECK (byte_size > 0),
  sha256 varchar(64) NOT NULL,
  status varchar(16) NOT NULL CHECK (status IN ('active','deleted')),
  created_at timestamptz NOT NULL DEFAULT now(),
  retention_until timestamptz,
  deleted_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_asset_objects_owner_user_id ON asset_objects(owner_user_id);
CREATE INDEX IF NOT EXISTS ix_asset_owner_parent_status ON asset_objects(owner_user_id,parent_id,status);
CREATE INDEX IF NOT EXISTS ix_asset_expiry_status ON asset_objects(retention_until,status);
