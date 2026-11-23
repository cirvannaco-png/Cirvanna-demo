SET search_path TO identity_private;

BEGIN;
DROP INDEX IF EXISTS uq_identity_skin_analysis_consent_id;
DROP TABLE IF EXISTS identity_cil_provider_consent_revocation_outbox;
ALTER TABLE identity_tal_consent_receipts
  DROP CONSTRAINT IF EXISTS ck_identity_skin_analysis_contributor_token;
ALTER TABLE identity_tal_consent_receipts
  DROP COLUMN IF EXISTS provider_contributor_token;
COMMIT;
