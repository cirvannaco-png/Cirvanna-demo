-- Resource-bound consent receipts for image, body, Twin and rendering purposes.
-- Existing receipts become standalone consent bundles so legacy scope behavior is preserved.
ALTER TABLE identity_tal_consent_receipts
  ADD COLUMN IF NOT EXISTS consent_id varchar(128);
ALTER TABLE identity_tal_consent_receipts
  ADD COLUMN IF NOT EXISTS resource_id varchar(160);

UPDATE identity_tal_consent_receipts
SET consent_id = receipt_id
WHERE consent_id IS NULL;

ALTER TABLE identity_tal_consent_receipts
  ALTER COLUMN consent_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_identity_tal_consent_bundle
  ON identity_tal_consent_receipts(subject_id, consent_id, resource_id, granted);
