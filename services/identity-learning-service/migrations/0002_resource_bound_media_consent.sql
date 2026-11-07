-- Resource-bound media consent bundle support.
-- Apply to the existing approved identity database; do not provision a new database.
ALTER TABLE identity_tal_consent_receipts ADD COLUMN IF NOT EXISTS consent_id varchar(128);
ALTER TABLE identity_tal_consent_receipts ADD COLUMN IF NOT EXISTS resource_id varchar(160);
UPDATE identity_tal_consent_receipts SET consent_id = receipt_id WHERE consent_id IS NULL;
ALTER TABLE identity_tal_consent_receipts ALTER COLUMN consent_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_identity_tal_consent_bundle ON identity_tal_consent_receipts(subject_id, consent_id, scope, granted, revoked_at);
CREATE INDEX IF NOT EXISTS ix_identity_tal_consent_resource ON identity_tal_consent_receipts(subject_id, resource_id);
