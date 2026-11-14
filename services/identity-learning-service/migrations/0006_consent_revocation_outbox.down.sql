-- Downgrade only after every pending Twin cleanup command has been reconciled.
BEGIN;
DROP TABLE IF EXISTS identity_consent_revocation_outbox;
COMMIT;
