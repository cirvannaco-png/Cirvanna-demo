CREATE TABLE IF NOT EXISTS virtual_try_on_jobs (
  subject_id varchar(128) NOT NULL,
  request_id varchar(128) NOT NULL,
  payload_hash varchar(64) NOT NULL,
  twin_id varchar(128) NOT NULL,
  product_id varchar(128) NOT NULL,
  person_image_asset_id varchar(36) NOT NULL,
  garment_image_asset_id varchar(36) NOT NULL,
  garment_asset_purpose varchar(40) NOT NULL,
  garment_asset_parent_id varchar(160) NOT NULL,
  garment_category varchar(32) NOT NULL,
  look_id varchar(128),
  look_version integer,
  wardrobe_snapshot_version integer,
  output_asset_id varchar(36),
  renderer_id varchar(128),
  renderer_version varchar(160),
  consent_id varchar(128) NOT NULL,
  consent_version varchar(160) NOT NULL,
  status varchar(16) NOT NULL CHECK (status IN ('processing','complete','failed','deleted')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  lease_expires_at timestamptz,
  result jsonb,
  PRIMARY KEY(subject_id, request_id)
);
CREATE INDEX IF NOT EXISTS ix_virtual_try_on_jobs_twin_id ON virtual_try_on_jobs(twin_id);
CREATE INDEX IF NOT EXISTS ix_virtual_try_on_jobs_status_lease ON virtual_try_on_jobs(status, lease_expires_at);
