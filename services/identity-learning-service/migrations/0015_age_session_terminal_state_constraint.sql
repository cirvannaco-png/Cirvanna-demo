BEGIN;
ALTER TABLE identity_private.identity_age_verification_sessions
  DROP CONSTRAINT IF EXISTS identity_age_verification_sessions_check;
ALTER TABLE identity_private.identity_age_verification_sessions
  ADD CONSTRAINT ck_identity_age_session_terminal_evidence
  CHECK (
    (state IN ('verified','denied') AND threshold_met IS NOT NULL AND verified_at IS NOT NULL)
    OR (state NOT IN ('verified','denied') AND verified_at IS NULL)
    OR state = 'revoked'
  );
COMMIT;
