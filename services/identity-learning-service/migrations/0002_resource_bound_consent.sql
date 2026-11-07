-- Add grouped and resource-bound consent support without invalidating existing receipts.
ALTER TABLE identity_tal_consent_receipts
  ADD COLUMN IF NOT EXISTS consent_id varchar(128);

UPDATE identity_tal_consent_receipts
SET consent_id = receipt_id
WHERE consent_id IS NULL;

ALTER TABLE identity_tal_consent_receipts
  ALTER COLUMN consent_id SET NOT NULL;

ALTER TABLE identity_tal_consent_receipts
  ADD COLUMN IF NOT EXISTS resource_id varchar(160);

CREATE INDEX IF NOT EXISTS ix_identity_tal_consent_group
  ON identity_tal_consent_receipts(subject_id, consent_id, granted, revoked_at);

CREATE INDEX IF NOT EXISTS ix_identity_tal_consent_resource
  ON identity_tal_consent_receipts(subject_id, resource_id, scope, granted, revoked_at);
