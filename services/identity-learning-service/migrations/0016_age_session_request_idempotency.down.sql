BEGIN;
ALTER TABLE identity_private.identity_age_verification_sessions
  DROP CONSTRAINT IF EXISTS uq_identity_age_session_request_policy;
COMMIT;
