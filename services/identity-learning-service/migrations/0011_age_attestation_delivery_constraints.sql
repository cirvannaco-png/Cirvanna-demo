-- Enforce complete, signed payload persistence after the additive column migration.
BEGIN;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM identity_private.identity_age_threshold_attestations
    WHERE attestation_payload IS NULL OR signature IS NULL
  ) THEN
    RAISE EXCEPTION 'age attestation rows require a controlled backfill before enforcing NOT NULL';
  END IF;
END
$$;

ALTER TABLE identity_private.identity_age_threshold_attestations
  ALTER COLUMN attestation_payload SET NOT NULL,
  ALTER COLUMN signature SET NOT NULL;

ALTER TABLE identity_private.identity_age_threshold_attestations
  ADD CONSTRAINT ck_identity_age_attestation_payload_object
    CHECK (jsonb_typeof(attestation_payload) = 'object'),
  ADD CONSTRAINT ck_identity_age_attestation_signature_hex
    CHECK (signature ~ '^[0-9a-f]{64}$');

COMMIT;
