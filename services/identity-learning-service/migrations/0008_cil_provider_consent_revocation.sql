SET search_path TO identity_private;

-- Canonical CIL skin-analysis contributor pseudonyms and durable provider cleanup outbox.
-- Pseudonyms are derived by Identity Learning from a dedicated HMAC key. Raw subject IDs
-- are not passed to CIL or to the external skin-analysis provider.
BEGIN;

ALTER TABLE identity_tal_consent_receipts
  ADD COLUMN IF NOT EXISTS provider_contributor_token varchar(80);

ALTER TABLE identity_tal_consent_receipts
  ADD CONSTRAINT ck_identity_skin_analysis_contributor_token
  CHECK (
    provider_contributor_token IS NULL
    OR provider_contributor_token ~ '^hmac-sha256:[0-9a-f]{64}$'
  );

-- Legacy rows predate contributor pseudonyms and may contain reused consent IDs.
-- They cannot mint new CIL receipts because provider_contributor_token is NULL.
-- Enforce global uniqueness for every new provider-capable grant without making
-- this migration fail on those historical rows.
CREATE UNIQUE INDEX IF NOT EXISTS uq_identity_skin_analysis_consent_id
  ON identity_tal_consent_receipts(consent_id)
  WHERE scope = 'skin_analysis'
    AND granted = true
    AND provider_contributor_token IS NOT NULL;

CREATE TABLE IF NOT EXISTS identity_cil_provider_consent_revocation_outbox (
  command_id varchar(160) PRIMARY KEY,
  revocation_receipt_id varchar(128),
  consent_id varchar(128) NOT NULL,
  resource_id varchar(160),
  receipt_id varchar(128) NOT NULL,
  contributor_token varchar(80),
  status varchar(24) NOT NULL DEFAULT 'pending',
  attempts integer NOT NULL DEFAULT 0,
  last_error_code varchar(80),
  matched_tasks integer NOT NULL DEFAULT 0,
  deleted_tasks integer NOT NULL DEFAULT 0,
  waiting_for_terminal integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  CONSTRAINT ck_identity_cil_provider_revocation_status
    CHECK (status IN ('pending', 'delivered')),
  CONSTRAINT ck_identity_cil_provider_revocation_attempts
    CHECK (attempts >= 0),
  CONSTRAINT ck_identity_cil_provider_revocation_counts
    CHECK (matched_tasks >= 0 AND deleted_tasks >= 0 AND waiting_for_terminal >= 0),
  CONSTRAINT ck_identity_cil_provider_revocation_token
    CHECK (
      contributor_token IS NULL
      OR contributor_token ~ '^hmac-sha256:[0-9a-f]{64}$'
    )
);

-- Safe for an already-created table from an earlier development deployment.
ALTER TABLE identity_cil_provider_consent_revocation_outbox
  ADD COLUMN IF NOT EXISTS revocation_receipt_id varchar(128);
UPDATE identity_cil_provider_consent_revocation_outbox
  SET revocation_receipt_id = receipt_id
  WHERE revocation_receipt_id IS NULL;
ALTER TABLE identity_cil_provider_consent_revocation_outbox
  ALTER COLUMN revocation_receipt_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_identity_cil_provider_revocation_status_created
  ON identity_cil_provider_consent_revocation_outbox(status, created_at);
CREATE INDEX IF NOT EXISTS ix_identity_cil_provider_revocation_receipt
  ON identity_cil_provider_consent_revocation_outbox(revocation_receipt_id);

COMMIT;
