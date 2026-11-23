-- Retry-safe delivery of the exact minimized threshold attestation.
BEGIN;
ALTER TABLE identity_private.identity_age_threshold_attestations
  ADD COLUMN IF NOT EXISTS attestation_payload jsonb,
  ADD COLUMN IF NOT EXISTS signature varchar(128);
COMMIT;
