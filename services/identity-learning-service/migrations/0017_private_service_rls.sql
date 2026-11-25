-- Defense-in-depth for the private Identity Learning schema.
-- The Twin Registry schema is owned by its own migration chain.
BEGIN;
REVOKE ALL ON SCHEMA identity_private FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA identity_private FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA identity_private TO identity_learning_service;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA identity_private TO identity_learning_service;

ALTER TABLE identity_private.identity_usi_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_usi_color_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_tal_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_tal_consent_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_tal_deletion_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_pnelly_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_dsi_capture_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_dsi_capture_verification_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_consent_revocation_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_cil_provider_consent_revocation_outbox ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_usi_profiles;
CREATE POLICY identity_private_service_all ON identity_private.identity_usi_profiles FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_usi_color_profiles;
CREATE POLICY identity_private_service_all ON identity_private.identity_usi_color_profiles FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_tal_events;
CREATE POLICY identity_private_service_all ON identity_private.identity_tal_events FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_tal_consent_receipts;
CREATE POLICY identity_private_service_all ON identity_private.identity_tal_consent_receipts FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_tal_deletion_receipts;
CREATE POLICY identity_private_service_all ON identity_private.identity_tal_deletion_receipts FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_pnelly_conversations;
CREATE POLICY identity_private_service_all ON identity_private.identity_pnelly_conversations FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_dsi_capture_challenges;
CREATE POLICY identity_private_service_all ON identity_private.identity_dsi_capture_challenges FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_dsi_capture_verification_receipts;
CREATE POLICY identity_private_service_all ON identity_private.identity_dsi_capture_verification_receipts FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_consent_revocation_outbox;
CREATE POLICY identity_private_service_all ON identity_private.identity_consent_revocation_outbox FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_cil_provider_consent_revocation_outbox;
CREATE POLICY identity_private_service_all ON identity_private.identity_cil_provider_consent_revocation_outbox FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
COMMIT;
