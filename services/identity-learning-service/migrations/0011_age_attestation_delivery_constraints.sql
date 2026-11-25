-- Enforce complete, signed payload persistence after the additive column migration.
-- Shape and signature-format CHECK constraints are created by 0010; do not
-- recreate them here because PostgreSQL rejects duplicate constraint names.
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

COMMIT;
