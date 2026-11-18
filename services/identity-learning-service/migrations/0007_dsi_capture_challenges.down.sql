-- Remove DSI capture challenge and verification receipt state.
BEGIN;
DROP TABLE IF EXISTS identity_dsi_capture_verification_receipts;
DROP TABLE IF EXISTS identity_dsi_capture_challenges;
COMMIT;
