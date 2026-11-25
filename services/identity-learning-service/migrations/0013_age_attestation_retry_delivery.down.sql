BEGIN;
ALTER TABLE identity_private.identity_age_threshold_attestations
  DROP CONSTRAINT IF EXISTS ck_identity_age_attestation_payload_object,
  DROP CONSTRAINT IF EXISTS ck_identity_age_attestation_signature_hex;
ALTER TABLE identity_private.identity_age_threshold_attestations
  DROP COLUMN IF EXISTS attestation_payload,
  DROP COLUMN IF EXISTS signature;
COMMIT;
