-- Short-lived, consent-bound PNELLY discovery context.
-- The store contains structured search state only; raw conversation transcripts are not retained.
CREATE TABLE IF NOT EXISTS identity_pnelly_conversations (
  conversation_id varchar(36) PRIMARY KEY,
  subject_id varchar(128) NOT NULL,
  consent_receipt_id varchar(128) NOT NULL
    REFERENCES identity_tal_consent_receipts(receipt_id),
  state_version integer NOT NULL DEFAULT 0 CHECK (state_version >= 0),
  context jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_turn_id varchar(128),
  last_turn_hash varchar(64),
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_identity_pnelly_conversation_subject
  ON identity_pnelly_conversations(subject_id);
CREATE INDEX IF NOT EXISTS ix_identity_pnelly_conversation_expiry
  ON identity_pnelly_conversations(expires_at);
