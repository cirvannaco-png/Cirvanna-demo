-- Identity / USI / TAL namespace migration.
-- Apply to the existing approved Cirvanna PostgreSQL instance, not a new database.
CREATE TABLE IF NOT EXISTS identity_usi_profiles (
  subject_id varchar(128) PRIMARY KEY,
  profile_version integer NOT NULL DEFAULT 1 CHECK (profile_version >= 1),
  preferences jsonb NOT NULL DEFAULT '[]'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS identity_tal_consent_receipts (
  receipt_id varchar(128) PRIMARY KEY,
  subject_id varchar(128) NOT NULL,
  scope varchar(40) NOT NULL,
  consent_version varchar(80) NOT NULL,
  granted boolean NOT NULL,
  granted_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_identity_tal_consent_subject_scope
  ON identity_tal_consent_receipts(subject_id, scope, granted);
CREATE TABLE IF NOT EXISTS identity_tal_events (
  event_id varchar(128) PRIMARY KEY,
  subject_id varchar(128) NOT NULL,
  consent_receipt_id varchar(128) NOT NULL REFERENCES identity_tal_consent_receipts(receipt_id),
  idempotency_key varchar(160) NOT NULL,
  payload_hash varchar(64) NOT NULL,
  feature_key varchar(120) NOT NULL,
  value text NOT NULL,
  event_kind varchar(24) NOT NULL DEFAULT 'observation',
  supersedes_event_id varchar(128),
  observed_at timestamptz NOT NULL,
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_identity_tal_subject_idempotency UNIQUE(subject_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_identity_tal_subject_observed
  ON identity_tal_events(subject_id, observed_at);
CREATE INDEX IF NOT EXISTS ix_identity_tal_expiry ON identity_tal_events(expires_at);
CREATE TABLE IF NOT EXISTS identity_tal_deletion_receipts (
  receipt_id varchar(128) PRIMARY KEY,
  subject_digest varchar(64) NOT NULL,
  deleted_at timestamptz NOT NULL DEFAULT now(),
  deleted_event_count integer NOT NULL,
  deleted_profile boolean NOT NULL
);
