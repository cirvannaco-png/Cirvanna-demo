-- Canonicalize the idempotency key for a subject/request/purpose/policy tuple.
-- This migration is safe on staging databases where the constraint was already
-- applied under the recorded identity_age_session_request_idempotency migration.
BEGIN;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_identity_age_session_request_policy'
      AND conrelid = 'identity_private.identity_age_verification_sessions'::regclass
  ) THEN
    ALTER TABLE identity_private.identity_age_verification_sessions
      ADD CONSTRAINT uq_identity_age_session_request_policy
      UNIQUE (subject_id, request_id, purpose, policy_id, policy_version);
  END IF;
END
$$;
COMMIT;
