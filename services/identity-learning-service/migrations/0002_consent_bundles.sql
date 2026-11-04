-- Purpose-scoped consent bundles for image, Twin, asset and Try-On operations.
-- Apply after 0001_identity_tal.sql to the existing approved shared PostgreSQL DB.
CREATE TABLE IF NOT EXISTS identity_consent_bundles (
  consent_id varchar(160) PRIMARY KEY,
  subject_id varchar(128) NOT NULL,
  granted_scopes jsonb NOT NULL,
  consent_version varchar(80) NOT NULL,
  resource_id varchar(160),
  granted_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_identity_consent_scopes_array CHECK (jsonb_typeof(granted_scopes) = 'array')
);
CREATE INDEX IF NOT EXISTS ix_identity_consent_subject_active
  ON identity_consent_bundles(subject_id, revoked_at);
