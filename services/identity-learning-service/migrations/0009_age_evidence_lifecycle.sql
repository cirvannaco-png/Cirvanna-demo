-- Durable, purpose-bound age assurance state.
-- Raw DOB, age, identity documents and biometrics are intentionally not stored.
BEGIN;

CREATE SCHEMA IF NOT EXISTS identity_private;
GRANT USAGE ON SCHEMA identity_private TO identity_learning_service;

CREATE TABLE IF NOT EXISTS identity_private.identity_age_verification_sessions (
  session_id uuid PRIMARY KEY,
  subject_id varchar(128) NOT NULL,
  request_id varchar(128) NOT NULL,
  purpose varchar(80) NOT NULL,
  policy_id varchar(100) NOT NULL,
  policy_version varchar(64) NOT NULL,
  threshold integer NOT NULL CHECK (threshold BETWEEN 13 AND 125),
  provider varchar(24) NOT NULL CHECK (provider = 'yoti'),
  provider_session_id uuid UNIQUE,
  provider_reference varchar(96) NOT NULL UNIQUE,
  provider_reference_sha256 varchar(64) NOT NULL UNIQUE
    CHECK (provider_reference_sha256 ~ '^[0-9a-f]{64}$'),
  provider_evidence_id varchar(160),
  state varchar(20) NOT NULL CHECK (state IN
    ('created','pending','verified','denied','failed','expired','revoked')),
  threshold_met boolean,
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  verified_at timestamptz,
  revoked_at timestamptz,
  UNIQUE (subject_id, request_id, purpose, policy_id, policy_version),
  CHECK (
    (state IN ('verified','denied') AND threshold_met IS NOT NULL AND verified_at IS NOT NULL)
    OR (state NOT IN ('verified','denied') AND verified_at IS NULL)
    OR state = 'revoked'
  )
);

CREATE INDEX IF NOT EXISTS ix_identity_age_sessions_subject_created
  ON identity_private.identity_age_verification_sessions(subject_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_identity_age_sessions_state_expiry
  ON identity_private.identity_age_verification_sessions(state, expires_at);

CREATE TABLE IF NOT EXISTS identity_private.identity_age_threshold_attestations (
  jti uuid PRIMARY KEY,
  session_id uuid NOT NULL UNIQUE REFERENCES identity_private.identity_age_verification_sessions(session_id) ON DELETE CASCADE,
  subject_id varchar(128) NOT NULL,
  request_id varchar(128) NOT NULL,
  purpose varchar(80) NOT NULL,
  policy_id varchar(100) NOT NULL,
  policy_version varchar(64) NOT NULL,
  threshold integer NOT NULL CHECK (threshold BETWEEN 13 AND 125),
  threshold_met boolean NOT NULL,
  signature_sha256 varchar(64) NOT NULL CHECK (signature_sha256 ~ '^[0-9a-f]{64}$'),
  issued_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  consumed_at timestamptz,
  revoked_at timestamptz,
  CHECK (expires_at > issued_at),
  CHECK (expires_at <= issued_at + interval '15 minutes')
);

CREATE INDEX IF NOT EXISTS ix_identity_age_attestations_subject_expiry
  ON identity_private.identity_age_threshold_attestations(subject_id, expires_at);
CREATE INDEX IF NOT EXISTS ix_identity_age_attestations_session
  ON identity_private.identity_age_threshold_attestations(session_id);

ALTER TABLE identity_private.identity_age_verification_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_age_threshold_attestations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON identity_private.identity_age_verification_sessions FROM anon, authenticated;
REVOKE ALL ON identity_private.identity_age_threshold_attestations FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON identity_private.identity_age_verification_sessions TO identity_learning_service;
GRANT SELECT, INSERT, UPDATE, DELETE ON identity_private.identity_age_threshold_attestations TO identity_learning_service;

DROP POLICY IF EXISTS identity_age_sessions_service_only ON identity_private.identity_age_verification_sessions;
CREATE POLICY identity_age_sessions_service_only ON identity_private.identity_age_verification_sessions
  FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_age_attestations_service_only ON identity_private.identity_age_threshold_attestations;
CREATE POLICY identity_age_attestations_service_only ON identity_private.identity_age_threshold_attestations
  FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);

COMMIT;
