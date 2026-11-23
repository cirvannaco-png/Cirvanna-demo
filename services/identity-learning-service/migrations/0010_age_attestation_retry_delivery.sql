-- Retry-safe delivery of the exact minimized threshold attestation.
BEGIN;
ALTER TABLE identity_private.identity_age_threshold_attestations
  ADD COLUMN IF NOT EXISTS attestation_payload jsonb,
  ADD COLUMN IF NOT EXISTS signature varchar(128);
ALTER TABLE identity_private.identity_age_threshold_attestations
  ALTER COLUMN attestation_payload SET NOT NULL,
  ALTER COLUMN signature SET NOT NULL;
ALTER TABLE identity_private.identity_age_threshold_attestations
  ADD CONSTRAINT ck_identity_age_attestation_payload_object
    CHECK (jsonb_typeof(attestation_payload) = 'object'),
  ADD CONSTRAINT ck_identity_age_attestation_signature_hex
    CHECK (signature ~ '^[0-9a-f]{64}COMMIT;
);
COMMIT;
