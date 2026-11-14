-- Durable handoff from consent withdrawal to owner-scoped Twin asset deletion.
-- The outbox stores opaque identifiers only; asset bytes remain in Asset Service.
BEGIN;

CREATE TABLE IF NOT EXISTS identity_consent_revocation_outbox (
  command_id varchar(160) PRIMARY KEY,
  subject_id varchar(128) NOT NULL,
  consent_id varchar(128) NOT NULL,
  resource_id varchar(160) NOT NULL,
  receipt_id varchar(128) NOT NULL,
  status varchar(24) NOT NULL DEFAULT 'pending',
  attempts integer NOT NULL DEFAULT 0,
  last_error_code varchar(80),
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  CONSTRAINT ck_identity_consent_revocation_status
    CHECK (status IN ('pending', 'complete')),
  CONSTRAINT ck_identity_consent_revocation_attempts
    CHECK (attempts >= 0)
);

CREATE INDEX IF NOT EXISTS ix_identity_consent_revocation_status_created
  ON identity_consent_revocation_outbox(status, created_at);
CREATE INDEX IF NOT EXISTS ix_identity_consent_revocation_subject
  ON identity_consent_revocation_outbox(subject_id, created_at DESC);

COMMIT;
