BEGIN;
ALTER TABLE identity_private.identity_age_threshold_attestations
  ALTER COLUMN attestation_payload DROP NOT NULL,
  ALTER COLUMN signature DROP NOT NULL;
COMMIT;
